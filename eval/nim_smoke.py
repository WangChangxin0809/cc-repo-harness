#!/usr/bin/env python3
"""Ask whether an OpenAI-shaped endpoint can actually drive a coding agent.

    NVIDIA_API_KEY=... python3 eval/nim_smoke.py [--model ...] [--base-url ...]

    0 = the endpoint answers and calls tools    1 = it does not
    2 = cannot judge (no key, or the network will not carry the question)

## Why this exists as its own step

The corpus plan needs a model behind Claude Code that is not Claude, and the
cheapest way to get one is an OpenAI-shaped provider plus a translating proxy.
That stack has four places to fail and they fail identically from the outside --
a hung request tells you nothing about which layer hung. So this asks the
narrowest question first, of the provider alone, with no proxy and no agent in
the path: *does this key, on this model, return a tool call?*

Tool calling is the whole test. A coding agent that cannot emit a tool call
cannot read a file, and a provider that merely produces fluent text is useless
to us. Everything else here is scaffolding around that one assertion.

## Why exit 2 is a distinct answer

Twice now the honest answer has been "no measurement was taken", and twice the
tempting answer was "fail".

`deepseek-v4-pro` is in the catalogue and accepts a sixteen-token request, then
holds the connection open for sixty-one seconds and resets it. A model that
cannot be reached and a key that is wrong both produce silence; scoring that as
failure sends you debugging a key that is fine. The way to tell them apart is
in the script: a request naming a model that cannot exist comes back 404 in a
second, which proves the path is open and puts the silence on the model.

Then `minimax-m3` answered, called the tool correctly -- and the next request
came back 429, because a free tier does not serve three in a row. The first
version of this script recorded that as "does not support streaming tool calls"
about a model it had just watched make one. A throttled provider is declining
to be measured, so `call()` backs off and retries, and gives up into exit 2.

Exit 1 is reserved for the endpoint answering and the answer being unfit.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://integrate.api.nvidia.com"
# Measured, not chosen: on one tool-calling prompt, nemotron-3-super answers in
# 2.2s where minimax-m3 takes 10.3s and deepseek-v4-pro never answers at all --
# it accepts a sixteen-token request and then holds the connection open for 61s
# before resetting it. This is a default for a smoke test, where the only
# requirement is that the endpoint reliably works; which model actually drives
# the corpus is a question about agentic quality that latency cannot answer.
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# Candidates worth re-checking when the provider changes. Catalogue membership
# is not availability: nemotron-nano-3-30b-a3b is listed and returns 404
# "Model not found", which is why `probe` reports a row instead of asserting.
CANDIDATES = (
    "openai/gpt-oss-120b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "moonshotai/kimi-k3",
    "minimaxai/minimax-m3",
)

# Long enough that a reasoning model's first token is not mistaken for a hang,
# short enough that a filtered connection is not mistaken for slowness. The
# proxy that prompted exit 2 reset at 61s, so this sits well past it.
TIMEOUT = 180

TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file from disk and return its contents.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string",
                                    "description": "Absolute path to read"}},
            "required": ["path"],
        },
    },
}


# A shared free tier answers three requests in a row with a rate limit, and a
# rate limit is the provider declining to be measured -- not the provider
# failing. The first version of this script scored a 429 as "does not support
# streaming tool calls" about a model that had demonstrably just made one.
RETRYABLE = frozenset((429, 500, 502, 503, 504))
RETRIES = 4
BACKOFF = 8  # seconds, then doubled


class CannotJudge(Exception):
    """The network would not carry the question. Not a verdict on the endpoint."""


def call(base, key, payload, timeout=TIMEOUT):
    """(status, body_text, seconds), retrying a throttled or flapping upstream.

    Raises CannotJudge if nothing ever came back, or if the provider spent every
    attempt declining to serve one. Both mean the same thing to a caller: no
    measurement was taken. Neither means the endpoint is unfit."""
    delay = BACKOFF
    for attempt in range(RETRIES):
        status, body, secs = call_once(base, key, payload, timeout)
        if status not in RETRYABLE:
            return status, body, secs
        if attempt == RETRIES - 1:
            raise CannotJudge(
                f"HTTP {status} on every one of {RETRIES} attempts -- the "
                f"provider is throttling or unwell, not answering the question")
        print(f"          HTTP {status}, waiting {delay}s "
              f"({attempt + 1}/{RETRIES - 1})")
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def call_once(base, key, payload, timeout=TIMEOUT):
    """(status, body_text, seconds). Raises CannotJudge if nothing came back."""
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), time.time() - started
    except urllib.error.HTTPError as exc:
        # An HTTP status is an answer, even a rude one: the request arrived.
        return exc.code, exc.read().decode("utf-8", "replace"), time.time() - started
    except (urllib.error.URLError, ssl.SSLError, OSError, TimeoutError) as exc:
        raise CannotJudge(f"{type(exc).__name__}: {exc} "
                          f"(after {time.time() - started:.1f}s)") from exc


def models(base, key, timeout=60):
    """The ids the endpoint admits to. Used to tell a typo from an outage."""
    req = urllib.request.Request(base.rstrip("/") + "/v1/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return sorted(m["id"] for m in json.load(resp).get("data", []))
    except Exception:
        return None


def tool_calls_in(body):
    """The tool calls a non-streaming response carries, or None if malformed."""
    try:
        message = json.loads(body)["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return message.get("tool_calls") or []


def probe(base, key, model):
    """One model's row: (verdict, seconds, detail).

    Verdict is pass / prose / error / unreachable. Kept separate from main()'s
    exit codes because a comparison wants every row, not the first refusal."""
    try:
        status, body, secs = call(base, key, {
            "model": model, "max_tokens": 300, "tools": [TOOL],
            "messages": [{"role": "user", "content":
                          "Read the file /etc/hostname. Use the tool; do not guess."}],
        })
    except CannotJudge as exc:
        return ("unreachable", None, str(exc)[:90])
    if status != 200:
        return ("error", secs, f"HTTP {status}: {body[:80]}")
    calls = tool_calls_in(body)
    if calls is None:
        return ("error", secs, "unparseable response")
    if not calls:
        return ("prose", secs, "answered in prose, never called the tool")
    fn = calls[0].get("function", {})
    return ("pass", secs, f"{fn.get('name')}({fn.get('arguments')})"[:70])


def compare(base, key, names, pause):
    """Rank candidates by whether they call tools, then by how fast.

    A shared free tier rate-limits bursts, so this paces itself. That makes the
    run slow and the numbers honest; a burst would measure the throttle."""
    rows = []
    for i, model in enumerate(names):
        if i:
            time.sleep(pause)
        verdict, secs, detail = probe(base, key, model)
        rows.append((model, verdict, secs, detail))
        print(f"  {verdict:<11} {secs if secs is None else round(secs, 1):>6}s  "
              f"{model:<40} {detail}")

    ok = sorted((r for r in rows if r[1] == "pass"), key=lambda r: r[2])
    print()
    if not ok:
        print("No candidate called a tool. None of these can drive a coding agent.")
        return 1
    print("Usable, fastest first:")
    for model, _, secs, _ in ok:
        print(f"  {secs:>6.1f}s  {model}")
    print(f"\nPASS: {len(ok)}/{len(rows)} candidates call tools. "
          f"Fastest is {ok[0][0]} at {ok[0][2]:.1f}s.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", nargs="?", const=",".join(CANDIDATES), default="",
                    help="rank model ids against each other; bare flag uses CANDIDATES")
    ap.add_argument("--pause", type=float, default=6.0,
                    help="seconds between candidates, to stay under the rate limit")
    # `or`, not a get() default: CI sets these to the empty string when the
    # triggering event carries no inputs, and an empty string is present.
    ap.add_argument("--base-url", default=os.environ.get("NIM_BASE_URL") or DEFAULT_BASE)
    ap.add_argument("--model", default=os.environ.get("NIM_MODEL") or DEFAULT_MODEL)
    ap.add_argument("--stream", action="store_true",
                    help="also check the streaming path, which is what agents use")
    a = ap.parse_args()

    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NIM_API_KEY")
    if not key:
        print("cannot judge: no NVIDIA_API_KEY in the environment", file=sys.stderr)
        return 2

    print(f"endpoint  {a.base_url}")

    if a.compare:
        names = [n.strip() for n in a.compare.split(",") if n.strip()]
        available = models(a.base_url, key)
        if available is None:
            print("cannot judge: could not list models", file=sys.stderr)
            return 2
        unknown = [n for n in names if n not in available]
        if unknown:
            print("FAIL: not in the catalogue: " + ", ".join(unknown), file=sys.stderr)
            return 1
        print(f"comparing {len(names)} candidates, {a.pause}s apart\n")
        return compare(a.base_url, key, names, a.pause)

    print(f"model     {a.model}")

    available = models(a.base_url, key)
    if available is None:
        print("cannot judge: could not list models; the endpoint is unreachable "
              "or the key is not accepted", file=sys.stderr)
        return 2
    print(f"catalogue {len(available)} models")
    if a.model not in available:
        near = [m for m in available if m.split("/")[-1][:8] in a.model]
        print(f"FAIL: {a.model} is not in the catalogue", file=sys.stderr)
        if near:
            print("      did you mean: " + ", ".join(near[:5]), file=sys.stderr)
        return 1

    # 1. Does it answer at all?
    try:
        status, body, secs = call(a.base_url, key, {
            "model": a.model, "max_tokens": 16,
            "messages": [{"role": "user", "content": "Reply with the word: ready"}],
        })
    except CannotJudge as exc:
        print(f"cannot judge: the completion request never returned -- {exc}",
              file=sys.stderr)
        print("      the model listing succeeded, so the key and host are fine; "
              "something between here and there is filtering inference calls.",
              file=sys.stderr)
        return 2
    print(f"plain     HTTP {status} in {secs:.1f}s")
    if status != 200:
        print(f"FAIL: plain completion returned {status}: {body[:300]}", file=sys.stderr)
        return 1

    # 2. Does it call tools? This is the assertion that matters.
    try:
        status, body, secs = call(a.base_url, key, {
            "model": a.model, "max_tokens": 300, "tools": [TOOL],
            "messages": [{"role": "user", "content":
                          "Read the file /etc/hostname. Use the tool; do not guess."}],
        })
    except CannotJudge as exc:
        print(f"cannot judge: the tool request never returned -- {exc}", file=sys.stderr)
        return 2
    print(f"tools     HTTP {status} in {secs:.1f}s")
    if status != 200:
        print(f"FAIL: tool completion returned {status}: {body[:300]}", file=sys.stderr)
        return 1

    calls = tool_calls_in(body)
    if calls is None:
        print(f"FAIL: tool response was not shaped as expected: {body[:300]}",
              file=sys.stderr)
        return 1
    if not calls:
        print("FAIL: the model answered in prose instead of calling the tool. "
              "It cannot drive a coding agent.", file=sys.stderr)
        return 1
    for c in calls:
        fn = c.get("function", {})
        print(f"          -> {fn.get('name')}({fn.get('arguments')})")

    # 3. Streaming, optionally: agents stream, and a provider can pass 1 and 2
    #    while emitting tool-call deltas nothing can reassemble.
    if a.stream:
        try:
            status, body, secs = call(a.base_url, key, {
                "model": a.model, "max_tokens": 300, "tools": [TOOL], "stream": True,
                "messages": [{"role": "user", "content":
                              "Read the file /etc/hostname. Use the tool."}],
            })
        except CannotJudge as exc:
            print(f"cannot judge: the streaming request never returned -- {exc}",
                  file=sys.stderr)
            return 2
        saw = "tool_calls" in body
        print(f"stream    HTTP {status} in {secs:.1f}s, "
              f"{len(body)} bytes, tool_calls deltas: {'yes' if saw else 'NO'}")
        if status != 200 or not saw:
            print("FAIL: streaming did not carry tool calls", file=sys.stderr)
            return 1

    print("\nPASS: this endpoint answers and calls tools. It can sit behind a "
          "translating proxy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
