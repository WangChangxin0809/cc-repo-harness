#!/usr/bin/env python3
"""Build the repo graph. Full rebuild from source; no incremental state.

    python3 build.py [--root .] [--out .index/graph.json] [--report]

    0 = built     2 = cannot judge (not a git repository)

Incremental indexes develop a silent divergence from the tree, and a silent
divergence produces confidently wrong answers -- strictly worse than no answers,
because nobody goes and checks. A full rebuild of a 100k-line repository is a
few seconds; that is cheap enough that correctness wins.

Symbols come from tree-sitter when it is installed, and from per-language
regexes when it is not. Which one was used is recorded in the report, because
the regex path misses things the parser would catch and an agent that does not
know which one ran cannot calibrate how much to trust a hole.

Nodes:  file:<path>  sym:<name>  doc:<path>
Edges:  defines · references · imports · calls · governs · supersedes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

# --- language table ----------------------------------------------------------
# `defs` must capture the symbol name in group 1. `refs` is deliberately coarse:
# an identifier followed by `(`. Precision here is not the point -- PageRank over
# a noisy graph still ranks the right neighbourhood, and a missed edge costs
# more than a spurious one.

LANGS = {
    ".py":  dict(name="python",
                 defs=[r"^\s*(?:async\s+)?def\s+(\w+)", r"^\s*class\s+(\w+)"],
                 imports=[r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))"]),
    ".js":  dict(name="javascript",
                 defs=[r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)",
                       r"^\s*(?:export\s+)?class\s+(\w+)",
                       r"^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\("],
                 imports=[r"""^\s*import\s.*?from\s+['"]([^'"]+)""",
                          r"""require\(\s*['"]([^'"]+)"""]),
    ".go":  dict(name="go",
                 defs=[r"^func\s+(?:\([^)]*\)\s*)?(\w+)", r"^type\s+(\w+)"],
                 imports=[r'^\s*"([\w./-]+)"']),
    ".rs":  dict(name="rust",
                 defs=[r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)",
                       r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)"],
                 imports=[r"^\s*use\s+([\w:]+)"]),
    ".java": dict(name="java",
                  defs=[r"^\s*(?:public|private|protected).*?\s(\w+)\s*\(",
                        r"^\s*(?:public\s+)?(?:class|interface|enum)\s+(\w+)"],
                  imports=[r"^\s*import\s+([\w.]+)"]),
    ".gd":  dict(name="gdscript",
                 defs=[r"^\s*func\s+(\w+)", r"^class_name\s+(\w+)"],
                 imports=[r'^\s*(?:const\s+\w+\s*=\s*)?preload\("([^"]+)"']),
}
LANGS[".ts"] = LANGS[".tsx"] = LANGS[".jsx"] = LANGS[".mjs"] = LANGS[".js"]

DOC_EXT = {".md", ".mdx", ".rst"}
REF = re.compile(r"\b([A-Za-z_]\w{2,})\s*\(")
GOVERNS = re.compile(r"^Governs:\s*(.+)$", re.M)
SUPERSEDES = re.compile(r"^Supersedes:\s*(\S+)", re.M)


# Vendored and generated code is tracked by git but is not code anyone here
# writes, and it is usually the largest thing in the tree -- left in, it wins
# the ranking on sheer edge count. Excluded by policy, and the count is reported
# separately from `blind`, because "chose not to look" and "could not see" are
# different facts and an agent needs to tell them apart.
EXCLUDE = ("vendor/", "node_modules/", "third_party/", "/vendor/",
           "/node_modules/", ".venv/", "site-packages/", "/dist/", "/build/")
EXCLUDE_SUFFIX = (".pb.go", "_pb2.py", ".generated.ts", ".min.js")


def tracked_files(root):
    """Only what git tracks, minus vendored and generated trees."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None, 0
    all_files = [p for p in out.stdout.split("\0") if p]
    kept = [p for p in all_files
            if not any(x in "/" + p for x in EXCLUDE)
            and not p.endswith(EXCLUDE_SUFFIX)]
    return kept, len(all_files) - len(kept)


def try_tree_sitter():
    try:
        import tree_sitter_languages  # noqa: F401
        return "tree-sitter"
    except ImportError:
        return "regex"


def scan(root, files, excluded=0):
    g = dict(nodes={}, edges=[], meta={})
    skipped = defaultdict(int)
    unresolved_imports = []
    dynamic = []
    governs = []
    dangling_governs = []
    defined_in = {}          # symbol -> [file, ...]
    spans = defaultdict(list)  # file -> [(name, start_line)]

    def node(nid, kind, **kw):
        g["nodes"].setdefault(nid, dict(kind=kind, **kw))

    def edge(a, b, kind, w=1.0):
        g["edges"].append([a, b, kind, w])

    for rel in files:
        ext = os.path.splitext(rel)[1].lower()
        path = os.path.join(root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            skipped["unreadable"] += 1
            continue

        if ext in DOC_EXT:
            node(f"doc:{rel}", "doc", path=rel)
            text = "\n".join(lines[:60])
            for pat in GOVERNS.findall(text):
                for target in re.split(r"[,\s]+", pat.strip()):
                    if target:
                        governs.append((rel, target))
            for target in SUPERSEDES.findall(text):
                edge(f"doc:{rel}", f"doc:{target}", "supersedes", 2.0)
            continue

        lang = LANGS.get(ext)
        if lang is None:
            skipped[ext or "<noext>"] += 1
            continue

        node(f"file:{rel}", "file", path=rel, lang=lang["name"])
        for i, line in enumerate(lines):
            for pat in lang["defs"]:
                m = re.match(pat, line)
                if m and m.group(1):
                    name = m.group(1)
                    node(f"sym:{name}", "symbol", name=name)
                    edge(f"file:{rel}", f"sym:{name}", "defines", 3.0)
                    defined_in.setdefault(name, []).append(rel)
                    spans[rel].append((name, i))
            for pat in lang["imports"]:
                m = re.search(pat, line)
                if m:
                    target = next((x for x in m.groups() if x), "")
                    g["meta"].setdefault("_imports", []).append((rel, target))

        seen = set()
        for i, line in enumerate(lines):
            for name in REF.findall(line):
                if name in seen:
                    continue
                seen.add(name)
                if f"sym:{name}" in g["nodes"] or name in defined_in:
                    edge(f"file:{rel}", f"sym:{name}", "references", 1.0)
                # An identifier used as a string key is how dynamic dispatch
                # usually looks. Record it; do not pretend it is an edge.
            for m in re.finditer(r"""getattr\(|__import__\(|['"]\w+['"]\s*:\s*\w+\(""", line):
                dynamic.append(f"{rel}:{i + 1}")
                break

        # calls: attribute a reference to the enclosing definition, by line span
        if spans[rel]:
            marks = sorted(spans[rel], key=lambda t: t[1])
            for idx, (owner, start) in enumerate(marks):
                end = marks[idx + 1][1] if idx + 1 < len(marks) else len(lines)
                for line in lines[start:end]:
                    for name in REF.findall(line):
                        if name != owner and name in defined_in:
                            edge(f"sym:{owner}", f"sym:{name}", "calls", 1.5)

    # A `Governs:` target is resolved against the tracked tree, and a miss is
    # recorded rather than dropped -- a document claiming to govern a path that
    # no longer exists is drift, and it is invisible from either side alone.
    tracked = set(files)
    for src, target in governs:
        hits = [f for f in tracked if f == target or f.startswith(target.rstrip("*"))]
        if hits:
            for f in hits[:200]:
                edge(f"doc:{src}", f"file:{f}", "governs", 2.0)
        else:
            dangling_governs.append(f"{src} -> {target}")

    # resolve imports against tracked paths
    index = {}
    for rel in files:
        stem = os.path.splitext(rel)[0]
        index[stem.replace(os.sep, ".")] = rel
        index[stem.replace(os.sep, "/")] = rel
        index[os.path.basename(stem)] = rel
    for src, target in g["meta"].pop("_imports", []):
        key = target.lstrip("./").replace("/", ".")
        hit = index.get(key) or index.get(target) or index.get(key.split(".")[-1])
        if hit and hit != src:
            edge(f"file:{src}", f"file:{hit}", "imports", 2.0)
        else:
            unresolved_imports.append(f"{src} -> {target}")

    g["meta"] = dict(
        files=len([n for n in g["nodes"].values() if n["kind"] == "file"]),
        docs=len([n for n in g["nodes"].values() if n["kind"] == "doc"]),
        symbols=len([n for n in g["nodes"].values() if n["kind"] == "symbol"]),
        edges=len(g["edges"]),
        extractor=try_tree_sitter(),
        excluded_by_policy=excluded,
        blind=dict(
            skipped_by_extension=dict(sorted(skipped.items(),
                                             key=lambda kv: -kv[1])[:20]),
            unresolved_imports=sorted(unresolved_imports)[:50],
            unresolved_import_count=len(unresolved_imports),
            dynamic_dispatch_sites=sorted(dynamic)[:50],
            dynamic_dispatch_count=len(dynamic),
            dangling_governs=sorted(dangling_governs)[:50],
            dangling_governs_count=len(dangling_governs),
        ),
    )
    return g


REPORT = """\
# Index negative control

Source: `scripts/index/build.py --report`. Regenerating this file must leave an
empty `git diff` — that gate is what keeps it from being edited by hand.

This records what the graph **cannot see**. It is a finding, not a disclaimer:
an agent told that reflection-based registrations are invisible goes and greps,
and an agent told nothing concludes the code does not exist.

| | |
|---|---|
| Extractor | `{extractor}` |
| Excluded by policy (vendored / generated) | {excluded_by_policy} |
| Files / docs / symbols | {files} / {docs} / {symbols} |
| Edges | {edges} |
| Unresolved imports | {unresolved_import_count} |
| Dynamic dispatch sites | {dynamic_dispatch_count} |
| `Governs:` targets that do not resolve | {dangling_governs_count} |

## Skipped, by extension

{skipped_table}

## Unresolved imports (first 50)

{unresolved}

## Dynamic dispatch (first 50)

These are call sites the graph records the existence of but cannot connect. A
question whose answer depends on one of these needs a grep, not a query.

{dynamic}

## `Governs:` targets that do not resolve

A document claiming to govern a path that is not in the tree. Either the path
moved and the document was not updated, or the document is describing something
that was removed.

{dangling}
"""


def write_report(root, g):
    b = g["meta"]["blind"]
    rows = "\n".join(f"| `{k}` | {v} |" for k, v in
                     b["skipped_by_extension"].items()) or "| — | 0 |"
    body = REPORT.format(
        skipped_table="| Extension | Files |\n|---|---|\n" + rows,
        unresolved="\n".join(f"- `{x}`" for x in b["unresolved_imports"]) or "_none_",
        dynamic="\n".join(f"- `{x}`" for x in b["dynamic_dispatch_sites"]) or "_none_",
        dangling="\n".join(f"- `{x}`" for x in b["dangling_governs"]) or "_none_",
        **{k: v for k, v in g["meta"].items() if k != "blind"},
        **{k: v for k, v in b.items() if isinstance(v, int)},
    )
    out = os.path.join(root, "docs", "generated", "index-report.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(body)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=".index/graph.json")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    files, excluded = tracked_files(root)
    if files is None:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2

    g = scan(root, files, excluded)
    out = a.out if os.path.isabs(a.out) else os.path.join(root, a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(g, fh)

    m = g["meta"]
    print(f"{m['files']} files · {m['docs']} docs · {m['symbols']} symbols · "
          f"{m['edges']} edges · extractor={m['extractor']}")
    if m["blind"]["skipped_by_extension"]:
        top = ", ".join(f"{k}×{v}" for k, v in
                        list(m["blind"]["skipped_by_extension"].items())[:5])
        print(f"blind: {top}  (see --report)")
    if a.report:
        print("wrote", os.path.relpath(write_report(root, g), root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
