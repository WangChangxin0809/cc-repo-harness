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
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

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
        # The demo repository is also a minimal plugin. check_plugin_structure
        # exits 2 -- cannot judge -- without a manifest, and every case here
        # asserts a green baseline first, so the surface has to exist before a
        # defect can be planted in it.
        (".claude-plugin/plugin.json", json.dumps({
            "name": "demo-plugin",
            "version": "0.1.0",
            "description": "A demonstration plugin.",
        }, indent=2) + "\n"),
        ("skills/demo/SKILL.md",
         "---\nname: demo\ndescription: Demonstrate something, when asked to.\n"
         "---\n\n# Demo\n\nGuidance lives here.\n"),
        ("agents/helper.md",
         "---\nname: helper\ndescription: Helps with demonstrations.\n---\n\n"
         "You help.\n"),
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
        gate="check_no_machine_paths.py",
        why="a committed file carrying somebody's home directory",
        needle="absolute home directory",
        # Assembled, not written: this file is committed, and a gate whose
        # red case plants a real-looking home path would fail on its own
        # source -- which it did, on the first run after being wired in.
        plant=lambda t: write(t, "results/run.json",
                              '{"python": "%s%s/proj/.venv/bin/python"}\n'
                              % ("/ho" + "me/", "j" + "smith")),
    ),
    dict(
        gate="check_no_machine_paths.py",
        why="a document showing the shape of a path, which is what it asks for",
        needle=None,
        plant=lambda t: write(t, "docs/setup.md",
                              "Run it from `/home/you/projects/thing`, or from\n"
                              "`/Users/username/src`. On CI the root is\n"
                              "`/home/runner/work/repo/repo`.\n"),
    ),
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
        why="instructions parked in .claude/CLAUDE.md instead of the root",
        # `./CLAUDE.md` **or** `./.claude/CLAUDE.md` -- both are first-party
        # project locations and both load. Counting only the root one meant a
        # repository following the documented layout returned "cannot judge"
        # while carrying hundreds of always-on lines.
        needle="cap is 20",
        plant=lambda t: write(t, ".claude/CLAUDE.md",
                              "# demo\n\n" + "".join(f"- rule {i}\n"
                                                     for i in range(1, 40))),
    ),
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20"],
        why="an unscoped .claude/rules file, which loads at launch",
        # "Rules without `paths` frontmatter are loaded at launch with the same
        # priority as `.claude/CLAUDE.md`." Not counting them made the whole
        # directory a bypass: move a hundred lines there and the cost is
        # identical while the cap goes quiet.
        needle="cap is 20",
        plant=lambda t: write(t, ".claude/rules/style.md",
                              "# style\n\n" + "".join(f"- rule {i}\n"
                                                      for i in range(1, 40))),
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
        why="HTML markup GitHub renders, which must NOT be reported",
        needle=None,
        plant=lambda t: write(t, "README.md",
                              "# demo\n\nA demonstration repository that exists so the "
                              "gates in this directory have something real to judge, "
                              "rather than being asserted against a mock.\n\n"
                              '<div align="center">\n\n'
                              '<img src="logo.svg" alt="the project logo" width="480">\n\n'
                              "</div>\n\n<details>\n<summary>The long tree</summary>\n\n"
                              "It is folded away because nobody reads it first.\n\n"
                              "</details>\n\n"
                              "## Requirements\n\n- python 3.9\n\n"
                              "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md).\n\n"
                              "## License\n\nMIT.\n"),
    ),
    dict(
        gate="check_templates_filled.py",
        why="a tag-shaped placeholder nothing ever closes, which IS still reported",
        needle="unfilled placeholder",
        plant=lambda t: write(t, "CLAUDE.md",
                              "# demo\n\n## What to write here\n\n<summary>\n\n"
                              "<section>\n"),
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
    # The plugin surface. This is the half of the repository that Claude Code
    # actually loads, and until this gate existed it had no coverage at all --
    # payload is code and code gets selftests, while a skill is markdown and
    # nobody writes a test for a paragraph.
    dict(
        gate="check_plugin_structure.py",
        why="a skill telling an agent to guess the plugin's location",
        needle="hand-invented placeholder",
        plant=lambda t: write(t, "skills/demo/SKILL.md",
                              "---\nname: demo\ndescription: Demonstrate "
                              "something, when asked to.\n---\n\n"
                              "Read `<plugin>/references/moments.md` first.\n"),
    ),
    # Bodies are free -- they load when the thing is invoked. The frontmatter
    # is not: every skill, agent and command is listed by name and description
    # on every turn, in every repository on the machine, including the ones
    # that never touch this plugin. Nothing measured that, and this repository
    # drifted to 350 tokens a turn, most of it one description that had grown a
    # clause for every symptom anyone might type.
    dict(
        gate="check_plugin_structure.py",
        args=["--always-on-cap", "60"],
        why="a description that has grown a clause for every symptom",
        needle="on every turn, cap is 60",
        plant=lambda t: write(t, "skills/demo/SKILL.md",
                              "---\nname: demo\ndescription: Demonstrate "
                              "something, when asked to. " +
                              "Use it when somebody mentions a thing. " * 12 +
                              "\n---\n\n# Demo\n\nGuidance lives here.\n"),
    ),
    # The other direction: a long *body* is not a cost, and charging for it
    # would push guidance out of the one place it is free.
    dict(
        gate="check_plugin_structure.py",
        args=["--always-on-cap", "60"],
        why="a long body behind a short description",
        needle=None,
        plant=lambda t: write(t, "skills/demo/SKILL.md",
                              "---\nname: demo\ndescription: Demonstrate "
                              "something, when asked to.\n---\n\n# Demo\n\n"
                              + "A paragraph of guidance.\n" * 400),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="component directories nested inside .claude-plugin/",
        needle="not inside .claude-plugin/",
        plant=lambda t: write(t, ".claude-plugin/skills/x/SKILL.md",
                              "---\nname: x\ndescription: Does x.\n---\n\nx\n"),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="a skill whose frontmatter has no description",
        needle="deciding whether this skill is ever activated",
        plant=lambda t: write(t, "skills/demo/SKILL.md",
                              "---\nname: demo\n---\n\nGuidance lives here.\n"),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="a manifest version that is not semver",
        needle="is not semver",
        plant=lambda t: write(t, ".claude-plugin/plugin.json",
                              json.dumps({"name": "demo-plugin",
                                          "version": "v0.1",
                                          "description": "A demo plugin."},
                                         indent=2) + "\n"),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="an agents list that drops the agent at the top level",
        needle="leaves out agents/helper.md",
        # A listed path replaces the default directory. The manifest names
        # the new agent and forgets the old one, and the loader says nothing.
        plant=lambda t: (write(t, "agents/assess/reader.md",
                               "---\nname: reader\ndescription: Reads one "
                               "thing.\n---\n\nYou read.\n"),
                         write(t, ".claude-plugin/plugin.json",
                               json.dumps({"name": "demo-plugin",
                                           "version": "0.1.0",
                                           "description": "A demo plugin.",
                                           "agents": ["./agents/assess/reader.md"]},
                                          indent=2) + "\n")),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="an agents list naming a file that is not there",
        needle="does not exist",
        plant=lambda t: write(t, ".claude-plugin/plugin.json",
                              json.dumps({"name": "demo-plugin",
                                          "version": "0.1.0",
                                          "description": "A demo plugin.",
                                          "agents": ["./agents/helper.md",
                                                     "./agents/gone.md"]},
                                         indent=2) + "\n"),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="an agent in a subdirectory with no description",
        needle="agents/assess/reader.md frontmatter has no `description`",
        plant=lambda t: write(t, "agents/assess/reader.md",
                              "---\nname: reader\n---\n\nYou read.\n"),
    ),
    dict(
        gate="check_plugin_structure.py",
        why="the variable itself, which must NOT be reported",
        needle=None,
        plant=lambda t: write(t, "skills/demo/SKILL.md",
                              "---\nname: demo\ndescription: Demonstrate "
                              "something, when asked to.\n---\n\n"
                              "Read `${CLAUDE_PLUGIN_ROOT}/references/"
                              "moments.md` first.\n"),
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
    # A command written the way a skill has to write it: behind the variable
    # Claude Code sets to the plugin's install location. This case is red, not
    # green, on purpose. A green one would not pin anything -- delete the strip
    # in resolve_script() and the command stops resolving, so it is silently
    # skipped and the gate still exits 0. That is precisely the bug this case
    # exists to catch, and it was live here until the day it was found: every
    # `${CLAUDE_PLUGIN_ROOT}` command in the skills went unchecked.
    dict(
        gate="check_docs_runnable.py",
        why="a bad flag on a command written with ${CLAUDE_PLUGIN_ROOT}",
        needle="has no option --flavour",
        plant=lambda t: (
            write(t, "scripts/scaffold.py",
                  "import argparse\n\n\n"
                  "def main():\n"
                  "    ap = argparse.ArgumentParser()\n"
                  "    ap.add_argument('command', choices=['init', 'check'])\n"
                  "    ap.add_argument('--tier')\n"
                  "    return ap.parse_args()\n"),
            write(t, "docs/how-to/setup.md",
                  "# Setup\n\n```bash\npython3 ${CLAUDE_PLUGIN_ROOT}/scripts/"
                  "scaffold.py init --tier B --flavour vanilla\n```\n")),
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
                  "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py init "
                  "--tier <A|B|C>\n"
                  "python3 <plugin>/scripts/scaffold.py init --tier <A|B|C>\n"
                  "python3 scripts/scaffold.py check --dry-run  # a comment\n"
                  "```\n\nWire it up:\n\n```json\n"
                  "{\"hooks\": [{\"command\": \"python3 scripts/nothing.py\"}]}\n"
                  "```\n")),
    ),
    # A ```markdown fence holds sample markup -- the shape of a good how-to
    # step -- and the paths inside it name nothing in this tree on purpose.
    # The gate read one as a live command and reported a document that was
    # doing its job, which is the false red this pair pins.
    dict(
        gate="check_docs_runnable.py",
        why="a command inside a markdown sample is not a command",
        needle=None,
        plant=lambda t: write(
            t, "docs/how-to/writing.md",
            "# Writing a step\n\nEvery step has three parts:\n\n"
            "```markdown\n### 3. Rebuild the index\n\n"
            "    python3 scripts/index/build.py\n\n"
            "Criterion: `scripts/index/query.py --stats` agrees with git grep.\n"
            "```\n"),
    ),
    # The other half, and the one that keeps the skip narrow: the identical
    # command in a bash fence is still a finding. Widen SAMPLE_LANGS to every
    # language and this case is what goes green when it should not.
    dict(
        gate="check_docs_runnable.py",
        why="the same command in a bash fence is still a command",
        needle="names a script that does not exist",
        plant=lambda t: write(
            t, "docs/how-to/writing.md",
            "# Writing a step\n\n```bash\n"
            "python3 scripts/index/build.py\n```\n"),
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
    dict(
        gate="check_docs_index.py",
        # The defect the folder shape invites. Routing an exec-plan reaches the
        # steps its README links, so a step nobody linked is now invisible in a
        # way a loose document never was -- it sits inside a folder that is
        # routed, next to siblings that are reached. The needle is the step's
        # own path: "does not route to" would also be printed for the README, so
        # asserting only that would pass while the step went unreported.
        why="an exec-plan step its README does not link",
        needle="steps/02-unlinked.md",
        plant=lambda t: (
            write(t, "docs/index.md",
                  "# docs\n\n| I want to | Read | Edit |\n|---|---|---|\n"
                  "| a thing | [how](how-to/thing.md) | src/ |\n"
                  "| a plan | [plan](exec-plans/demo/README.md) | src/ |\n"),
            write(t, "docs/exec-plans/demo/README.md",
                  "# Demo plan\n\n- [ ] todo [first](steps/01-first.md)\n"),
            write(t, "docs/exec-plans/demo/steps/01-first.md", "# First\n"),
            write(t, "docs/exec-plans/demo/steps/02-unlinked.md", "# Unlinked\n")),
    ),

    dict(
        gate="check_docs_layout.py",
        # The failure that actually happened to OpenStack's seventh repository:
        # `configuration/` became `config/`, nothing broke that day, and both
        # spellings accumulated documents. Here it is `decisions/` forking to
        # `adr/` -- the most likely fork, since `docs/adr` is about twice as
        # common on GitHub as `docs/decisions`.
        why="a required bucket renamed to a common variant",
        needle="fork a required name",
        plant=lambda t: write(t, "docs/adr/0001-something.md",
                              "# 0001 — Something\n\nStatus: accepted\n"),
    ),
    dict(
        gate="check_docs_layout.py",
        why="a document loose at the top of docs/",
        needle="loose at the top",
        plant=lambda t: write(t, "docs/notes.md", "# Notes\n\nStray.\n"),
    ),

    dict(
        gate="check_file_size.py",
        args=["--cap", "30"],
        why="a tracked file over the line cap",
        needle="cap is 30",
        plant=lambda t: write(t, "src/big.py",
                              "".join(f"x = {i}\n" for i in range(1, 50))),
    ),
    dict(
        gate="check_file_size.py",
        args=["--cap", "30"],
        why="an exemption with a reason for a file still over the cap",
        needle=None,
        plant=lambda t: (
            write(t, "src/big.py",
                  "".join(f"x = {i}\n" for i in range(1, 50))),
            write(t, ".claude/guards.json", json.dumps({
                "protected_branches": ["main"],
                "layers": [{"name": "types", "paths": ["src/types/"]},
                          {"name": "service", "paths": ["src/service/"]}],
                "file_size": {"exempt": [
                    {"path": "src/big.py",
                     "reason": "kept large for this demo repository"}]},
            }, indent=2) + "\n")),
    ),
    dict(
        gate="check_file_size.py",
        args=["--cap", "30"],
        why="an exemption with no reason",
        needle="exemption has no reason",
        plant=lambda t: (
            write(t, "src/big.py",
                  "".join(f"x = {i}\n" for i in range(1, 50))),
            write(t, ".claude/guards.json", json.dumps({
                "protected_branches": ["main"],
                "layers": [{"name": "types", "paths": ["src/types/"]},
                          {"name": "service", "paths": ["src/service/"]}],
                "file_size": {"exempt": [{"path": "src/big.py",
                                          "reason": ""}]},
            }, indent=2) + "\n")),
    ),
    dict(
        gate="check_file_size.py",
        args=["--cap", "30"],
        why="an exemption for a file that no longer needs it",
        needle="outlived its reason",
        plant=lambda t: (
            write(t, "src/small.py", "x = 1\n"),
            write(t, ".claude/guards.json", json.dumps({
                "protected_branches": ["main"],
                "layers": [{"name": "types", "paths": ["src/types/"]},
                          {"name": "service", "paths": ["src/service/"]}],
                "file_size": {"exempt": [{"path": "src/small.py",
                                          "reason": "used to be big"}]},
            }, indent=2) + "\n")),
    ),
    dict(
        gate="check_file_size.py",
        args=["--cap", "30"],
        why="an exemption naming a file that has since been deleted or renamed",
        needle="no longer exists",
        plant=lambda t: write(t, ".claude/guards.json", json.dumps({
            "protected_branches": ["main"],
            "layers": [{"name": "types", "paths": ["src/types/"]},
                      {"name": "service", "paths": ["src/service/"]}],
            "file_size": {"exempt": [
                {"path": "src/gone.py",
                 "reason": "used to justify a file removed since"}]},
        }, indent=2) + "\n"),
    ),
    dict(
        gate="check_file_size.py",
        args=["--cap", "30"],
        why="an exemption naming a file this gate does not judge",
        needle="does not judge",
        plant=lambda t: (
            write(t, "assets/logo.svg", "<svg></svg>\n"),
            write(t, ".claude/guards.json", json.dumps({
                "protected_branches": ["main"],
                "layers": [{"name": "types", "paths": ["src/types/"]},
                          {"name": "service", "paths": ["src/service/"]}],
                "file_size": {"exempt": [
                    {"path": "assets/logo.svg",
                     "reason": "shrink target once split out"}]},
            }, indent=2) + "\n")),
    ),

    # --- negative controls ---------------------------------------------------
    # Each gate needs at least one of these, and coverage_gaps() below enforces
    # it. Without one, a gate that flagged *everything* would show a perfect row
    # of red-on-defect results and nobody would find out until it had cost
    # someone an afternoon. These plant the thing most easily mistaken for the
    # defect -- the documented exemption, the deliberate escape hatch -- so they
    # also pin those exemptions against silent removal.
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20"],
        why="a nested CLAUDE.md over the root cap is still not charged",
        needle=None,
        plant=lambda t: write(t, "src/api/CLAUDE.md",
                              "# api\n\n" + "".join(f"- rule {i}\n"
                                                    for i in range(1, 30))),
    ),
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20"],
        why="a scoped .claude/rules file over the root cap is not charged",
        # The escape hatch this gate exists to push work toward. Charging for a
        # scoped rule would push it straight back into CLAUDE.md, which is the
        # outcome the cap is trying to prevent.
        needle=None,
        plant=lambda t: write(t, ".claude/rules/api.md",
                              '---\npaths:\n  - "src/**"\n---\n\n'
                              + "".join(f"- rule {i}\n" for i in range(1, 30))),
    ),
    # Uncharged is not unbounded. The two cases above prove neither escape
    # hatch is billed on every turn; these two prove each still has a ceiling
    # of its own, because the cost of a three-hundred-line scoped rule did not
    # vanish when it left CLAUDE.md -- it moved from every turn to every
    # matching read, which is the worse of the two.
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20", "--nested-cap", "50"],
        why="a nested CLAUDE.md that has become a second root file",
        needle="second root file",
        plant=lambda t: write(t, "src/api/CLAUDE.md",
                              "# api\n\n" + "".join(f"- rule {i}\n"
                                                    for i in range(1, 80))),
    ),
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20", "--scoped-cap", "40"],
        why="a scoped rule longer than one file's worth of context",
        needle="scoped rule is longer",
        plant=lambda t: write(t, ".claude/rules/api.md",
                              '---\npaths:\n  - "src/**"\n---\n\n'
                              + "".join(f"- rule {i}\n" for i in range(1, 80))),
    ),
    dict(
        gate="check_context_budget.py",
        args=["--cap", "20"],
        why="maintainer notes in an HTML comment, far over the cap",
        # Block-level HTML comments are stripped before the content enters
        # context, so they are free. The cap charged for them, which failed a
        # file on lines that were never delivered to anyone.
        needle=None,
        # Enough real content to clear the "almost no content" assertion; the
        # point of the case is the 90 commented lines, not the size of the rest.
        plant=lambda t: write(t, "CLAUDE.md",
                              "# demo\n\nA repository.\n\n## Hard rules\n\n"
                              + "".join(f"{i}. rule -> docs/x.md\n"
                                        for i in range(1, 9))
                              + "\n<!--\n"
                              + "".join(f"note {i}\n" for i in range(1, 90))
                              + "-->\n"),
    ),
    dict(
        gate="check_docs_index.py",
        why="a document that declares why nothing routes to it",
        needle=None,
        plant=lambda t: write(t, "docs/reference/scratch.md",
                              "<!-- unrouted: a worked example kept for one "
                              "release, deliberately not in the table -->\n\n"
                              "# Scratch\n"),
    ),
    dict(
        gate="check_docs_index.py",
        # Pins the one hop. Without it every step file is unrouted, so the only
        # way to keep the gate green would be a routing row per step -- and the
        # table's job is answering "I am about to do X, what do I read", which
        # ten rows for one plan destroys. The green direction is where that
        # lives: nothing else here would notice the hop being removed.
        why="exec-plan steps reached through the README the index routes",
        needle=None,
        plant=lambda t: (
            write(t, "docs/index.md",
                  "# docs\n\n| I want to | Read | Edit |\n|---|---|---|\n"
                  "| a thing | [how](how-to/thing.md) | src/ |\n"
                  "| a plan | [plan](exec-plans/demo/README.md) | src/ |\n"),
            write(t, "docs/exec-plans/demo/README.md",
                  "# Demo plan\n\n- [ ] todo [first](steps/01-first.md)\n"
                  "- [ ] todo [second](steps/02-second.md)\n"),
            write(t, "docs/exec-plans/demo/steps/01-first.md", "# First\n"),
            write(t, "docs/exec-plans/demo/steps/02-second.md", "# Second\n")),
    ),
    dict(
        gate="check_docs_layout.py",
        # Pins the half of the rule that is easy to lose. Only the top level is
        # fixed; additions are legitimate once routed, which is how OpenStack's
        # conformers all carried project-specific directories alongside the
        # mandated ones. A gate that rejected every addition would be enforcing
        # a rule nobody agreed to, and would be switched off within a month.
        why="an added top-level directory that the index routes",
        needle=None,
        plant=lambda t: (
            write(t, "docs/index.md",
                  "# docs\n\n| I want to | Read | Edit |\n|---|---|---|\n"
                  "| a thing | [how](how-to/thing.md) | src/ |\n"
                  "| the shape of it | [arch](explanation/shape.md) | src/ |\n"),
            write(t, "docs/explanation/shape.md", "# Shape\n\nWhy it is so.\n")),
    ),
    dict(
        gate="check_layering.py",
        why="an import inside a single layer",
        needle=None,
        plant=lambda t: write(t, "src/service/other.py",
                              "from src.service.use import use\n\n"
                              "def other():\n    return use()\n"),
    ),
    dict(
        gate="check_hook_paths.py",
        # This is the real defect fixed at aafdc0113: every wired hook command
        # was a bare relative path, which only resolved when the session's cwd
        # happened to be the repository root. `python3 <missing>.py` exits 2,
        # the same code Claude Code reads as *block* -- so the failure is not
        # silence, it is every matching tool call refused with an unreadable
        # "can't open file".
        why="a hook command wired to a bare relative path",
        needle="resolves from one directory",
        plant=lambda t: write(t, ".claude/settings.json", json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command",
                 "command": "python3 shared/scripts/guards/dispatch.py"}]}]}},
            indent=2) + "\n"),
    ),
    dict(
        gate="check_hook_paths.py",
        # The near-miss the gate must not learn to flag: a shell one-liner
        # that names no script at all, only a bare command word and a
        # redirect target. Treating either as an unresolved path would make
        # this indistinguishable from a gate that fires on every hook.
        why="a shell one-liner naming no script, which must NOT be reported",
        needle=None,
        plant=lambda t: write(t, ".claude/settings.json", json.dumps({
            "hooks": {"SessionStart": [{"matcher": "*", "hooks": [
                {"type": "command",
                 "command": 'command -v jq >/dev/null || '
                            'echo "install jq: brew install jq" >&2'}]}]}},
            indent=2) + "\n"),
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


def coverage_gaps():
    """Every gate in this directory is covered in both directions.

    The cases above are a hand-written list, and for a long time that was the
    whole suite: adding `check_something.py` with no entry here left it untested
    while the run stayed green, which reads as evidence that it works.
    `guards/selftest.py` never had this hole -- it enumerates the directory and
    makes each guard declare its own cases -- and the asymmetry was not a
    decision, it was an oversight in the one file whose subject is exactly this.

    So enumerate, and require both directions per gate. One red case proves the
    gate can fire; one green case proves it does not fire on everything. A gate
    with only the first is indistinguishable from `exit 1`.
    """
    on_disk = {os.path.basename(p) for p in
               glob.glob(os.path.join(HERE, "check_*.py"))}
    red, green = defaultdict(int), defaultdict(int)
    for case in CASES:
        (green if case["needle"] is None else red)[case["gate"]] += 1

    gaps = []
    for gate in sorted(on_disk):
        if not red[gate] and not green[gate]:
            gaps.append(f"{gate}\n    has no cases at all — nothing here proves "
                        f"it works, and the suite stays green regardless")
        elif not red[gate]:
            gaps.append(f"{gate}\n    has no case that expects a failure — "
                        f"nobody has watched it turn red")
        elif not green[gate]:
            gaps.append(f"{gate}\n    has no case that must stay green — a gate "
                        f"that flagged everything would pass this suite")

    for gate in sorted(set(red) | set(green)):
        if gate not in on_disk:
            gaps.append(f"{gate}\n    has cases here but no such file in "
                        f"{os.path.relpath(HERE)} — a stale case tests nothing")
    return gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2

    failures = coverage_gaps()
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
