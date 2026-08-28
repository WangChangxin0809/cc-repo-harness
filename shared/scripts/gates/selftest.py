#!/usr/bin/env python3
"""Prove every gate in this directory can turn red, and turn green.

    python3 scripts/gates/selftest.py [--verbose]

    0 = every gate passed both directions    1 = a gate failed    2 = cannot run

A gate nobody has watched fail is a file, not a check. This builds a throwaway
git repository in a temporary directory, plants a defect each gate must catch,
and asserts the gate exits 1 *and* names the defect. Then it removes the defect
and asserts the gate exits 0.

Both directions matter and for different reasons. Only checking that it goes red
lets through a gate that is red on everything, which people learn to ignore
within a week. Only checking green lets through a gate that never fires, which
is worse because it looks like evidence.

The failure assertion greps the output for a specific string rather than only
checking the exit code. Exit 1 is a shared observable -- several unrelated
failures produce it, and a selftest that asserts only the code passes for the
wrong reason, which is exactly the bug it is supposed to catch.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def make_repo(tmp):
    for rel, body in (
        ("CLAUDE.md", "# demo\n\nA repository.\n\n## Hard rules\n\n"
                      "1. rule -> docs/x.md\n\n## Commands\n\n`./ci.sh`\n"),
        ("docs/index.md", "# docs\n\n| I want to | Read | Edit |\n|---|---|---|\n"
                          "| a thing | [how](how-to/thing.md) | src/ |\n"),
        ("docs/how-to/thing.md", "# Thing\n\n### 1. Do it\n\n    ./ci.sh\n\n"
                                 "Criterion: exit code is 0.\n"),
        ("README.md", "# demo\n\nA demonstration repository that exists so the "
                      "gates in this directory have something real to judge, "
                      "rather than being asserted against a mock.\n\n"
                      "## Quick start\n\n    ./ci.sh --fast\n\n"
                      "## Requirements\n\n- python 3.9\n\n"
                      "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md).\n\n"
                      "## License\n\nMIT.\n"),
        ("LICENSE", "MIT\n"),
        ("CONTRIBUTING.md", "# Contributing\n\nRun `./ci.sh` before opening a PR.\n"),
        ("SECURITY.md", "# Security\n\nReport privately to the maintainer.\n"),
        ("src/types/model.py", "class Model:\n    pass\n"),
        ("src/service/use.py", "from src.types.model import Model\n\n"
                               "def use():\n    return Model()\n"),
        (".claude/guards.json", json.dumps({
            "protected_branches": ["main"],
            "layers": [{"name": "types", "paths": ["src/types/"]},
                       {"name": "service", "paths": ["src/service/"]}],
        }, indent=2) + "\n"),
    ):
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    sh(["git", "init", "-q"], tmp)
    sh(["git", "add", "-A"], tmp)
    return tmp


# Each case: gate script, the defect to plant, and a fragment the failure output
# must contain. The fragment is what stops a pass-for-the-wrong-reason.
CASES = [
    dict(
        gate="check_layering.py",
        why="an import pointing up the stack",
        needle="point up the layer stack",
        plant=lambda t: write(t, "src/types/model.py",
                              "from src.service.use import use\n\n"
                              "class Model:\n    pass\n"),
    ),
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20"],
        why="a CLAUDE.md over its line cap",
        needle="cap is 20",
        plant=lambda t: write(t, "CLAUDE.md",
                              "# demo\n\nA repository.\n\n## Hard rules\n\n"
                              + "".join(f"{i}. rule -> docs/x.md\n"
                                        for i in range(1, 20))),
    ),
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20"],
        why="a CLAUDE.md left as an empty template",
        needle="almost no content",
        plant=lambda t: write(t, "CLAUDE.md", "# demo\n"),
    ),
    dict(
        gate="check_community_health.py",
        why="a missing LICENSE",
        needle="LICENSE",
        plant=lambda t: remove(t, "LICENSE"),
    ),
    dict(
        gate="check_community_health.py",
        why="a README left as a placeholder",
        needle="under 40 words",
        plant=lambda t: write(t, "README.md", "# demo\n"),
    ),
    dict(
        gate="check_community_health.py",
        why="a README link that resolves to nothing",
        needle="resolve to nothing",
        plant=lambda t: write(t, "README.md",
                              "# demo\n\nA demonstration repository that exists so "
                              "the gates in this directory have something real to "
                              "judge, rather than being asserted against a mock.\n\n"
                              "## Quick start\n\n    ./ci.sh --fast\n\n"
                              "## Requirements\n\n- python 3.9\n\n"
                              "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md) "
                              "and the [handbook](docs/handbook.md).\n\n"
                              "## License\n\nMIT.\n"),
    ),
    dict(
        gate="check_community_health.py",
        why="a GitHub relative link, which must NOT be reported",
        needle=None,
        plant=lambda t: write(t, "SECURITY.md",
                              "# Security\n\nReport via a [private advisory]"
                              "(../../security/advisories/new).\n"),
    ),
    dict(
        gate="check_templates_filled.py",
        why="a scaffolded CLAUDE.md left full of placeholders",
        needle="unfilled placeholder",
        plant=lambda t: write(t, "CLAUDE.md",
                              "# <project>\n\n<One paragraph: what this is.>\n\n"
                              "## Hard rules\n\n1. <rule> -> <docs/path.md>\n"),
    ),
    dict(
        gate="check_templates_filled.py",
        why="a placeholder inside a decision record",
        needle="0002-thing.md",
        plant=lambda t: write(t, "docs/decisions/0002-thing.md",
                              "# 0002 — Thing\n\nDate: <YYYY-MM-DD>\n\n"
                              "We chose the thing.\n"),
    ),
    dict(
        gate="check_templates_filled.py",
        why="an unwritten quick start inside a fenced block",
        needle="a fresh clone",
        plant=lambda t: write(t, "README.md",
                              "# demo\n\nA demonstration repository that exists so the "
                              "gates in this directory have something real to judge, "
                              "rather than being asserted against a mock.\n\n"
                              "## Quick start\n\n```bash\n<the shortest sequence from "
                              "a fresh clone to something working>\n```\n\n"
                              "## Requirements\n\n- python 3.9\n\n"
                              "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md).\n\n"
                              "## License\n\nMIT.\n"),
    ),
    dict(
        gate="check_templates_filled.py",
        why="generics and one-word stand-ins in code, which must NOT be reported",
        needle=None,
        plant=lambda t: write(t, "README.md",
                              "# demo\n\nA demonstration repository that exists so the "
                              "gates in this directory have something real to judge, "
                              "rather than being asserted against a mock.\n\n"
                              "## Quick start\n\n```rust\nlet v: Vec<String> = "
                              "Vec::new();\nlet m: Map<String, Int> = Map::new();\n```\n\n"
                              "Pass `-H \"Authorization: Bearer <token>\"` to "
                              "authenticate. An indented block is code too:\n\n"
                              "    let e: Result<Box<dyn Error>> = run(<REPO>);\n\n"
                              "## Requirements\n\n- python 3.9\n\n"
                              "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md).\n\n"
                              "## License\n\nMIT.\n"),
    ),
    # A script whose real interface the documents below either match or do not.
    # `--tier` exists, `--dry-run` exists, `--flavour` never did.
    dict(
        gate="check_docs_runnable.py",
        why="a documented flag the script does not have",
        needle="has no option --flavour",
        plant=lambda t: (
            write(t, "scripts/scaffold.py",
                  "import argparse\n\n\n"
                  "def main():\n"
                  "    ap = argparse.ArgumentParser()\n"
                  "    ap.add_argument('command', choices=['init', 'check'])\n"
                  "    ap.add_argument('--tier')\n"
                  "    ap.add_argument('--dry-run', action='store_true')\n"
                  "    return ap.parse_args()\n"),
            write(t, "docs/how-to/setup.md",
                  "# Setup\n\n```bash\npython3 scripts/scaffold.py init "
                  "--tier B --flavour vanilla\n```\n")),
    ),
    dict(
        gate="check_docs_runnable.py",
        why="a documented subcommand the script does not have",
        needle="has no subcommand 'bootstrap'",
        plant=lambda t: (
            write(t, "scripts/scaffold.py",
                  "import argparse\n\n\n"
                  "def main():\n"
                  "    ap = argparse.ArgumentParser()\n"
                  "    ap.add_argument('command', choices=['init', 'check'])\n"
                  "    ap.add_argument('--tier')\n"
                  "    return ap.parse_args()\n"),
            write(t, "docs/how-to/setup.md",
                  "# Setup\n\n```bash\npython3 scripts/scaffold.py bootstrap "
                  "--tier B\n```\n")),
    ),
    # Three ways to be right that a blunter check would call wrong: a
    # placeholder value, a `<plugin>/` prefix, and a hook wiring quoted inside
    # JSON, which is not a command line at all.
    dict(
        gate="check_docs_runnable.py",
        why="correct commands in every dialect these documents use",
        needle=None,
        plant=lambda t: (
            write(t, "scripts/scaffold.py",
                  "import argparse\n\n\n"
                  "def main():\n"
                  "    ap = argparse.ArgumentParser()\n"
                  "    ap.add_argument('command', choices=['init', 'check'])\n"
                  "    ap.add_argument('--tier')\n"
                  "    ap.add_argument('--dry-run', action='store_true')\n"
                  "    return ap.parse_args()\n"),
            write(t, "docs/how-to/setup.md",
                  "# Setup\n\n```bash\n"
                  "python3 <plugin>/scripts/scaffold.py init --tier <A|B|C>\n"
                  "python3 scripts/scaffold.py check --dry-run  # a comment\n"
                  "```\n\nWire it up:\n\n```json\n"
                  "{\"hooks\": [{\"command\": \"python3 scripts/nothing.py\"}]}\n"
                  "```\n")),
    ),
    dict(
        gate="check_docs_index.py",
        why="a document nothing routes to",
        needle="does not route to",
        plant=lambda t: write(t, "docs/how-to/orphan.md", "# Orphan\n"),
    ),
    dict(
        gate="check_docs_index.py",
        why="a route pointing at nothing",
        needle="point at nothing",
        plant=lambda t: write(t, "docs/index.md",
                             "# docs\n\n| I want to | Read | Edit |\n|---|---|---|\n"
                             "| a thing | [how](how-to/thing.md) | src/ |\n"
                             "| gone | [g](how-to/removed.md) | src/ |\n"),
    ),
]


def write(root, rel, body):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    sh(["git", "add", "-A"], root)


def remove(root, rel):
    os.remove(os.path.join(root, rel))
    sh(["git", "add", "-A"], root)


def run_gate(case, root):
    return sh([sys.executable, os.path.join(HERE, case["gate"]),
               "--root", root, *case.get("args", [])], root)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2

    failures = []
    for case in CASES:
        label = f"{case['gate']}: {case['why']}"
        tmp = make_repo(tempfile.mkdtemp(prefix="gate-selftest-"))
        try:
            clean = run_gate(case, tmp)
            if clean.returncode != 0:
                failures.append(
                    f"{label}\n    baseline is not green: exit "
                    f"{clean.returncode}\n    {clean.stderr.strip()[:400]}")
                continue

            case["plant"](tmp)
            dirty = run_gate(case, tmp)
            out = dirty.stdout + dirty.stderr
            if case["needle"] is None:
                # A must-still-pass case. Without at least one of these per
                # gate, a check that matches everything looks perfect here.
                if dirty.returncode != 0:
                    failures.append(
                        f"{label}\n    over-blocked: exit {dirty.returncode}\n"
                        f"    {out.strip()[:400]}")
                elif a.verbose:
                    print(f"  ok  {label}")
                continue
            if dirty.returncode != 1:
                failures.append(f"{label}\n    did not fail: exit "
                                f"{dirty.returncode}")
            elif case["needle"] not in out:
                failures.append(
                    f"{label}\n    failed, but not for the stated reason — "
                    f"{case['needle']!r} absent from the output\n"
                    f"    {out.strip()[:400]}")
            elif a.verbose:
                print(f"  ok  {label}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"{len(failures)} of {len(CASES)} gate case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if a.verbose:
        print(f"{len(CASES)} gate cases: each turns red on its defect and green "
              f"without it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
