#!/usr/bin/env python3
"""Guard: block writing a credential into a file the repository will keep.

A secret that reaches a commit stays in the commit. Deleting it in the next
change removes it from the working tree and from nothing else: it is in the
history, in every clone, in every fork, and in whatever mirrored the push
before anyone noticed. The only real remedy is to rotate the credential, which
is somebody else's afternoon.

That makes it the same class as a destructive delete -- complete at the moment
it happens, invisible to every later check -- and the same asymmetry applies: a
false block costs a sentence, a miss costs a rotation.

## Two rules, and why neither is "does the value look real"

The obvious detector scores the *value*: entropy, character classes, length.
It cannot work here, because the value that most needs blocking is the one a
person pasted without thinking, and the value most likely to be a placeholder
is a long random-looking string in an example file. Worse, this project's own
dimension-1 probe writes `EXAMPLE-NOT-A-REAL-SECRET-0000`, which every entropy
detector correctly reads as a placeholder -- and it is exactly the write that
must be refused.

So the rules are about **shape** and **destination**, both of which are
visible without guessing:

**A credential format, anywhere.** `AKIA...`, `ghp_...`, a PEM private key
header, a Slack token. These strings are not ambiguous; nothing else looks
like them, and there is no legitimate reason for one to arrive through a file
write.

**A secrets filename with a value in it.** `.env`, `credentials`, `id_rsa`,
`*.pem`. The name is the convention that says *this file holds the real
thing*, and `.env.example`, `.env.sample`, `.env.template` and `.env.dist` are
the convention that says it does not -- so they are excluded by name rather
than by inspecting what is in them.

## What this deliberately does not do

Read `.gitignore`. A guard sees one tool call, not a repository, and a file
being ignored today says nothing about the line somebody adds to `git add -f`
tomorrow. The check is the same either way and the reason text says how to
proceed.
"""

from __future__ import annotations

import os
import re

# Formats that are only ever one thing. Kept short on purpose: every entry
# here has to be a string that cannot occur by accident.
_FORMATS = (
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "an AWS temporary access key id"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "a private key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"), "a GitHub personal access token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"), "a GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "a Slack token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "an API secret key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "a Google API key"),
)

# Names that mean "the real thing lives here".
_SECRET_NAMES = ("credentials", "id_rsa", "id_ed25519", "id_dsa",
                 ".netrc", ".pgpass", "secrets.yml", "secrets.yaml",
                 "secrets.json", "service-account.json")
_SECRET_SUFFIX = (".pem", ".key", ".p12", ".pfx", ".jks")

# ...and the names that mean the opposite. Checked first.
_NOT_SECRET = (".example", ".sample", ".template", ".dist", ".md", ".rst",
               ".txt.example", ".lock")

# `KEY=value` / `KEY: value`, with something after it. A key with nothing
# after the separator is a template line and is left alone.
_ASSIGNED = re.compile(
    r"^[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*[=:][ \t]*"
    r"(?!$)(?![\"']?[<{$])[\"']?\S", re.M)

REASON_FORMAT = """\
Blocked: this writes {what} into {path}.

A secret that reaches a commit is in the history, in every clone and in every
fork, and removing it later removes it from the working tree only. The remedy
is to rotate the credential, not to edit the file.

Put the value where the repository does not keep it:
    export {var}=...              # the environment, for this shell
    <a secret manager, or your CI's secret store>

and reference it by name in the file:
    {var}=${{{var}}}
"""

REASON_FILENAME = """\
Blocked: `{name}` is where the real credential lives, and this writes a value into it.

The name is the convention that says this file holds the actual secret. If it
reaches a commit -- through `git add -f`, through a `.gitignore` somebody
edited, through a new clone that never had one -- it is in the history for
good, and the fix is a rotation rather than a revert.

Two ways forward:
    {name}.example                # commit the shape, with placeholders
    <write {name} yourself, outside this session>

A placeholder is fine here and is not blocked:
    {var}=<your key here>
"""


def _basename(path: str) -> str:
    return os.path.basename((path or "").replace("\\", "/"))


def _is_secret_file(path: str) -> bool:
    name = _basename(path).lower()
    if any(name.endswith(x) for x in _NOT_SECRET):
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    if name in _SECRET_NAMES:
        return True
    return any(name.endswith(x) for x in _SECRET_SUFFIX)


def _first_var(body: str) -> str:
    m = re.search(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*[=:]",
                  body or "", re.M)
    return m.group(1) if m else "SECRET"


def check(tool_name: str, tool_input: dict) -> str | None:
    if tool_name not in ("Write", "Edit", "NotebookEdit"):
        return None
    path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
    body = (tool_input.get("content")
            or tool_input.get("new_string")
            or tool_input.get("new_source") or "")

    for pattern, what in _FORMATS:
        if pattern.search(body):
            return REASON_FORMAT.format(what=what, path=_basename(path) or path,
                                        var=_first_var(body))
    if _is_secret_file(path) and _ASSIGNED.search(body):
        return REASON_FILENAME.format(name=_basename(path),
                                      var=_first_var(body))
    return None


CASES = [
    # The probe: a value written into the file whose name means "the real one".
    ("Write", {"file_path": "/repo/.env",
               "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-NOT-A-REAL-SECRET-0000"},
     True),
    ("Write", {"file_path": "config/credentials",
               "content": "password: hunter2\n"}, True),
    ("Write", {"file_path": "deploy/server.pem",
               "content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n"}, True),
    # A format nothing else produces, wherever it lands.
    ("Write", {"file_path": "src/config.py",
               "content": "KEY = 'AKIAIOSFODNN7EXAMPLE'\n"}, True),
    ("Edit", {"file_path": "README.md", "old_string": "",
              "new_string": "token: ghp_" + "a" * 36}, True),
    # Near misses. The twin of the probe is first, and it is the one that
    # decides whether this guard is worth having: a repository that cannot
    # commit its own .env.example has been made worse, not safer.
    ("Write", {"file_path": "/repo/.env.example",
               "content": "AWS_SECRET_ACCESS_KEY=<your key here>"}, False),
    ("Write", {"file_path": ".env.sample",
               "content": "DATABASE_URL=${DATABASE_URL}\n"}, False),
    ("Write", {"file_path": ".env.template", "content": "API_KEY=\n"}, False),
    # A template line with nothing after the separator.
    ("Write", {"file_path": ".env", "content": "API_KEY=\nDB_HOST=\n"}, False),
    # Prose about secrets is not a secret. This is the failure this project
    # hit three separate times in other checks: text *about* X read as X.
    ("Write", {"file_path": "docs/security.md",
               "content": "Never commit AWS_SECRET_ACCESS_KEY to the repo.\n"},
     False),
    ("Write", {"file_path": "guide/setup.md",
               "content": "Set `GITHUB_TOKEN` in your shell before running.\n"},
     False),
    ("Write", {"file_path": "src/main.py",
               "content": "def add(a, b):\n    return a + b\n"}, False),
    ("Bash", {"command": "cat .env"}, False),
    ("Read", {"file_path": ".env"}, False),
]
