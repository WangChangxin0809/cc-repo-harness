#!/usr/bin/env python3
"""Whether an agent can watch its own change run.

    python3 assess/observe.py [--root .] [--json OUT]
    python3 assess/observe.py --brief RUN.json
    python3 assess/observe.py --grade RUN.json --answers ANSWERS.json

Exit codes:
    0 = the evidence was collected, or the answers were graded
    2 = cannot judge (nothing readable in the tree)

## The denominator of `same-turn`

Dimension 2's ladder has a rung between the hook that fires before a write and
the test suite: the same turn, after the edit, before anything is committed.
Almost every repository reads `same-turn: none wired` there, and the reading is
usually taken to mean *no PostToolUse hook*. That is not the whole of it.

The other way a defect dies in the same turn has nothing to do with hooks: the
agent runs what it just changed and looks at the result. Start the service,
hit the endpoint, read the log line, open the page. Nothing in a repository
*makes* an agent do that, but a repository can make it impossible, and most do
without noticing.

So this is a denominator, and it is the same shape as coverage -- 0031's
argument, moved one rung up:

* Coverage and `local-suite`: covered does not mean caught, **uncovered means
  never caught**.
* Observability and `same-turn`: readable output does not mean the agent will
  look, **unreadable output means it cannot**.

Both are one-directional. A guarantee, not a correlation. That is the only
reason either of them is on the page, because in the direction people usually
read them, neither predicts much.

## What a machine may decide here, which is very little

Nothing here is scored, and the reason is worth stating plainly. "Can an agent
verify its own output in this repository" is a question about a whole
workflow -- whether the thing starts, whether starting it twice collides,
whether what comes out is text an agent can read or a dashboard it cannot
reach, whether the page it renders can be looked at. A machine reading a tree
can find the *pieces* and cannot judge whether they add up.

What it can do is stop the agent from reading the whole repository to find
them. It collects six kinds of evidence and hands them over already sorted,
which is a far better question than *is this repo observable*.

## The six angles

| angle | the question behind it |
|---|---|
| `run` | can the thing be started at all, by a command in the tree |
| `isolation` | can two of it run at once, or does the second collide |
| `logs` | does what it emits land somewhere an agent can read |
| `surface` | is there a thing a user sees, and is it reachable |
| `drive` | is there a way to make it do something and observe the result |
| `teardown` | can an instance be disposed of, or does it accumulate |

`isolation` and `teardown` look like operational nitpicks and are not. An
agent working in a worktree while six others do the same needs its own
instance; a repository that hard-codes one port and one database name gives
the second agent a crash that looks like a bug in its change. That is worse
than no observability, because it is observability that lies.

## What this deliberately does not do

**It does not run anything.** No service is started, no port is bound, no
container comes up. Everything here is read off the tree. Starting a stranger's
application is a different and much larger promise than this assessment makes
anywhere else, and 0026's pre-flight contract exists precisely so that nothing
executes without having been named first.

**It does not fix, suggest wiring, or write files.** Hard rule 4: a diagnostic
that starts fixing what it finds has stopped being a diagnostic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SKIP_DIRS = (".git", "node_modules", "vendor", "venv", ".venv", "dist",
             "build", "target", "__pycache__", ".mypy_cache", ".pytest_cache",
             ".tox", ".next", ".cache", "coverage", "htmlcov")

# Reading a stranger's repository has no natural bound, and an assessment that
# takes minutes to collect evidence nobody reads is worse than one that misses
# a signal. Both caps are generous for the shape of repository this measures
# and are reported when they bite, so a truncated scan is never silently a
# clean one.
MAX_FILES = 4000
MAX_BYTES = 400_000

ANGLES = ("run", "isolation", "logs", "surface", "drive", "teardown")


def _read(path, limit=MAX_BYTES):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _walk(root):
    """Every file worth reading, and whether the walk was cut short.

    The instrument's own directory is excluded when it happens to sit inside
    the subject. Every collector below is a list of the names it looks for, so
    a scan that reads this file finds `grafana`, `jaeger` and `playwright` in
    a repository that has none of them -- an instrument that measures itself
    reports its own vocabulary as the subject's."""
    out, truncated = [], False
    mine = os.path.realpath(HERE)
    for base, dirs, names in os.walk(root):
        if os.path.realpath(base).startswith(mine):
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not d.startswith("."))
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(base, name), root)
            out.append(rel.replace(os.sep, "/"))
            if len(out) >= MAX_FILES:
                return out, True
    return out, truncated


def _found(kind, where, detail):
    return {"kind": kind, "where": where, "detail": detail}


# --- run ------------------------------------------------------------------
# A target whose name is a verb about starting something. Deliberately not
# `test`: this dimension is about the rung the test suite is not on.
START = re.compile(r"^(run|dev|start|serve|server|up|watch|preview|launch"
                   r"|debug)([-_:.][\w-]+)?$")
_MAKE_TARGET = re.compile(r"^([A-Za-z][\w./-]*)\s*:(?!=)")
_JUST_RECIPE = re.compile(r"^([a-z][\w-]*)\s*(\([^)]*\))?\s*:")


def _run_ways(root, files):
    out = []
    for rel in files:
        low = rel.lower()
        base = os.path.basename(low)
        full = os.path.join(root, rel)
        if base in ("makefile", "gnumakefile"):
            for line in _read(full).splitlines():
                m = _MAKE_TARGET.match(line)
                if m and START.match(m.group(1).lower()):
                    out.append(_found("make", rel, f"make {m.group(1)}"))
        elif base == "justfile":
            for line in _read(full).splitlines():
                m = _JUST_RECIPE.match(line)
                if m and START.match(m.group(1)):
                    out.append(_found("just", rel, f"just {m.group(1)}"))
        elif base == "package.json":
            try:
                scripts = json.loads(_read(full)).get("scripts") or {}
            except ValueError:
                scripts = {}
            for key in sorted(scripts):
                if START.match(key.lower()):
                    out.append(_found("npm", rel, f"npm run {key}"))
        elif base in ("docker-compose.yml", "docker-compose.yaml",
                      "compose.yml", "compose.yaml"):
            out.append(_found("compose", rel, "docker compose up"))
        elif base == "procfile":
            out.append(_found("procfile", rel, "a process table"))
        elif base in ("main.py", "app.py", "manage.py", "server.py",
                      "wsgi.py", "asgi.py", "__main__.py") and "/" not in rel:
            out.append(_found("entry", rel, f"python3 {rel}"))
        elif base.endswith(".sh") and START.match(base[:-3]):
            out.append(_found("script", rel, f"./{rel}"))
        elif low.endswith("cmd/main.go") or low == "main.go":
            out.append(_found("entry", rel, "go run ."))
        elif base == "pyproject.toml":
            # A console script is a way to run the thing even though nothing
            # here looks like a service. The first version of this collector
            # only knew application shapes -- a Makefile, a compose file, a
            # top-level app.py -- and read `run: 0` on a repository whose every
            # file is executable from a shell.
            text = _read(full)
            for section in ("[project.scripts]", "[tool.poetry.scripts]"):
                if section in text:
                    body = text.split(section, 1)[1].split("\n[", 1)[0]
                    for line in body.splitlines():
                        name = line.split("=")[0].strip().strip('"\'')
                        if name and not name.startswith("#"):
                            out.append(_found("console", rel, name))
    out.extend(_runnable_modules(root, files))
    return out


_MAIN_GUARD = re.compile(r'^if\s+__name__\s*==\s*[\'"]__main__[\'"]', re.M)


def _runnable_modules(root, files):
    """Files that say, in the language's own words, that they can be run.

    This is the general form of the entry-point list above, and it is the one
    that catches repositories which are not applications at all: a tool, a
    library with a CLI, a directory of scripts. An agent working in one of
    those can watch its change run by running the file it changed."""
    out = []
    for rel in files:
        if not rel.endswith(".py"):
            continue
        if _MAIN_GUARD.search(_read(os.path.join(root, rel), 40_000)):
            out.append(_found("module", rel, "python3 " + rel))
        if len(out) >= 30:
            out.append(_found("module", "", "...and more"))
            break
    return out


# --- isolation ------------------------------------------------------------
# The question is not "is a port configured" but "does the second instance get
# a different one". An env lookup with a default is the shape that survives
# two agents; a bare literal is the shape that does not.
_PORT_ENV = re.compile(r"(PORT|port)\s*[=:]\s*(os\.environ|os\.getenv"
                       r"|process\.env|env\.|ENV\[|getenv|\$\{?[A-Z_]*PORT)")
_PORT_LITERAL = re.compile(r"^\s*-?\s*[\"']?(\d{2,5}):(\d{2,5})[\"']?\s*$")
_CONTAINER_NAME = re.compile(r"^\s*container_name\s*:\s*(\S+)")


def _isolation(root, files):
    out = []
    for rel in files:
        base = os.path.basename(rel).lower()
        if base not in ("docker-compose.yml", "docker-compose.yaml",
                        "compose.yml", "compose.yaml", ".env", ".env.example",
                        ".env.sample"):
            continue
        text = _read(os.path.join(root, rel))
        for line in text.splitlines():
            m = _PORT_LITERAL.match(line)
            if m:
                out.append(_found("fixed-port", rel,
                                  f"host port {m.group(1)} is a literal"))
            m = _CONTAINER_NAME.match(line)
            if m and "$" not in m.group(1):
                out.append(_found("fixed-name", rel,
                                  f"container_name {m.group(1)} is a literal"))
        if _PORT_ENV.search(text):
            out.append(_found("port-from-env", rel,
                              "the port comes from the environment"))
    for rel in files:
        if not rel.endswith((".py", ".js", ".ts", ".go", ".rb", ".rs")):
            continue
        text = _read(os.path.join(root, rel), 60_000)
        if _PORT_ENV.search(text):
            out.append(_found("port-from-env", rel,
                              "the port comes from the environment"))
            if len([o for o in out if o["kind"] == "port-from-env"]) > 8:
                break
    return out


# --- logs -----------------------------------------------------------------
# What matters is not that logging exists but that the output is something an
# agent can get at: a stream it can capture, a file it can read, structured
# text it can query. A hosted dashboard is the case this row exists to catch,
# because it looks like excellent observability and the agent cannot see it.
# Prose is not configuration. A design document that discusses a logging stack
# is evidence about what somebody wrote down, not about what the application
# emits, and counting it puts a repository's ambitions on the page as its
# capabilities.
CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".rs", ".java",
            ".kt", ".cs", ".php", ".ex", ".exs", ".scala", ".sh")
CONFIG_EXT = (".json", ".toml", ".yml", ".yaml", ".ini", ".cfg", ".xml",
              ".properties", ".env", ".conf")

LOGGERS = {
    "logging.basicConfig": "python stdlib logging",
    "logging.config": "python stdlib logging, configured",
    "structlog": "structlog (structured)",
    "winston": "winston",
    "pino": "pino (structured)",
    "log/slog": "go slog (structured)",
    "logback": "logback",
    "log4j": "log4j",
    "tracing_subscriber": "rust tracing",
    "env_logger": "rust env_logger",
}
TELEMETRY = ("opentelemetry", "otel", "prometheus_client", "prom-client",
             "victoria", "vector.toml", "jaeger", "grafana", "loki")
_JSON_LOG = re.compile(r"json.?formatter|JsonFormatter|format:\s*[\"']json"
                       r"|jsonlogger|json_logs", re.I)


def _logs(root, files):
    out, seen = [], set()
    for rel in files:
        if not rel.endswith(CODE_EXT + CONFIG_EXT):
            continue
        text = _read(os.path.join(root, rel), 60_000)
        if not text:
            continue
        for needle, label in LOGGERS.items():
            if needle in text and label not in seen:
                seen.add(label)
                out.append(_found("logger", rel, label))
        low = text.lower()
        for needle in TELEMETRY:
            if needle in low and needle not in seen:
                seen.add(needle)
                out.append(_found("telemetry", rel, needle))
        if _JSON_LOG.search(text) and "structured" not in seen:
            seen.add("structured")
            out.append(_found("structured", rel, "logs are emitted as JSON"))
    for rel in files:
        top = rel.split("/")[0]
        if top in ("logs", "log", "var") and "logdir" not in seen:
            seen.add("logdir")
            out.append(_found("logdir", top, "output lands in the tree"))
    return out


# --- surface --------------------------------------------------------------
UI_EXT = (".html", ".jsx", ".tsx", ".vue", ".svelte", ".astro")
_ENDPOINT = re.compile(r"[\"'](/(?:health[a-z]*|readyz|livez|metrics|status|"
                       r"debug|__debug__)[\w/]*)[\"']")
SPECS = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json",
         "swagger.yaml", "schema.graphql")


def _surface(root, files):
    out, ui, seen = [], 0, set()
    for rel in files:
        base = os.path.basename(rel).lower()
        if rel.endswith(UI_EXT):
            ui += 1
        if base in SPECS:
            out.append(_found("spec", rel, "an interface description"))
        if rel.endswith((".py", ".js", ".ts", ".go", ".rb", ".rs")):
            for m in _ENDPOINT.finditer(_read(os.path.join(root, rel), 60_000)):
                path = m.group(1)
                if path not in seen:
                    seen.add(path)
                    out.append(_found("endpoint", rel, path))
    if ui:
        out.append(_found("ui", "", f"{ui} file(s) render something a person sees"))
    return out


# --- drive ----------------------------------------------------------------
# Tools that let something make the application do a thing and then look at
# what it did. A browser driver is the strongest signal here and the rarest.
DRIVERS = {
    "playwright": "playwright (browser)",
    "puppeteer": "puppeteer (browser)",
    "selenium": "selenium (browser)",
    "cypress": "cypress (browser)",
    "chrome-devtools": "chrome devtools protocol",
    "webdriver": "webdriver",
    "httpx": "an http client",
    "requests": "an http client",
    "supertest": "an http client",
}
DEP_FILES = ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
             "go.mod", "Gemfile", "pom.xml", "build.gradle", ".mcp.json")


def _drive(root, files):
    out, seen = [], set()
    for rel in files:
        base = os.path.basename(rel)
        if base not in DEP_FILES and base != ".mcp.json":
            continue
        text = _read(os.path.join(root, rel)).lower()
        for needle, label in DRIVERS.items():
            if needle in text and label not in seen:
                seen.add(label)
                out.append(_found("driver", rel, label))
    for rel in files:
        if os.path.basename(rel) == ".mcp.json":
            try:
                servers = json.loads(_read(os.path.join(root, rel)))
            except ValueError:
                continue
            for name in sorted((servers.get("mcpServers") or {})):
                out.append(_found("mcp", rel, f"MCP server: {name}"))
    return out


# --- teardown -------------------------------------------------------------
_TEARDOWN = (("docker compose down", "compose brings itself down"),
             ("docker-compose down", "compose brings itself down"),
             ("--rm", "containers are removed on exit"),
             ("trap ", "a shell trap cleans up"),
             ("mkdtemp", "instances live in a temporary directory"),
             ("TemporaryDirectory", "instances live in a temporary directory"),
             ("git worktree", "work happens in a worktree"))


def _teardown(root, files):
    out, seen = [], set()
    for rel in files:
        if not rel.endswith((".sh", ".py", ".yml", ".yaml", ".mk", ".just")) \
                and os.path.basename(rel).lower() not in ("makefile", "justfile"):
            continue
        text = _read(os.path.join(root, rel), 60_000)
        for needle, label in _TEARDOWN:
            if needle in text and label not in seen:
                seen.add(label)
                out.append(_found("teardown", rel, label))
    return out


COLLECTORS = {"run": _run_ways, "isolation": _isolation, "logs": _logs,
              "surface": _surface, "drive": _drive, "teardown": _teardown}


def assess(root):
    """Evidence for each angle, and nothing resembling a verdict."""
    files, truncated = _walk(root)
    if not files:
        return None, "cannot judge: nothing readable under the root"
    out = {"files_scanned": len(files), "truncated": truncated}
    for angle in ANGLES:
        out[angle] = COLLECTORS[angle](root, files)
    return out, ""


BRIEF = """\
# Can an agent watch its own change run in this repository?

Below is every piece of evidence a machine could find in the tree, sorted into
six angles. It was collected by reading files only — **nothing was started, no
port was bound, no container came up** — so the evidence is about what the
repository *offers*, and the judgement about whether it adds up is yours.

## Why the question matters

Dimension 2 measures how late a defect is caught, on a ladder whose third rung
is the local test suite. The rung above it is the same turn: the agent made an
edit and has not committed yet. A defect dies there in one of two ways — a
hook refuses it, or **the agent runs what it changed and sees that it is
wrong**. This assessment can measure the first. Only you can judge the second,
and the inference runs one way: output an agent can read does not mean the
agent will look, but output it cannot reach means it cannot look, ever.

## What to answer

**`verdict`** — one of:

| | meaning |
|---|---|
| `yes` | an agent that just made a change could start this, exercise it, and read the result, using what is in the tree |
| `partly` | it could see some of what it changed; name what is out of reach |
| `no` | it could not verify its own output by running anything |

**`prose`** — two to five sentences, **printed on the page verbatim**. Write
what a person needs in order to act: what an agent can and cannot see here,
and what is missing. Do not restate the evidence list; the reader has it. Do
not recommend a product. If the answer is `yes`, say what makes it work, so
somebody can avoid breaking it.

## Angles, and what would make each one a `no`

* **run** — no command in the tree starts the thing. An agent can compile it
  and never observe it.
* **isolation** — it starts, but a literal port or a fixed container name means
  the second concurrent instance collides. Worse than nothing: the second agent
  gets a crash that looks like a bug in its own change.
* **logs** — it emits nothing an agent can capture, or everything goes to a
  hosted dashboard the agent has no way to reach. A dashboard reads as
  excellent observability and is invisible from inside a session.
* **surface** — there is something a person sees and no way to look at it.
* **drive** — nothing can make it do a thing on demand: no http client, no
  browser driver, no exercise script.
* **teardown** — instances accumulate. Over a long session this becomes the
  reason the next run fails.

Absence of evidence under an angle is not proof of absence — say so rather
than scoring it down, if you find the reason elsewhere in the repository.

## Evidence
"""

ANSWER_SHAPE = """\

---

Answer as JSON:

    {"verdict": "yes|partly|no",
     "prose": "two to five sentences, printed verbatim",
     "angles": {"run": "one line", "...": "..."}}
"""


def brief(ev):
    """The question, with the evidence already sorted. One call, not six."""
    if not ev:
        return ""
    out = [BRIEF]
    for angle in ANGLES:
        items = ev.get(angle) or []
        out.append("\n### %s — %d found\n" % (angle, len(items)))
        if not items:
            out.append("\n*nothing found by the scan.*\n")
            continue
        for it in items[:40]:
            where = it["where"] or "(across the tree)"
            out.append("- `%s` — %s (%s)\n" % (where, it["detail"], it["kind"]))
        if len(items) > 40:
            out.append("- ...and %d more\n" % (len(items) - 40))
    if ev.get("truncated"):
        out.append("\n**The scan stopped at %d files.** Anything below that "
                   "is unscanned, not absent.\n" % MAX_FILES)
    out.append(ANSWER_SHAPE)
    return "".join(out)


VERDICTS = ("yes", "partly", "no")


def grade(answers):
    """What came back, or a reason it cannot be used. Never a default verdict.

    An unparseable or absent answer leaves the row pending. Supplying a verdict
    here when nobody gave one would put words on the page that no judge said,
    which is the one failure mode this whole two-pass shape exists to avoid."""
    if not isinstance(answers, dict):
        return None, "the answers are not a JSON object"
    verdict = str(answers.get("verdict", "")).strip().lower()
    if verdict not in VERDICTS:
        return None, "verdict must be one of: " + ", ".join(VERDICTS)
    prose = str(answers.get("prose", "")).strip()
    if not prose:
        return None, "the verdict came with no prose, and the page prints prose"
    angles = answers.get("angles")
    if not isinstance(angles, dict):
        angles = {}
    return {"verdict": verdict, "prose": prose,
            "angles": {k: str(v) for k, v in angles.items() if k in ANGLES}}, ""


def render(ev, judged=None):
    lines = []
    if not ev:
        return "observability: could not judge\n"
    for angle in ANGLES:
        items = ev.get(angle) or []
        head = "  %-10s %d" % (angle, len(items))
        if items:
            head += "  " + "; ".join(sorted({i["detail"] for i in items}))[:90]
        lines.append(head)
    if judged:
        lines.append("  verdict    " + judged["verdict"])
        lines.append("  " + judged["prose"])
    else:
        lines.append("  verdict    not yet judged")
    return "can an agent watch its own change run?\n" + "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    ap.add_argument("--brief", default="",
                    help="a run's JSON; writes the question for the agent")
    ap.add_argument("--grade", default="", help="a run's JSON")
    ap.add_argument("--answers", default="", help="what the agent answered")
    a = ap.parse_args()

    if a.brief:
        with open(a.brief, encoding="utf-8") as fh:
            run = json.load(fh)
        ev = run.get("observe") if "observe" in run else run
        text = brief(ev)
        if not text:
            print("cannot judge: no evidence in that run", file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if a.grade:
        if not a.answers:
            print("cannot judge: --grade needs --answers", file=sys.stderr)
            return 2
        with open(a.answers, encoding="utf-8") as fh:
            judged, why = grade(json.load(fh))
        if not judged:
            print("cannot judge: " + why, file=sys.stderr)
            return 2
        sys.stdout.write(json.dumps(judged, indent=2) + "\n")
        return 0

    ev, why = assess(os.path.abspath(a.root))
    if not ev:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(ev, fh, indent=1)
    sys.stdout.write(render(ev))
    return 0


if __name__ == "__main__":
    sys.exit(main())
