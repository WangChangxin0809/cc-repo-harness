#!/usr/bin/env python3
"""Gate: no scaffolded template was left with its placeholders in it.

    python3 scripts/gates/check_templates_filled.py [--root .]

    0 = filled    1 = placeholders remain    2 = cannot judge

This gate exists because the failure it catches is the most likely one in the
whole harness and the least visible. A scaffolder writes a dozen files in a
second; filling them takes an afternoon; the tree in between looks *exactly*
like a documented repository. Every other check passes on it -- the line count
is fine, the routing table resolves, the community-health files are present --
and a reader, human or agent, finds `<One paragraph: what this is>` only after
trusting the file enough to act on it.

`check_context_budget.py` used to be asked to catch this with `len(body) < 5`,
which catches an *empty* file and nothing else. The scaffolder's own CLAUDE.md
has twenty-odd non-blank lines of pure placeholder and sailed through. A check
that cannot fail on the artefact its own repository ships is the thing this
project keeps telling other people not to build.

## What counts as a placeholder

`<angle-bracketed text>`, judged by where it sits. Code is where angle brackets
are legitimately dense -- `Vec<String>`, `<html>`, `Authorization: Bearer
<token>` -- so the bar there is higher, but it is not infinite: a quick start
that still reads

    ```bash
    <the shortest sequence from a fresh clone to something working>
    ```

is the single most common unfilled template in the wild, and stripping code
blocks outright would make this gate blind to exactly it.

| Where | Reported when the text inside the brackets… |
|---|---|
| Prose | contains a space, or is lowercase, or is a date mask |
| Code, fenced or inline | is three or more words |

Three words is what separates `<the shortest sequence from a fresh clone>` from
`Map<String, Int>`, and it is the whole reason the two regions are scanned under
different rules rather than one compromise rule that is wrong in both.

A file whose first 40 lines contain `<!-- placeholders-ok: reason -->` is
exempt. The reason is required: an exemption without one becomes a blanket.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.S | re.M)
INLINE_CODE = re.compile(r"`+[^`\n]*`+")
COMMENT = re.compile(r"<!--.*?-->", re.S)
ANGLE = re.compile(r"<([^<>\n]{2,})>")
EXEMPT = re.compile(r"<!--\s*placeholders-ok:\s*\S+")

DATE_MASK = re.compile(r"^[YMDNn0-9]+(?:[-/][YMDNn0-9]+)*$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.·/…-]*$")

SKIP_DIRS = {"generated", "node_modules", "vendor", "third_party", ".venv",
             "site-packages", "__pycache__"}

# Markdown on GitHub renders inline HTML, and a README that folds its long tree
# into <details> is using the platform rather than leaving a blank to fill.
VOID_HTML = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}
HTML = VOID_HTML | {
    "a", "abbr", "article", "aside", "b", "blockquote", "caption", "center",
    "cite", "code", "colgroup", "dd", "del", "details", "div", "dl", "dt",
    "em", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "i", "ins", "kbd", "li", "main", "mark", "nav", "ol",
    "p", "picture", "pre", "q", "s", "samp", "section", "small", "span",
    "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "time", "tr", "u", "ul", "var", "video", "audio"}

OPEN_TAG = re.compile(r"^([A-Za-z][A-Za-z0-9]*)(?:\s[^<>]*)?/?$")
CLOSE_TAG = re.compile(r"</([A-Za-z][A-Za-z0-9]*)\s*>")


def html_in(text: str):
    """Which `<...>` in this document are markup rather than a blank to fill.

    An element name alone is not enough -- `<summary>` is a real HTML tag and
    also a plausible thing to leave unwritten. What separates them is whether
    the document goes on to use it as markup: a void element such as `<img>`,
    which never closes, or one whose closing tag is present. So `<details>`
    above a `</details>` is markup, and a lone `<summary>` under a heading
    that says what to write there is still reported.
    """
    closed = {m.group(1).lower() for m in CLOSE_TAG.finditer(text)}

    def markup(inner: str) -> bool:
        m = OPEN_TAG.match(inner.strip())
        if not m:
            return False
        name = m.group(1).lower()
        return name in HTML and (name in VOID_HTML or name in closed)

    return markup


def in_prose(inner: str) -> bool:
    inner = inner.strip()
    if not inner or inner[0] in "/!?%":       # closing tag, comment, template tag
        return False
    if " " in inner:                          # "<One paragraph: what this is>"
        return True
    if IDENTIFIER.match(inner):               # "<project>", "<docs/path.md>"
        return True
    if DATE_MASK.match(inner):                # "<YYYY-MM-DD>", "<00NN>"
        return True
    return False


def in_code(inner: str) -> bool:
    """Three words or more. Below that it is a type parameter or a one-word
    stand-in a reader will fill from context; above it, it is a sentence
    somebody meant to replace."""
    return len(inner.split()) >= 3


def indented_block_spans(text: str):
    """Markdown's other code block: four spaces or a tab, opened by a blank
    line. Handling only fences would leave every command example written this
    way judged as prose, where the bar is one space rather than three words --
    and `git clone <REPO>` would be reported as an unfilled template. A gate
    that cries wolf on real documents is a gate nobody leaves switched on."""
    spans, pos, prev_blank, start = [], 0, True, None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        indented = bool(re.match(r"(?: {4}|\t)", line)) and stripped
        if indented and (prev_blank or start is not None):
            start = pos if start is None else start
        elif stripped and start is not None:
            spans.append((start, pos))
            start = None
        if stripped:
            prev_blank = False
        else:
            prev_blank = True
        pos += len(line)
    if start is not None:
        spans.append((start, pos))
    return spans


def split_regions(text: str):
    """(prose, code) — the same document twice, each with the other blanked to
    spaces. Newlines survive both, so reported line numbers stay honest."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    spans = [m.span() for m in FENCE.finditer(text)]
    spans += [m.span() for m in INLINE_CODE.finditer(text)]
    spans += indented_block_spans(text)

    prose = list(COMMENT.sub(blank, text))
    code = [c if c == "\n" else " " for c in text]
    for start, end in spans:
        for i in range(start, end):
            if text[i] != "\n":
                prose[i] = " "
                code[i] = text[i]
    return "".join(prose), "".join(code)


def scan(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    if EXEMPT.search("".join(text.splitlines(keepends=True)[:40])):
        return []

    hits = {}
    markup = html_in(text)
    for body, accept in zip(split_regions(text), (in_prose, in_code)):
        for lineno, line in enumerate(body.splitlines(), 1):
            for m in ANGLE.finditer(line):
                if accept(m.group(1)) and not markup(m.group(1)):
                    hits.setdefault((lineno, m.start()), (lineno, m.group(0)))
    return [v for _, v in sorted(hits.items())]


def targets(root):
    """The repository's own knowledge surface: root-level markdown plus docs/.
    Not the whole tree -- a placeholder in a fixture or a vendored README is
    somebody else's problem, and a gate that reports it gets skipped."""
    out = []
    for name in sorted(os.listdir(root)):
        if name.endswith(".md") and os.path.isfile(os.path.join(root, name)):
            out.append(name)
    docs = os.path.join(root, "docs")
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if not os.path.isdir(root):
        print(f"cannot judge: no such directory: {root}", file=sys.stderr)
        return 2
    files = targets(root)
    if not files:
        print("cannot judge: no markdown at the repository root or under docs/",
              file=sys.stderr)
        return 2

    found = [(rel, hits) for rel in files
             for hits in [scan(os.path.join(root, rel))] if hits]
    if not found:
        return 0

    total = sum(len(h) for _, h in found)
    print(f"{total} unfilled placeholder(s) in {len(found)} file(s):",
          file=sys.stderr)
    for rel, hits in found:
        for lineno, snippet in hits[:6]:
            short = snippet if len(snippet) <= 60 else snippet[:57] + "…>"
            print(f"  {rel}:{lineno}  {short}", file=sys.stderr)
        if len(hits) > 6:
            print(f"  {rel}          … and {len(hits) - 6} more", file=sys.stderr)
    print("\n  A template left unfilled is worse than no file: it reads as "
          "though the\n  conventions were written down, so nobody writes them. "
          "Fill it, delete the\n  section, or mark the file "
          "<!-- placeholders-ok: <reason> --> in its first 40 lines.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
