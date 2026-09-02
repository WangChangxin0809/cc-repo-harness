---
paths:
  - "**/*.py"
  - "**/*.sh"
  - "**/*.js"
  - "**/*.ts"
  - "**/*.mjs"
  - "**/*.go"
  - "**/*.rs"
---

# A comment earns its line or it goes

Two failures, and only one of them looks like a mistake while you are writing
it.

**Trivial.** The comment says what the line already says. `# increment i`,
`# open the file`, a docstring that repeats the signature, a banner over a
section whose name is the next line. It costs a read and settles nothing.

**Excessive.** The comment is true, load-bearing somewhere, and not here — the
same argument made three times in one file, a paragraph of history above a
two-line helper, the decision record pasted in rather than pointed at.

The test, applied to the comment you just wrote: **if the line below changed,
would this have to change too?** A comment that tracks the code is describing
it. A comment that survives the change is carrying something the code cannot —
why this and not the obvious alternative, what broke that made it necessary,
where the constant's number came from, the trap the next reader will walk into.
Keep that one. Say it once, next to the line it is about.

Reasoning that outgrows a few lines is a decision record; a procedure is a
skill. A comment that is really either of those goes there, and leaves a
pointer.
