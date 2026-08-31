#!/usr/bin/env python3
"""Turn the five dimensions into something a person reads once and acts on.

Two renderings of the same data, and they must never disagree:

    text   for a terminal, and for the agent that will write the checklist
    html   for the person who is deciding whether to spend anyone's time

The HTML is self-contained -- no network, no fonts to fetch, no scripts. It is
written to a file and opened; it may be read on a machine that has never heard
of this project, and a report that needs a CDN to render is a report that is
blank in exactly the meeting it was made for.

## Why flags and not scores

There is no total. A number out of a hundred invites the reader to compare two
repositories that have nothing to do with each other, and it hides which of the
five kinds of trouble this one is in -- which is the only thing the page is for.
Each row carries a flag instead, and the flags mean:

    ok    measured, and nothing here needs attention
    warn  measured, and worth a look
    bad   measured, and it names something that can cost you
    info  measured, and it is context rather than a verdict

`abstained` is a state of a whole dimension, never of a row, and it is never
rendered as a zero.
"""

from __future__ import annotations

import datetime
import html
import os

FLAG_ORDER = {"bad": 0, "warn": 1, "ok": 2, "info": 3}

MARK = {"ok": "ok  ", "warn": "warn", "bad": "BAD ", "info": "·   "}


# -- text --------------------------------------------------------------------

def text(head, dims, cannot_say):
    out = ["", f"  {head['name']}",
           f"  {head['tracked']} tracked · {head['source']} source · "
           f"tier {head['tier']}"
           + (f" · {head['scope']}" if head.get("scope") else ""),
           ""]
    for d in dims:
        if d["state"] == "abstained":
            out.append(f"  {d['n']}. {d['name']} — COULD NOT JUDGE: "
                       f"{d['headline']}")
        else:
            out.append(f"  {d['n']}. {d['name']} — {d['headline']}")
        for row in d["rows"]:
            out.append(f"     {MARK.get(row['flag'], '    ')} "
                       f"{row['label']}: {row['value']}")
            if row.get("note"):
                out += _wrap(row["note"], "          ")
        out.append("")

    if cannot_say:
        out.append("  WHAT THIS PAGE CANNOT SAY — the brief for the reading")
        for i, q in enumerate(cannot_say, 1):
            out.append(f"    {i}. {q}")
        out.append("")
    return "\n".join(out)


def _wrap(s, pad, width=72):
    words, line, out = s.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(pad + line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(pad + line)
    return out


# -- html --------------------------------------------------------------------

CSS = """
:root{
  --ink:#16191c; --dim:#5d666e; --faint:#8b949c;
  --ground:#fbfaf8; --card:#ffffff; --rule:#e6e3dd;
  --accent:#0f5f63;
  --ok:#2f7a52; --warn:#a8700f; --bad:#b03a2b; --info:#6b737a;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ink:#e8e6e2; --dim:#a2aab1; --faint:#767e85;
    --ground:#121416; --card:#191c1f; --rule:#2b3034;
    --accent:#5fb8ba;
    --ok:#63b98a; --warn:#d9a441; --bad:#e0705e; --info:#8e969d;
  }
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",
       "Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:820px;margin:0 auto;padding:56px 24px 80px}
header{border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:6px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em;
   text-wrap:balance}
.sub{color:var(--dim);font-size:13px;
     font-variant-numeric:tabular-nums;display:flex;flex-wrap:wrap;gap:0 14px}
.sub b{font-weight:600;color:var(--ink)}
.ran{margin:14px 0 34px;font-size:12.5px;color:var(--faint)}
section{
  background:var(--card);border:1px solid var(--rule);border-radius:3px;
  padding:20px 22px;margin-bottom:14px;
}
.dh{display:flex;gap:12px;align-items:baseline;margin-bottom:2px}
.n{font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
   color:var(--accent);border:1px solid var(--accent);border-radius:2px;
   padding:4px 6px;flex:none}
h2{font-size:15px;margin:0;font-weight:650;letter-spacing:.01em}
.q{color:var(--dim);font-size:13px;margin:2px 0 0 34px;font-style:italic}
.head{margin:14px 0 16px 34px;font-size:16px;font-weight:600;
      border-left:3px solid var(--accent);padding-left:12px;text-wrap:balance}
.head.abst{border-color:var(--info);color:var(--dim);font-weight:500}
table{width:100%;border-collapse:collapse;margin-left:34px;
      width:calc(100% - 34px)}
td{padding:9px 0;vertical-align:top;border-top:1px solid var(--rule)}
tr:first-child td{border-top:0}
td.f{width:8px;padding-right:10px}
td.l{width:38%;min-width:10rem;color:var(--dim);font-size:13.5px}
/* `pre-wrap` rather than `nowrap`: the double space in `6/33  (18%)` has to
   survive, but a value naming four workflow files must be allowed to wrap.
   With `nowrap` one long row widened the table and squeezed every label in
   the dimension into a five-line column. */
td.v{font:600 13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
     font-variant-numeric:tabular-nums;white-space:pre-wrap;
     overflow-wrap:anywhere;padding-right:14px}
.note{display:block;color:var(--faint);font-size:12.5px;font-weight:400;
      font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,
                  "Noto Sans CJK SC","PingFang SC",sans-serif;
      line-height:1.5;white-space:normal;margin-top:4px;max-width:46em}
.dot{display:block;width:8px;height:8px;border-radius:50%;margin-top:7px}
.dot.ok{background:var(--ok)} .dot.warn{background:var(--warn)}
.dot.bad{background:var(--bad)} .dot.info{background:var(--info);opacity:.4}
.cannot{margin-top:34px;border-top:1px solid var(--rule);padding-top:20px}
.cannot h3{font-size:12px;text-transform:uppercase;letter-spacing:.09em;
           color:var(--faint);margin:0 0 12px;font-weight:600}
.cannot ol{margin:0;padding-left:20px;color:var(--dim);font-size:13.5px}
.cannot li{margin-bottom:6px}
footer{margin-top:34px;color:var(--faint);font-size:12px;line-height:1.7}
@media(max-width:620px){
  .wrap{padding:32px 16px 60px}
  table,.head,.q{margin-left:0;width:100%}
  td.l{width:auto;display:block;padding-bottom:0}
  td.v{display:block;white-space:normal;padding:0 0 9px}
  td.f{display:none}
}
"""


def html_page(head, dims, cannot_say):
    """The whole document, self-contained: no network, no fonts, no scripts."""
    e = html.escape
    parts = ['<div class="wrap">', "<header>",
             f"<h1>{e(head['name'])}</h1>", '<div class="sub">',
             f"<span><b>{head['tracked']}</b> tracked files</span>",
             f"<span><b>{head['source']}</b> source</span>",
             f"<span>tier <b>{e(head['tier'])}</b></span>",
             f"<span>{datetime.date.today().isoformat()}</span>",
             "</div></header>",
             f'<div class="ran">{e(head["ran"])}</div>']

    for d in dims:
        parts.append("<section>")
        parts.append('<div class="dh">'
                     f'<span class="n">{d["n"]}</span>'
                     f'<h2>{e(d["name"])}</h2></div>')
        parts.append(f'<div class="q">{e(d["question"])}</div>')
        abst = " abst" if d["state"] == "abstained" else ""
        label = ("Could not judge — " if d["state"] == "abstained" else "")
        parts.append(f'<div class="head{abst}">{e(label)}{e(d["headline"])}</div>')
        if d["rows"]:
            parts.append("<table>")
            for row in sorted(d["rows"],
                              key=lambda r: FLAG_ORDER.get(r["flag"], 9)):
                note = (f'<span class="note">{e(row["note"])}</span>'
                        if row.get("note") else "")
                parts.append(
                    f'<tr><td class="f"><span class="dot {e(row["flag"])}">'
                    f'</span></td>'
                    f'<td class="l">{e(row["label"])}</td>'
                    f'<td class="v">{e(str(row["value"]))}{note}</td></tr>')
            parts.append("</table>")
        parts.append("</section>")

    if cannot_say:
        parts.append('<div class="cannot"><h3>What this page cannot say</h3>'
                     "<ol>")
        for q in cannot_say:
            parts.append(f"<li>{e(q)}</li>")
        parts.append("</ol></div>")

    parts.append(
        "<footer>Every line above is measured, not judged. Token figures are "
        "characters over four — the same approximation Claude Code uses, and "
        "reproducible offline. A dimension that could not be judged says so "
        "and is never scored as a zero.</footer>")
    parts.append("</div>")
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{e(head['name'])} — assessment</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        + "\n".join(parts)
        + "\n</body>\n</html>\n")


def write_html(path, head, dims, cannot_say):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_page(head, dims, cannot_say))
    return os.path.abspath(path)
