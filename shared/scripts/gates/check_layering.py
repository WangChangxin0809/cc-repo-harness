#!/usr/bin/env python3
"""Gate: imports must point down the declared layer stack, never up.

    python3 scripts/gates/check_layering.py [--root .] [--json]

    0 = no upward imports    1 = upward imports found    2 = cannot judge

An empty `"layers": []` means "not declared yet": the gate reports that it is
inert and exits 0. A *missing* `"layers"` key means the declaration was never
considered, and exits 2. The distinction matters -- one is a choice, the other
is an unknown, and collapsing them either makes every fresh install red or hides
a config that silently stopped being read.

Layering described in prose is followed for about a month. The reason is not
carelessness: an upward import is invisible at review time -- the diff shows one
plausible line, and the fact that it inverts the architecture is only visible to
someone holding the whole stack in their head. A gate holds it for them.

Declare the stack in `.claude/guards.json`:

    {"layers": [
       {"name": "types",   "paths": ["src/types/"]},
       {"name": "config",  "paths": ["src/config/"]},
       {"name": "repo",    "paths": ["src/repo/"]},
       {"name": "service", "paths": ["src/service/"]},
       {"name": "ui",      "paths": ["src/ui/", "src/pages/"]}
     ],
     "layering_allow": ["src/service/legacy_bridge.py -> src/ui/"]}

Order is the stack, lowest first. A file in layer N may import from layers
0..N; importing from N+1 or above is the violation. Files in no declared layer
are not judged -- an unlisted directory is a gap in the declaration, not a pass,
and the summary line says how many files fell through so the gap is visible.

`layering_allow` entries are exceptions with a shape that makes them expensive
to accumulate: each names a specific source file and a specific target prefix,
so a blanket exemption cannot be written. Every entry is a piece of debt and
belongs in `docs/exec-plans/tech-debt-tracker.md` with a reason.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

IMPORT_PATTERNS = [
    re.compile(r"^\s*from\s+([\w.]+)\s+import"),
    re.compile(r"^\s*import\s+([\w.]+)"),
    re.compile(r"""^\s*import\s.*?from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""^\s*use\s+([\w:]+)"""),
    re.compile(r"""\bpreload\(\s*"([^"]+)"""),
]
SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".go", ".rs",
              ".java", ".gd"}


def load_config(root):
    path = os.path.join(root, ".claude", "guards.json")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except OSError:
        return None, f"no {os.path.relpath(path, root)} — nothing to enforce"
    except ValueError as exc:
        return None, f"{os.path.relpath(path, root)} does not parse: {exc}"
    if "layers" not in cfg:
        return None, ('no "layers" key in .claude/guards.json — this gate has '
                      'no idea what the stack is')
    if cfg["layers"] == []:
        # An explicitly empty list is an author's statement ("not declared
        # yet"), not an unknown. Treating it as unjudgeable makes every fresh
        # install exit 2 on its first run, and a suite that is red out of the
        # box is a suite people learn to ignore -- which costs more than the
        # rule this gate protects. The note keeps it from being forgotten.
        return cfg, "inert"
    return cfg, None


def layer_of(rel, layers):
    """Deepest matching prefix wins, so src/ui/widgets/ can sit in a layer of
    its own without src/ui/ swallowing it."""
    best, best_len = None, -1
    for i, layer in enumerate(layers):
        for prefix in layer["paths"]:
            if rel.startswith(prefix) and len(prefix) > best_len:
                best, best_len = i, len(prefix)
    return best


def resolve(target, files_by_key):
    for key in (target, target.replace(".", "/"), target.replace("::", "/"),
                target.lstrip("./")):
        hit = files_by_key.get(key)
        if hit:
            return hit
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    cfg, why = load_config(root)
    if cfg is None:
        print(f"cannot judge: {why}", file=sys.stderr)
        return 2
    if why == "inert":
        print('note: no layer stack declared, so this gate enforces nothing. '
              'Add "layers" to .claude/guards.json, lowest layer first — see '
              "the docstring of this file for the shape.", file=sys.stderr)
        return 0

    ls = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                        capture_output=True, text=True)
    if ls.returncode != 0:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2
    files = [p for p in ls.stdout.split("\0")
             if p and os.path.splitext(p)[1] in SOURCE_EXT]

    layers = cfg["layers"]
    names = [l["name"] for l in layers]
    allow = set(cfg.get("layering_allow", []))

    by_key = {}
    for rel in files:
        stem = os.path.splitext(rel)[0]
        by_key.setdefault(stem, rel)
        by_key.setdefault(stem.replace(os.sep, "."), rel)
        by_key.setdefault(os.path.basename(stem), rel)

    violations, unclassified = [], 0
    for rel in files:
        src_layer = layer_of(rel, layers)
        if src_layer is None:
            unclassified += 1
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8",
                      errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            for pat in IMPORT_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                target = resolve(m.group(1), by_key)
                if not target:
                    continue
                dst_layer = layer_of(target, layers)
                if dst_layer is None or dst_layer <= src_layer:
                    continue
                if any(rel == e.split(" -> ")[0].strip()
                       and target.startswith(e.split(" -> ")[-1].strip())
                       for e in allow if " -> " in e):
                    continue
                violations.append(dict(file=rel, line=n, target=target,
                                       from_layer=names[src_layer],
                                       to_layer=names[dst_layer]))

    if a.json:
        print(json.dumps(dict(violations=violations,
                              unclassified=unclassified,
                              layers=names), indent=2))
        return 1 if violations else 0

    if not violations:
        # Silent on success -- output on every green run trains everyone to
        # skim, and then the one run that printed something goes unread. The
        # unclassified count is the exception: it is how a gap in the layer
        # declaration becomes visible, and a gap is not a pass.
        if unclassified:
            print(f"note: {unclassified} source file(s) are in no declared "
                  f"layer and were not judged", file=sys.stderr)
        return 0

    print(f"{len(violations)} import(s) point up the layer stack "
          f"({' < '.join(names)}):", file=sys.stderr)
    for v in violations:
        print(f"  {v['file']}:{v['line']}  [{v['from_layer']}] imports "
              f"{v['target']}  [{v['to_layer']}]", file=sys.stderr)
    print("\nFix by moving the shared piece down the stack, or by inverting the\n"
          "dependency behind an interface owned by the lower layer.\n"
          "If it genuinely cannot be fixed now, add the exact pair to\n"
          '"layering_allow" in .claude/guards.json AND a line in\n'
          "docs/exec-plans/tech-debt-tracker.md saying why. Why this rule\n"
          "exists: docs/decisions/", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
