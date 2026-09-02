#!/usr/bin/env python3
"""What the pipeline runs, on what, how far it can be trusted, and what ships.

    python3 assess/pipeline.py [--root .] [--json]

Exit codes:
    0 = read    2 = cannot judge (no GitHub Actions workflows to read)

## What this is not

Dimension 2 injects defects and watches whether CI turns red. 3.1 asks whether
a change arrives with a test, 3.2 whether the check can be walked around.
Nothing here repeats any of that. Four things are read that none of them
touch, and each passes the test 0043 set -- *is there another way to get this
effect?* A workflow that runs on nothing, is checked by nothing, whose verdict
flips on a rerun, and which ships nothing traceable has not chosen a different
convention. It has those properties.

    scope      which changes run which checks, and which run none
    checked    whether the workflow files are themselves linted, audited or
               tested, and which steps refuse a pattern outright
    verdict    how often a rerun changed the verdict, from run history
    shipping   tags, what makes them, whether the latest is on this branch

## What is deliberately not read

Matrix breadth, caching, job count, reusable workflows, the runner image. A
repository that runs one job on one Python is not worse than one that runs
six; it is smaller. Scoring those is scoring resemblance -> 0020, 0043.

## GitHub Actions only, and it says so

`.gitlab-ci.yml`, Jenkinsfiles and the rest are found by the "CI runs the
suite" row and are not read here. Trigger and filter syntax differ per host,
and a reader that half-understands five of them reports confidently wrong
scope on four. Another host gets `cannot judge`, which is a fact about the
reader and is printed as one.

## The audit row is somebody else's tool

`zizmor` finds unpinned actions, `pull_request_target` checking out the head,
template injection -- and is better at it than anything written here would
be -> 0033. On PATH, its findings are counted by severity. Absent, the row
abstains rather than pretending the workflows are clean.

## What is handed over, not decided

A path filter is usually deliberate. A grep step that refuses a pattern is a
guard somebody wrote on purpose. A manifest one version ahead of its tag may be
a release in flight. Every one of those is a candidate with its evidence
attached, and the reading is the agent's -> 0043.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

WORKFLOWS = os.path.join(".github", "workflows")

_ON_BLOCK = re.compile(r"^on:[ \t]*(.*?)(?=^\S|\Z)", re.M | re.S)
_LIST_ITEM = re.compile(r"^\s*-\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$")
_INLINE_LIST = re.compile(r"\[(.*?)\]")

# A step that fails on a pattern reappearing: the CI-side twin of a guard.
# A recursive search inside a run block that also exits non-zero or emits
# a workflow error. Plain `grep` is excluded: an install step checking its
# own output is not a rule. Loose on purpose; every hit is handed over, not counted.
_SEARCH = re.compile(r"\bgrep\s+(-\w*r\w*|--recursive)\b|\brg\s|\bgit grep\b")
_REFUSE = re.compile(r"\bexit\s+[1-9]\b|::error::")

# Something a workflow does that leaves the repository. Each is a name a
# person would recognise in the row, not a proof that anything shipped.
_SHIPS = (
    ("gh release create", "a GitHub release"),
    ("softprops/action-gh-release", "a GitHub release"),
    ("ncipollo/release-action", "a GitHub release"),
    ("git/refs", "a tag, by API"),
    ("git push --tags", "a tag"),
    ("git push origin v", "a tag"),
    ("docker/build-push-action", "a container image"),
    ("docker push", "a container image"),
    ("pypa/gh-action-pypi-publish", "a PyPI package"),
    ("twine upload", "a PyPI package"),
    ("npm publish", "an npm package"),
    ("cargo publish", "a crate"),
    ("gem push", "a gem"),
    ("goreleaser", "release binaries"),
)

_SELF_CHECKS = (
    ("actionlint", "linted"),
    ("zizmor", "audited"),
)

_MANIFESTS = (
    (".claude-plugin/plugin.json", "json"),
    ("package.json", "json"),
    ("pyproject.toml", "toml"),
    ("Cargo.toml", "toml"),
)


def sh(args, cwd, timeout=60):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(args, 127, "", "not run")


# --------------------------------------------------------------------------
# reading a workflow file without a YAML library
# --------------------------------------------------------------------------

def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _block_after(lines, i):
    """Lines nested under lines[i], by indentation."""
    base = _indent(lines[i])
    out = []
    for line in lines[i + 1:]:
        if line.strip() and _indent(line) <= base:
            break
        out.append(line)
    return out


def _list_under(lines, i):
    """The list items under a `key:` line, inline or nested."""
    head = lines[i].split(":", 1)[1] if ":" in lines[i] else ""
    m = _INLINE_LIST.search(head)
    if m:
        return [x.strip().strip("'\"") for x in m.group(1).split(",")
                if x.strip()]
    out = []
    for line in _block_after(lines, i):
        m = _LIST_ITEM.match(line)
        if m:
            out.append(m.group(1).strip())
        elif line.strip():
            break
    return out


def _events(on_text):
    """{event: {"paths": [...], "paths-ignore": [...]}} from an `on:` block."""
    text = on_text.strip()
    events = {}
    if not text:
        return events
    if text.startswith("["):
        for name in _INLINE_LIST.search(text).group(1).split(","):
            if name.strip():
                events[name.strip().strip("'\"")] = {}
        return events
    if "\n" not in text and ":" not in text:
        events[text.strip("'\"")] = {}
        return events
    lines = on_text.splitlines()
    base = min((_indent(ln) for ln in lines if ln.strip()), default=0)
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() and _indent(line) == base and ":" in line \
                and not line.lstrip().startswith("-"):
            name = line.split(":", 1)[0].strip().strip("'\"")
            spec = {}
            body = _block_after(lines, i)
            for j, sub in enumerate(body):
                key = sub.split(":", 1)[0].strip()
                if key in ("paths", "paths-ignore") and _indent(sub) == \
                        min((_indent(b) for b in body if b.strip()),
                            default=0):
                    spec[key] = _list_under(body, j)
            events[name] = spec
        i += 1
    return events


def _steps(text):
    """(name, uses, run) per step, read loosely from the whole file."""
    lines = text.splitlines()
    steps, cur = [], None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("- ") and ("name:" in s or "uses:" in s or
                                    "run:" in s):
            cur = {"line": i + 1, "name": "", "uses": "", "run": ""}
            steps.append(cur)
            s = s[2:]
        if cur is None:
            continue
        if s.startswith("name:"):
            cur["name"] = s[5:].strip().strip("'\"")
        elif s.startswith("uses:"):
            cur["uses"] = s[5:].strip().strip("'\"")
        elif s.startswith("run:"):
            body = s[4:].strip()
            if body in ("|", ">", "|-", ">-"):
                body = "\n".join(_block_after(lines, i))
            cur["run"] = body
    return steps


def workflows(root):
    where = os.path.join(root, WORKFLOWS)
    if not os.path.isdir(where):
        return []
    out = []
    for name in sorted(os.listdir(where)):
        if not name.endswith((".yml", ".yaml")):
            continue
        try:
            with open(os.path.join(where, name), encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        m = _ON_BLOCK.search(text)
        events = _events(m.group(1)) if m else {}
        steps = _steps(text)
        out.append({
            "file": WORKFLOWS.replace(os.sep, "/") + "/" + name,
            "events": events,
            "steps": steps,
            "job_filter": "paths-filter" in text,
            "text": text,
        })
    return out


# --------------------------------------------------------------------------
# scope: which changes run which checks
# --------------------------------------------------------------------------

def _matches_self(pattern, file):
    p = pattern.strip()
    if p.startswith("!"):
        return False
    if p in (file, ".github/**", ".github/workflows/**",
             ".github/workflows/*", ".github/workflows/*.yml", "**"):
        return True
    return p.rstrip("*/") and file.startswith(p.rstrip("*/"))


def scope(flows):
    on_pr = [f for f in flows if "pull_request" in f["events"]
             or "pull_request_target" in f["events"]]
    unconditional, filtered, self_blind = [], [], []
    for f in on_pr:
        spec = f["events"].get("pull_request") or \
            f["events"].get("pull_request_target") or {}
        paths, ignore = spec.get("paths") or [], spec.get("paths-ignore") or []
        if not paths and not ignore:
            unconditional.append(f["file"])
            continue
        filtered.append({"file": f["file"], "paths": paths,
                         "paths-ignore": ignore})
        if paths and not any(_matches_self(p, f["file"]) for p in paths):
            self_blind.append(f["file"])
    return {
        "on_pull_request": [f["file"] for f in on_pr],
        "unconditional": unconditional,
        "filtered": filtered,
        "self_blind": self_blind,
        "job_filters": [f["file"] for f in on_pr if f["job_filter"]],
    }


# --------------------------------------------------------------------------
# checked: is the pipeline itself under test
# --------------------------------------------------------------------------

def checked(flows):
    present, refusing = {}, []
    for f in flows:
        low = f["text"].lower()
        for needle, what in _SELF_CHECKS:
            if needle in low:
                present[what] = f["file"]
        for s in f["steps"]:
            run = s["run"]
            if not run:
                continue
            if ".github/" in run or "--self-test" in run or \
                    "--selftest" in run:
                present.setdefault("tested", f["file"])
            if _SEARCH.search(run) and _REFUSE.search(run):
                refusing.append({"file": f["file"], "line": s["line"],
                                 "name": s["name"] or run.splitlines()[0][:60]})
    return {"present": present, "refusing": refusing}


# --------------------------------------------------------------------------
# audit: zizmor, when it is here
# --------------------------------------------------------------------------

def interpret_audit(text):
    """Counts by severity from zizmor's JSON. Tolerant of both the flat and
    the nested shape, because the tool's output has moved between them."""
    try:
        findings = json.loads(text or "[]")
    except ValueError:
        return None
    if not isinstance(findings, list):
        return None
    by, idents = {}, []
    for f in findings:
        if not isinstance(f, dict):
            continue
        det = f.get("determinations") or {}
        sev = str(det.get("severity") or f.get("severity") or "unknown").lower()
        by[sev] = by.get(sev, 0) + 1
        ident = f.get("ident") or ""
        if ident and ident not in idents:
            idents.append(ident)
    return {"total": len(findings), "by_severity": by, "idents": idents[:6]}


def audit(root, tool=None):
    tool = tool if tool is not None else shutil.which("zizmor")
    if not tool:
        return None, "zizmor is not on PATH"
    r = sh([tool, "--format", "json", "--no-progress",
            os.path.join(root, WORKFLOWS)], root, 120)
    if r.returncode not in (0, 13, 14):
        # 0 = clean, 13/14 = findings at or above the threshold. Anything
        # else is the tool failing, which is not a finding about the tree.
        return None, "zizmor could not read the workflows: " + \
            (r.stderr or "").strip()[:120]
    out = interpret_audit(r.stdout)
    if out is None:
        return None, "zizmor's output was not the JSON this reader expects"
    return out, ""


# --------------------------------------------------------------------------
# verdict: reruns that changed the answer
# --------------------------------------------------------------------------

def _dur(a, b):
    try:
        t0 = datetime.datetime.fromisoformat((a or "").replace("Z", "+00:00"))
        t1 = datetime.datetime.fromisoformat((b or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    d = (t1 - t0).total_seconds()
    return d if d > 0 else None


def verdicts(root, fetch=None):
    """From run history: how many runs were rerun, how many of those changed
    conclusion between the first attempt and the last, and the median time
    to a verdict. `fetch` is injectable so the reading can be tested without
    a remote; by default it is `gh api`.

    A rerun is somebody pressing the button on an unchanged commit, which is
    almost always a red they did not believe. When the rerun goes green,
    the verdict depended on something other than the code -- flakiness by
    definition, measured rather than felt."""
    if fetch is None:
        if shutil.which("gh") is None:
            return None, "gh is not on PATH"

        def fetch(path):
            r = sh(["gh", "api", path], root, 60)
            return r.stdout if r.returncode == 0 else None

    body = fetch("repos/{owner}/{repo}/actions/runs?per_page=60")
    if body is None:
        return None, "run history is not readable: no remote, no gh, or no auth"
    try:
        runs = (json.loads(body) or {}).get("workflow_runs") or []
    except ValueError:
        return None, "run history came back unreadable"
    done = [r for r in runs if r.get("status") == "completed"
            and r.get("conclusion") in ("success", "failure")]
    if not done:
        return None, "no completed run to read"
    secs = sorted(d for d in (_dur(r.get("run_started_at"),
                                   r.get("updated_at")) for r in done) if d)
    reruns = [r for r in done if (r.get("run_attempt") or 1) > 1]
    flipped = []
    for r in reruns[:10]:
        first = fetch("repos/{owner}/{repo}/actions/runs/%s/attempts/1"
                      % r.get("id"))
        if first is None:
            continue
        try:
            c1 = (json.loads(first) or {}).get("conclusion")
        except ValueError:
            continue
        if c1 and c1 != r.get("conclusion"):
            flipped.append({"run": r.get("id"), "name": r.get("name"),
                            "first": c1, "last": r.get("conclusion"),
                            "sha": (r.get("head_sha") or "")[:10]})
    return {"runs": len(done), "reruns": len(reruns),
            "reruns_read": min(len(reruns), 10), "flipped": flipped,
            "median_seconds": secs[len(secs) // 2] if secs else None}, ""


# --------------------------------------------------------------------------
# shipping: tags, what makes them, whether the latest is on this branch
# --------------------------------------------------------------------------

def _manifest_version(root):
    for rel, kind in _MANIFESTS:
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                text = fh.read(200000)
        except OSError:
            continue
        if kind == "json":
            try:
                v = json.loads(text).get("version")
            except (ValueError, AttributeError):
                v = None
        else:
            m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
            v = m.group(1) if m else None
        if v:
            return rel, str(v)
    return None, None


def shipping(root, flows):
    tags = sh(["git", "for-each-ref", "--sort=-creatordate",
               "--format=%(refname:short) %(objectname) %(*objectname)",
               "refs/tags"], root)
    lines = [ln for ln in (tags.stdout or "").splitlines() if ln.strip()]
    latest, latest_sha = "", ""
    if lines:
        parts = lines[0].split()
        # An annotated tag lists the tag object first and the commit it
        # points at second; a lightweight tag has only the commit.
        latest, latest_sha = parts[0], (parts[2] if len(parts) > 2 else parts[1])
    reachable = None
    if latest:
        reachable = sh(["git", "merge-base", "--is-ancestor", latest_sha,
                        "HEAD"], root).returncode == 0
    makers = []
    for f in flows:
        ev = f["events"]
        low = f["text"].lower()
        trig = []
        if "release" in ev:
            trig.append("on release")
        if "tags" in json.dumps(ev.get("push") or {}) or \
                re.search(r"^\s+tags:\s*$|^\s+tags:\s*\[", f["text"], re.M):
            trig.append("on tag")
        what = sorted({w for needle, w in _SHIPS if needle in low})
        if what or trig:
            makers.append({"file": f["file"], "what": what, "trigger": trig})
    m_file, m_version = _manifest_version(root)
    tag_version = re.sub(r"^[^0-9]*", "", latest) if latest else ""
    return {
        "tags": len(lines),
        "latest": latest, "latest_sha": latest_sha[:10],
        "latest_reachable": reachable,
        "makers": makers,
        "manifest": m_file, "manifest_version": m_version,
        "tag_version": tag_version,
    }


# --------------------------------------------------------------------------

def assess(root, fetch=None, audit_tool=None):
    flows = workflows(root)
    if not flows:
        return None, ("cannot judge: no GitHub Actions workflows — other hosts "
                      "are not read here, and a repository with no pipeline "
                      "is already reported by the CI row above")
    a, a_why = audit(root, audit_tool)
    v, v_why = verdicts(root, fetch)
    return {
        "files": [f["file"] for f in flows],
        "scope": scope(flows),
        "checked": checked(flows),
        "audit": a, "audit_why": a_why,
        "verdicts": v, "verdicts_why": v_why,
        "shipping": shipping(root, flows),
    }, ""


def render(r):
    if not r:
        return "pipeline: could not judge\n"
    s, c, sh_ = r["scope"], r["checked"], r["shipping"]
    out = ["pipeline  %d workflow(s)" % len(r["files"])]
    out.append("  scope      %d unconditional on pull requests, %d filtered%s"
               % (len(s["unconditional"]), len(s["filtered"]),
                  ", %d blind to their own change" % len(s["self_blind"])
                  if s["self_blind"] else ""))
    out.append("  checked    %s" % (", ".join(sorted(c["present"])) or
                                    "by nothing"))
    if c["refusing"]:
        out.append("  refusing   %d step(s) fail on a pattern" %
                   len(c["refusing"]))
    if r["audit"]:
        out.append("  audit      %d finding(s) %s" % (
            r["audit"]["total"], json.dumps(r["audit"]["by_severity"])))
    else:
        out.append("  audit      not run: " + r["audit_why"])
    if r["verdicts"]:
        v = r["verdicts"]
        out.append("  verdicts   %d run(s), %d rerun, %d flipped" %
                   (v["runs"], v["reruns"], len(v["flipped"])))
    else:
        out.append("  verdicts   not readable: " + r["verdicts_why"])
    out.append("  shipping   %d tag(s)%s%s" % (
        sh_["tags"],
        ", latest %s %s" % (sh_["latest"], "on this branch" if
                            sh_["latest_reachable"] else "NOT on this branch")
        if sh_["latest"] else "",
        "; made by " + ", ".join(m["file"] for m in sh_["makers"])
        if sh_["makers"] else ""))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r, why = assess(os.path.abspath(a.root))
    if r is None:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2, default=str))
    else:
        print(render(r), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
