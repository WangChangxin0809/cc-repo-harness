"""Exercise real MCP negotiation and calls through TWO independent subprocesses.

Requires the pinned official SDK; missing SDK is exit 2, never a skipped pass.
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = {"room_claim", "room_release", "room_state", "room_broadcast", "room_read",
         "room_join", "room_open", "room_apply", "room_delete", "room_rename"}


async def scenario(root):
    from mcp import Client, StdioServerParameters
    (root / "src").mkdir()
    (root / "src/shared.py").write_text("# base\n", encoding="utf-8")

    def connect():
        return Client(StdioServerParameters(
            command=sys.executable,
            args=[str(HERE / "server.py"), "--root", str(root), "--name", "same-label"],
        ))

    async def call(client, name, args):
        result = await client.call_tool(name, args)
        assert not result.is_error, str(result.content)
        assert isinstance(result.structured_content, dict), "missing structured output"
        return result.structured_content

    async with connect() as a, connect() as b:
        assert {t.name for t in (await a.list_tools()).tools} == TOOLS
        assert a.instructions and "advisory" in a.instructions
        sa = await call(a, "room_state", {})
        sb = await call(b, "room_state", {})
        assert sa["owner"] != sb["owner"]
        results = await asyncio.gather(
            call(a, "room_claim", {"path": "src/shared.py"}),
            call(b, "room_claim", {"path": "src/shared.py"}),
        )
        assert sum(r["ok"] for r in results) == 1
        winner_idx = 0 if results[0]["ok"] else 1
        winner, loser = (a, b) if winner_idx == 0 else (b, a)
        lease = results[winner_idx]["lease"]
        wrong = await call(loser, "room_release", {"path": "src/shared.py", "lease": lease})
        assert wrong["ok"] is False
        sent = await call(a, "room_broadcast", {"message": "interface updated", "request_id": "one"})
        retry = await call(a, "room_broadcast", {"message": "interface updated", "request_id": "one"})
        assert retry["id"] == sent["id"] and retry["replayed"] is True
        page = await call(b, "room_read", {"after": 0, "limit": 50})
        matches = [e for e in page["events"] if e["kind"] == "broadcast"]
        assert len(matches) == 1 and matches[0]["body"]["message"] == "interface updated"
        assert (await call(b, "room_read", {"after": page["next_cursor"]}))["events"] == []
        invalid = await a.call_tool("room_claim", {"path": "../outside"})
        assert invalid.is_error
        assert (await call(winner, "room_release", {"path": "src/shared.py", "lease": lease}))["ok"]
        assert (await call(loser, "room_claim", {"path": "src/shared.py"}))["ok"]
        state = await call(a, "room_state", {})
        assert state["crdt"] is True
        assert state["workspace"]["backend"] == "pycrdt-v1"
        x = await call(a, "room_open", {"path": "src/shared.py"})
        y = await call(b, "room_open", {"path": "src/shared.py"})
        await asyncio.gather(
            call(a, "room_apply", {"snapshot": x["snapshot"], "text": x["text"]+"# A😀\n", "request_id":"edit-A"}),
            call(b, "room_apply", {"snapshot": y["snapshot"], "text": y["text"]+"# B中\n", "request_id":"edit-B"}),
        )
        current = await call(a, "room_open", {"path":"src/shared.py"})
        assert "A😀" in current["text"] and "B中" in current["text"]
        assert (root / "src/shared.py").read_text(encoding="utf-8") == current["text"]
        first = await call(a, "room_join", {"name":"child-1"})
        second = await call(a, "room_join", {"name":"child-2"})
        assert first["owner"] != second["owner"]
        assert (await call(a,"room_claim",{"path":"child.txt","actor_token":first["actor_token"]}))["ok"]
        assert not (await call(a,"room_claim",{"path":"child.txt","actor_token":second["actor_token"]}))["ok"]
    print(json.dumps({"scope": "mcp-stdio-integration", "sdk": "2.2.0",
                      "clients": 2, "tools": sorted(TOOLS), "result": "pass",
                      "task_outcomes": "not-measured", "crdt": "pycrdt-0.14.4-mediated-edits",
                      "host": "official-sdk-client-not-Claude-Code"}))


def main():
    if not __debug__:
        print("could not judge: assertions disabled by Python optimization", file=sys.stderr)
        return 2
    try:
        if (importlib.metadata.version("mcp") != "2.2.0"
                or importlib.metadata.version("pycrdt") != "0.14.4"):
            raise ValueError("install the pinned requirements.txt in an isolated environment")
    except (importlib.metadata.PackageNotFoundError, ValueError) as exc:
        print("could not judge MCP protocol: " + str(exc), file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="room-mcp-") as tmp:
        subprocess.run(["git", "init", "--quiet", tmp], check=True)
        asyncio.run(asyncio.wait_for(scenario(Path(tmp)), timeout=60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
