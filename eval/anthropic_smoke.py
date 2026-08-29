#!/usr/bin/env python3
"""Ask whether something speaks the Anthropic Messages API well enough to be Claude.

    python3 eval/anthropic_smoke.py --base-url http://127.0.0.1:8788 --model ...

    0 = it answers and returns a tool_use block    1 = it does not
    2 = cannot judge (nothing reachable there, or it spent every try throttled)

## Why this is a separate file from nim_smoke.py

They ask the same question of two different protocols, and the point of the
exercise is that the protocols differ. `nim_smoke.py` speaks OpenAI chat
completions, which is what the provider offers. This speaks Anthropic Messages,
which is what Claude Code requires. A translating proxy sits between them, and
the only way to know the translation survives *tool calls specifically* -- the
part with the most structure and therefore the most to lose -- is to send an
Anthropic-shaped tool request and insist on an Anthropic-shaped `tool_use`
block coming back.

Pointed at a proxy this tests the translation. Pointed at api.anthropic.com it
tests nothing interesting, which is the correct behaviour for a control.

## Why it stops before Claude Code

The chain is provider -> proxy -> agent, and a failure anywhere in it produces
the same symptom at the end: the agent does nothing and says little. Each link
gets its own probe so that a red run names the link. This is the middle one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nim_smoke import (  # noqa: E402  (path set above)
    BACKOFF, CannotJudge, RETRIES, RETRYABLE, TIMEOUT,
)

import ssl          # noqa: E402
import time         # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

# The Anthropic spelling of nim_smoke's TOOL: same tool, different schema key
# (`input_schema`, not `parameters`) and no `function` wrapper. If a proxy gets
# this wrong the model never sees a tool at all and answers in prose, which is
# why the prose case is reported as its own verdict rather than a generic fail.
TOOL = {
    "name": "read_file",
    "description": "Read a file from disk and return its contents.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string",
                                "description": "Absolute path to read"}},
        "required": ["path"],
    },
}

ANTHROPIC_VERSION = "2023-06-01"


def call(base, key, payload, timeout=TIMEOUT):
    """(status, body, seconds), retrying a throttled upstream. See nim_smoke."""
    delay = BACKOFF
    for attempt in range(RETRIES):
        status, body, secs = call_once(base, key, payload, timeout)
        if status not in RETRYABLE:
            return status, body, secs
        if attempt == RETRIES - 1:
            raise CannotJudge(f"HTTP {status} on all {RETRIES} attempts")
        print(f"          HTTP {status}, waiting {delay}s")
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def call_once(base, key, payload, timeout=TIMEOUT):
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            # Both spellings: a proxy may forward either, and which one it
            # honours is not something we should have to know to test it.
            "x-api-key": key,
            "Authorization": "Bearer " + key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), time.time() - started
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), time.time() - started
    except (urllib.error.URLError, ssl.SSLError, OSError, TimeoutError) as exc:
        raise CannotJudge(f"{type(exc).__name__}: {exc} "
                          f"(after {time.time() - started:.1f}s)") from exc


def blocks_of(body):
    """(content blocks, stop_reason) or (None, None) if not Anthropic-shaped."""
    try:
        d = json.loads(body)
        return d["content"], d.get("stop_reason")
    except (ValueError, KeyError, TypeError):
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("ANTHROPIC_BASE_URL")
                    or "http://127.0.0.1:8788")
    ap.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL")
                    or "claude-sonnet-4-20250514")
    ap.add_argument("--stream", action="store_true")
    a = ap.parse_args()

    key = (os.environ.get("ANTHROPIC_AUTH_TOKEN")
           or os.environ.get("ANTHROPIC_API_KEY") or "placeholder")

    print(f"endpoint  {a.base_url}")
    print(f"model     {a.model}")

    # 1. Does anything answer in the right shape at all?
    try:
        status, body, secs = call(a.base_url, key, {
            "model": a.model, "max_tokens": 32,
            "messages": [{"role": "user", "content": "Reply with the word: ready"}],
        })
    except CannotJudge as exc:
        print(f"cannot judge: nothing answered at {a.base_url} -- {exc}",
              file=sys.stderr)
        return 2
    print(f"plain     HTTP {status} in {secs:.1f}s")
    if status != 200:
        print(f"FAIL: plain message returned {status}: {body[:400]}", file=sys.stderr)
        return 1
    content, _ = blocks_of(body)
    if content is None:
        print(f"FAIL: the response is not an Anthropic message: {body[:300]}",
              file=sys.stderr)
        return 1

    # 2. Does a tool survive the round trip? This is the assertion.
    try:
        status, body, secs = call(a.base_url, key, {
            "model": a.model, "max_tokens": 400, "tools": [TOOL],
            "messages": [{"role": "user", "content":
                          "Read the file /etc/hostname. Use the tool; do not guess."}],
        })
    except CannotJudge as exc:
        print(f"cannot judge: the tool request never returned -- {exc}", file=sys.stderr)
        return 2
    print(f"tools     HTTP {status} in {secs:.1f}s")
    if status != 200:
        print(f"FAIL: tool message returned {status}: {body[:400]}", file=sys.stderr)
        return 1

    content, stop = blocks_of(body)
    if content is None:
        print(f"FAIL: tool response is not an Anthropic message: {body[:300]}",
              file=sys.stderr)
        return 1
    uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
    print(f"          stop_reason={stop}, "
          f"blocks={[b.get('type') for b in content if isinstance(b, dict)]}")
    if not uses:
        prose = " ".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
        print("FAIL: no tool_use block came back. The model answered in prose, or "
              "the translation dropped the tool.", file=sys.stderr)
        print(f"      it said: {prose[:200]}", file=sys.stderr)
        return 1
    for u in uses:
        print(f"          -> tool_use {u.get('name')}({json.dumps(u.get('input'))})")

    # 3. Streaming, because that is the only mode a coding agent uses.
    if a.stream:
        try:
            status, body, secs = call(a.base_url, key, {
                "model": a.model, "max_tokens": 400, "tools": [TOOL], "stream": True,
                "messages": [{"role": "user", "content":
                              "Read the file /etc/hostname. Use the tool."}],
            })
        except CannotJudge as exc:
            print(f"cannot judge: the streaming request never returned -- {exc}",
                  file=sys.stderr)
            return 2
        # An Anthropic stream announces a tool call by opening a content block
        # whose type is tool_use, then dribbling the JSON in as partial_json.
        saw = "tool_use" in body
        deltas = body.count("input_json_delta")
        print(f"stream    HTTP {status} in {secs:.1f}s, {len(body)} bytes, "
              f"tool_use block: {'yes' if saw else 'NO'}, "
              f"{deltas} input_json_delta event(s)")
        if status != 200 or not saw:
            print("FAIL: the stream carried no tool_use", file=sys.stderr)
            print(f"      first bytes: {body[:300]}", file=sys.stderr)
            return 1

    print("\nPASS: this endpoint speaks Anthropic Messages and returns tool_use. "
          "Claude Code can talk to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
