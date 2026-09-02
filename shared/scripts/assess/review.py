#!/usr/bin/env python3
"""The last pass: an agent puts a number on every sub-item, out of ten.

    python3 assess/review.py --brief RUN.json          # what to answer
    python3 assess/review.py --grade RUN.json --answers A.json

Exit codes:
    0 = the brief was written, or the answers were graded
    2 = cannot judge (no run, or nothing usable came back)

## Why the last word is an agent's and not a threshold's

Every row this page prints is a measurement, and not one of them is a verdict.
`3 of 6 destructive actions refused` is bad in a repository where an agent
commits all day and irrelevant in one nobody has write access to. `31% of
statements never executed` is alarming in a payments library and ordinary in a
tree of one-shot scripts. `nothing is required on main` is the finding of the
week in a team of twelve and noise in a repository with one author.

A threshold chosen here is a threshold chosen for a repository nobody has seen.
So the rows narrow, and the last step is a reading: an agent that has the
measurements *and* has opened the repository puts each sub-item somewhere on a
ten.

## Why ten and not good/bad

Two states cannot say *this is the one to fix first*. Six of ten and two of ten
are both `bad` and they are not the same week's work. Ten is not precise -- it
is not meant to be, and nothing here pretends there is a rubric behind the
difference between a 6 and a 7. What it carries is **order**, which is the only
thing anybody does with this page: what to do next.

The number is also comparable against **itself**. Two runs of the same
repository, before and after a change, are the comparison this supports. Two
different repositories are not.

## What the agent is not allowed to do

Score a sub-item nobody measured. A row that abstained stays absent -- there is
no `0` for `we could not run your tests`, because a repository whose toolchain
is missing is not a repository with bad tests. Sub-items with no row are not in
the brief and are refused if they come back anyway.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MIN, MAX = 0, 10

# Which printed rows belong to which sub-item. Matched on the row labels rather
# than set at the point each row is built, so that the numbering can change
# without touching the nine modules that produce rows -- and so that a row
# nobody has mapped yet is visible as unmapped instead of silently scored.
SUBITEMS = (
    ("1.1", "dangerous behaviour",
     "destructive actions are refused, recorded, or left revertible",
     ("refused before they happen",)),
    ("1.2", "legitimate work",
     "the repository's own ordinary work still gets through",
     ("legitimate work blocked", "legitimate work refused")),
    ("1.3", "watching a change run",
     "an agent can run the thing, drive it, read its logs, see its surface",
     ("an agent watching", "watching its own change")),

    ("2.1", "coverage",
     "what no test executes at all, from the ecosystem's own tool",
     ("statements no test executes", "branches never taken both ways",
      "criteria this tool does not produce")),
    ("2.2", "mutation",
     "changes the tests did not notice, judged for whether they mattered",
     ("mutants", "survivors", "uncaught changes")),
    ("2.3", "real defect replay",
     "this repository's own defects, put back, and where each was caught",
     ("defects available to replay", "how the defect got in",
      "where each was first caught", "and how long that took",
      "defects that could not be put back")),
    ("2.4", "the layers behind the ladder",
     "which rungs exist, which are wired and silent, which are absent",
     ("what could have caught it",)),

    ("3.1", "tested",
     "changes that add or repair behaviour arrive with something verifying them",
     ("changes that verified nothing", "where the verdict is written",
      "unverified changes to the machinery itself", "a verdict someone can run")),
    ("3.2", "verified",
     "the repository requires the check, rather than merely offering it",
     ("can the verification be skipped", "steps that could turn a red run green",
      "CI runs the suite")),

    ("4.1", "what is written down",
     "the kinds of memory that exist, and whether their references hold",
     ("what it writes down", "references that do not resolve",
      "somewhere mistakes are written")),
    ("4.2", "is each memory worth keeping",
     "what the standing text is spent on, and what restates a guard",
     ("candidates for a second reading",)),
    ("4.3", "documents against the code",
     "promises the documentation makes that the code does not keep",
     ("promises the documents make", "claims tested")),
    ("4.4", "documents against each other",
     "two documents naming one thing and giving it two values",
     ("documents that contradict each other",)),
    # Not "is it worth keeping" (4.2) and not "is it true" (4.1, 4.3, 4.4).
    # A standing instruction can be worth every token, accurate, and still
    # written in a shape that competes with itself for attention -- which is
    # the only thing this one asks about.
    ("4.5", "the form of the instructions",
     "whether what is kept is shaped so a model can act on it",
     ("the form of the instructions",
      "prohibitions with no stated alternative",
      "paragraphs carrying several requirements at once",
      "requirements asking for a quality, not a shape")),

    ("5.1", "usage",
     "floor, ceiling and parked -- what a turn pays before anyone types",
     ("floor — paid on every turn", "ceiling — the worst a single turn reaches",
      "parked — installed, arrives only when asked",
      "what the floor is spent on",
      "sentences about one path, paid for on every turn")),
    ("5.2", "files unlike their neighbours",
     "each loaded file against the median of its own kind",
     ("files unlike their neighbours",)),
)

DIM_OF = {"1": "execution", "2": "validation", "3": "reliable delivery",
          "4": "repository memory", "5": "context economy"}


def _rows(run):
    """Every printed row, flattened, with the dimension it came from."""
    out = []
    for dim in run.get("dimensions") or []:
        title = dim.get("title") or dim.get("name") or ""
        for row in dim.get("rows") or []:
            out.append({**row, "dimension": title})
    return out


# A row that printed instead of abstaining. The check is on the value rather
# than the flag because an abstention and an ordinary fact share the `info`
# flag: `defects available to replay: 12` is measured, `an agent finding its
# way: not probed` is not, and both are info.
ABSTAINED = ("could not judge", "cannot judge", "not probed", "not yet judged",
             "not run", "not tested", "pending", "abstain")


def measured(row):
    value = str(row.get("value", "")).strip()
    if value in ("", "-", "\u2014", "?"):
        return False
    return not any(w in value.lower() for w in ABSTAINED)


def collect(run):
    """Sub-items that actually have a measured row, with the rows under each.

    A sub-item nothing measured is left out rather than handed over with an
    empty body. Scoring one is the failure this whole page is built against:
    it turns `we could not judge` into a number, and once a number is on a
    chart nothing distinguishes it from a measurement.

    Abstentions are dropped here rather than in the caller, because the brief
    and the grader have to agree about what exists. A sub-item the brief did
    not ask about must be refused if it comes back anyway, and that only holds
    if one function decides."""
    rows = _rows(run)
    used, out = set(), []
    for sid, name, asks, needles in SUBITEMS:
        mine = []
        for i, row in enumerate(rows):
            label = (row.get("label") or "").lower()
            if any(n.lower() in label for n in needles):
                used.add(i)
                if measured(row):
                    mine.append(row)
        if mine:
            out.append({"id": sid, "name": name, "asks": asks, "rows": mine})
    unmapped = [rows[i]["label"] for i in range(len(rows))
                if i not in used and measured(rows[i])]
    return out, unmapped


BRIEF = """\
# Put every sub-item somewhere on a ten

You have the measurements above and you have opened the repository. Neither
alone is enough: a threshold written into the instrument would be a threshold
chosen for a repository nobody has seen, and a reading with no measurements
behind it is an opinion.

**0** is the worst this could be. **10** is that nothing here is worth anyone's
time to improve. Most real sub-items are not at either end.

Two states cannot say which one to fix first, and that is the only thing
anybody does with this page. So the number carries **order**, not precision --
nothing here pretends there is a rubric behind a 6 against a 7.

Judge each sub-item **for this repository**. The same measurement means
different things in different trees:

* `3 of 6 destructive actions refused` is serious where an agent commits all
  day, and irrelevant where it has no write access
* `31% of statements never executed` is alarming in a payments library and
  ordinary in a tree of one-shot scripts
* `nothing is required on main` is the week's finding in a team of twelve and
  noise in a repository with one author

Say **why** in one line, naming the thing about *this* repository that moved
the number. A reason that would read the same for any repository is not a
reason, it is a restatement.

## Answer

    {"items": [{"id": "1.1", "score": 4,
                "why": "an agent commits here every day and three of the six
                        that matter are open"},
               {"id": "5.1", "score": 8,
                "why": "1065 tokens, and all of it is the payload/plugin split
                        nothing else states"}]}

Only the sub-items below. One that is absent was not measured, and a number
there would be indistinguishable from a measurement once it is on the chart.

---

"""


def brief(run):
    items, unmapped = collect(run)
    if not items:
        return "", "cannot judge: this run printed no row to review"
    out = [BRIEF]
    for it in items:
        out.append("## %s %s\n\n%s\n\n" % (it["id"], it["name"], it["asks"]))
        for row in it["rows"]:
            flag = (row.get("flag") or "").upper()
            out.append("- **%s**: %s%s\n" % (
                row.get("label", ""), row.get("value", ""),
                ("   [" + flag + "]") if flag else ""))
            note = (row.get("note") or "").strip()
            if note:
                out.append("  %s\n" % note.replace("\n", " ")[:400])
        out.append("\n")
    if unmapped:
        out.append("## Rows no sub-item claims\n\nScore these under whichever "
                   "sub-item they belong to, or leave them:\n\n")
        for label in unmapped:
            out.append("- %s\n" % label)
    return "".join(out), ""


def grade(run, answers):
    """The agent's numbers, checked against what was actually measured."""
    items, _ = collect(run)
    known = {it["id"]: it for it in items}
    got, refused = {}, []
    for a in (answers or {}).get("items", []):
        if not isinstance(a, dict):
            continue
        sid = str(a.get("id", "")).strip()
        if sid not in known:
            refused.append((sid or "(no id)", "nothing measured this"))
            continue
        try:
            score = float(a.get("score"))
        except (TypeError, ValueError):
            refused.append((sid, "no usable number"))
            continue
        if not (MIN <= score <= MAX):
            refused.append((sid, "out of 0-10"))
            continue
        got[sid] = {"score": score, "why": str(a.get("why", "")).strip()[:300],
                    "name": known[sid]["name"]}
    if not got:
        return None, ("cannot judge: no usable score came back" +
                      (" (" + "; ".join("%s: %s" % r for r in refused) + ")"
                       if refused else ""))
    per_dim = {}
    for sid, v in got.items():
        per_dim.setdefault(sid[0], []).append(v["score"])
    dims = {k: round(sum(v) / len(v), 1) for k, v in sorted(per_dim.items())}
    return {"items": got, "dimensions": dims, "refused": refused,
            "missing": sorted(set(known) - set(got))}, ""


# --- the shape, drawn from the numbers ------------------------------------

def radar(dims, size=400):
    """Five axes, one polygon. Deliberately without a second polygon on it.

    There is no baseline and no other repository here, so the area means
    nothing and the shape means something: which axis is short. Two runs of
    the same repository can be laid over each other; two repositories cannot,
    and the page says so rather than inviting it."""
    import math
    cx, cy, R = size / 2, size * 0.46, size * 0.275
    order = ["1", "2", "3", "4", "5"]
    names = ["1 execution", "2 validation", "3 reliable", "4 memory",
             "5 context"]

    def at(i, r):
        a = math.radians(-90 + 72 * i)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    def ring(frac):
        return " ".join("%.1f,%.1f" % at(i, R * frac) for i in range(5))

    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (
        size, size * 0.825,
        ", ".join("%s %s of 10" % (n, dims.get(k, "not scored"))
                  for n, k in zip(names, order)))]
    parts.append('<g fill="none" stroke="#c9cfce" stroke-width="1">')
    for f in (0.2, 0.4, 0.6, 0.8, 1.0):
        parts.append('<polygon points="%s"/>' % ring(f))
    parts.append("</g>")
    parts.append('<g stroke="#c9cfce" stroke-width="1">')
    for i in range(5):
        x, y = at(i, R)
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                     % (cx, cy, x, y))
    parts.append("</g>")

    pts = []
    for i, k in enumerate(order):
        pts.append(at(i, R * (dims.get(k, 0) / 10.0)))
    parts.append('<polygon points="%s" fill="#0E6C66" fill-opacity="0.17" '
                 'stroke="#0E6C66" stroke-width="2" stroke-linejoin="round"/>'
                 % " ".join("%.1f,%.1f" % p for p in pts))
    parts.append('<g fill="#0E6C66">')
    for x, y in pts:
        parts.append('<circle cx="%.1f" cy="%.1f" r="3.4"/>' % (x, y))
    parts.append("</g>")
    parts.append('<g font-size="11.5" fill="#4a5654" '
                 'font-family="ui-monospace, monospace">')
    anchors = ("middle", "start", "middle", "middle", "end")
    for i, (n, k, anc) in enumerate(zip(names, order, anchors)):
        x, y = at(i, R * 1.24)
        parts.append('<text x="%.1f" y="%.1f" text-anchor="%s">%s  %s</text>'
                     % (x, y + 4, anc, n,
                        ("%g" % dims[k]) if k in dims else "--"))
    parts.append("</g></svg>")
    return "".join(parts)


def render(judged):
    out = ["", "  the reading, out of ten", ""]
    for sid in sorted(judged["items"]):
        v = judged["items"][sid]
        out.append("  %-5s %-34s %4g / 10" % (sid, v["name"][:34], v["score"]))
        if v["why"]:
            out.append("        %s" % v["why"][:96])
    out.append("")
    for k in sorted(judged["dimensions"]):
        out.append("  %s  %-22s %4g / 10"
                   % (k, DIM_OF.get(k, ""), judged["dimensions"][k]))
    if judged["missing"]:
        out.append("")
        out.append("  not scored: " + ", ".join(judged["missing"])
                   + "  -- measured, and the reading skipped them")
    for sid, why in judged["refused"]:
        out.append("  refused %s: %s" % (sid, why))
    return "\n".join(out) + "\n"



# --- the page -------------------------------------------------------------
#
# Self-contained: no network, no font host, no script. The instrument may be
# read on a machine that has neither, and a page that degrades to unstyled
# text when a CDN is unreachable is a page that fails in exactly the
# circumstances somebody is most likely to be reading it.

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
:root{--bg:#FBFAF7;--card:#FFFFFF;--ink:#1B2220;--ink-2:#4A5654;
 --ink-3:#7E8A87;--line:#E4E7E4;--accent:#0E6C66;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#121615;--card:#1A201F;--ink:#E8EDEB;--ink-2:#AAB4B1;
 --ink-3:#7B8683;--line:#2A3230;--accent:#4FBFB2}}
:root[data-theme="dark"]{--bg:#121615;--card:#1A201F;--ink:#E8EDEB;
 --ink-2:#AAB4B1;--ink-3:#7B8683;--line:#2A3230;--accent:#4FBFB2}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:62rem;margin:0 auto;padding:2.5rem 1.5rem 4rem}
.eyebrow{font:600 11px/1 ui-monospace,monospace;letter-spacing:.14em;
 text-transform:uppercase;color:var(--accent);margin:0 0 .6rem}
h1{font-size:1.9rem;margin:0 0 .5rem;letter-spacing:-.01em;
 text-wrap:balance}
.sub{color:var(--ink-2);margin:0 0 1.6rem;max-width:44rem}
.meta{display:flex;flex-wrap:wrap;gap:.4rem 1.4rem;
 font:12px/1.5 ui-monospace,monospace;color:var(--ink-3);
 border-top:1px solid var(--line);padding-top:.8rem}
.meta b{color:var(--ink-2);font-weight:600}
.figure{display:flex;flex-wrap:wrap;gap:2rem;align-items:center;
 margin:2rem 0 2.5rem;padding:1.4rem;background:var(--card);
 border:1px solid var(--line);border-radius:10px}
.plot{flex:1 1 20rem;min-width:17rem}
.plot svg{width:100%%;height:auto}
.legend{flex:1 1 17rem;min-width:15rem}
.legend h2{font:600 12px/1 ui-monospace,monospace;letter-spacing:.1em;
 text-transform:uppercase;color:var(--ink-3);margin:0 0 .9rem}
.lrow{display:flex;align-items:baseline;gap:.7rem;padding:.34rem 0;
 border-bottom:1px solid var(--line)}
.lrow .n{font:600 11px/1 ui-monospace,monospace;color:var(--accent);width:1rem}
.lrow .name{flex:1;color:var(--ink-2)}
.lrow .score{font:600 15px/1 ui-monospace,monospace;
 font-variant-numeric:tabular-nums}
.caveat{font-size:12.5px;color:var(--ink-3);margin:1rem 0 0;line-height:1.55}
.item{display:flex;gap:1rem;align-items:flex-start;padding:.95rem 0;
 border-bottom:1px solid var(--line)}
.item .id{font:600 12px/1.5 ui-monospace,monospace;color:var(--accent);
 width:2.4rem;flex:none}
.item .what{flex:1;min-width:0}
.item b{font-weight:600}
.item p{margin:.25rem 0 0;color:var(--ink-2);font-size:13.5px}
.item .val{font:12px/1.5 ui-monospace,monospace;color:var(--ink-3);
 margin-top:.35rem;white-space:pre-wrap;word-break:break-word}
.item .s{font:600 17px/1 ui-monospace,monospace;flex:none;width:4.2rem;
 text-align:right;font-variant-numeric:tabular-nums}
.item .s small{font-weight:400;font-size:11px;color:var(--ink-3)}
.note{margin-top:2rem;padding:1rem 1.2rem;background:var(--card);
 border:1px solid var(--line);border-left:3px solid var(--accent);
 border-radius:6px;font-size:13.5px;color:var(--ink-2)}
</style></head><body><div class="wrap">
<p class="eyebrow">Assessment</p>
<h1>%(title)s</h1>
<p class="sub">%(sub)s</p>
<div class="meta">%(meta)s</div>
<div class="figure"><div class="plot">%(radar)s</div>
<div class="legend"><h2>Out of ten</h2>%(legend)s
<p class="caveat">%(caveat)s</p></div></div>
%(items)s
%(note)s
</div></body></html>
"""

CAVEAT = ("An agent that had the measurements and had opened the repository "
          "put each sub-item on a ten. There is no baseline and no second "
          "repository on the plot, so the shape is worth reading and the area "
          "is not: two runs of the same repository compare, two repositories "
          "do not.")

ABSENT = ("Sub-items with no row here were not measured in this run. They are "
          "absent rather than zero \u2014 a number on a chart cannot be told "
          "apart from a measurement, and `we could not run your tests` is not "
          "`your tests are bad`.")


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def html(judged, run=None, title="The Reading"):
    """One page: the shape, then every sub-item that earned a number."""
    items, _ = collect(run or {})
    by_id = {it["id"]: it for it in items}
    legend, body = [], []
    for k in sorted(judged["dimensions"]):
        legend.append(
            '<div class="lrow"><span class="n">%s</span>'
            '<span class="name">%s</span>'
            '<span class="score">%g</span></div>'
            % (k, _esc(DIM_OF.get(k, "")), judged["dimensions"][k]))
    for sid in sorted(judged["items"]):
        v = judged["items"][sid]
        it = by_id.get(sid, {})
        rows = "\n".join(
            "%s: %s" % (r.get("label", ""), r.get("value", ""))
            for r in it.get("rows", []))
        body.append(
            '<div class="item"><span class="id">%s</span>'
            '<div class="what"><b>%s</b><p>%s</p>'
            '<div class="val">%s</div></div>'
            '<span class="s">%g<small> /10</small></span></div>'
            % (_esc(sid), _esc(v["name"]), _esc(v["why"]), _esc(rows),
               v["score"]))
    meta = []
    if run:
        head = run.get("head") or {}
        for key in ("name", "tracked", "source", "tier"):
            if head.get(key) is not None:
                meta.append("<span><b>%s</b> %s</span>"
                            % (key, _esc(head[key])))
    meta.append("<span><b>scored</b> %d of %d sub-item(s)</span>"
                % (len(judged["items"]),
                   len(judged["items"]) + len(judged["missing"])))
    return PAGE % {
        "title": _esc(title),
        "sub": ("Every number here is a reading, not a threshold. The rows "
                "underneath each one are what it was read from."),
        "meta": "".join(meta),
        "radar": radar(judged["dimensions"]),
        "legend": "".join(legend),
        "caveat": CAVEAT,
        "items": "".join(body),
        "note": '<div class="note">%s</div>' % ABSENT,
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--brief", default="", help="a run's JSON")
    ap.add_argument("--grade", default="", help="a run's JSON")
    ap.add_argument("--answers", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--html", default="", help="also write a page for a person")
    a = ap.parse_args()

    path = a.brief or a.grade
    if not path:
        print("cannot judge: pass --brief RUN.json or --grade RUN.json",
              file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as fh:
        run = json.load(fh)

    if a.brief:
        text, why = brief(run)
        if not text:
            print(why, file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if not a.answers:
        print("cannot judge: --grade needs --answers", file=sys.stderr)
        return 2
    with open(a.answers, encoding="utf-8") as fh:
        judged, why = grade(run, json.load(fh))
    if judged is None:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(judged, fh, indent=1, ensure_ascii=False)
    if a.html:
        with open(a.html, "w", encoding="utf-8") as fh:
            fh.write(html(judged, run))
        print("  page written to %s\n" % os.path.abspath(a.html))
    sys.stdout.write(render(judged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
