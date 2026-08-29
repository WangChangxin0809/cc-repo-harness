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

The first attempt to run this ran on a machine behind a proxy that permits
`GET /v1/models` and holds `POST /v1/chat/completions` open for sixty seconds
before resetting it. Both a blocked network and a broken key produce "no
answer". Calling that a failure would have sent us debugging a key that was
fine. A refused or filtered network is a thing this script *could not judge*,
and it says so.
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
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-pro-0813"

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


class CannotJudge(Exception):
    """The network would not carry the question. Not a verdict on the endpoint."""


def call(base, key, payload, timeout=TIMEOUT):
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


def main():
    ap = argparse.ArgumentParser()
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
