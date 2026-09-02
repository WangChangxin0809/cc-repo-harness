# shared/scripts/ — this is payload

This is hard rule 1, at the point it's actually read. Everything here is
**written for a repository you have never seen**. You are not
editing our tooling; you are editing a stranger's. Two ways that happens, and
the difference decides what you may depend on:

| | Reaches a stranger by | Examples |
|---|---|---|
| **copied** | `scaffold.py`'s `COPY` table writes it into their tree | `gates/` `guards/` `index/` `context/` |
| **run from here** | the plugin runs it against their repo | `probe_repo.py` `drift.py` `assess/` |

Copied code has to keep working after this plugin is uninstalled, so it may
depend on nothing but the tree it lands in. Code run from here may import its
siblings, and must discover the *subject* repository's shape rather than expect
it to match ours -- `probe_repo.py` looked for gates under `scripts/gates` and
reported this repository's own as absent, which is the failure this distinction
exists to prevent.

A diagnostic is not repository behaviour and does not belong in `COPY`.
Uninstalling the plugin must not change what a repository *does*, and a repo
that never asked for a per-commit defect replay should not find one in its tree.

(This file is neither: `COPY` takes `.py` only, so the note you are reading
stays here. It is the one thing in this directory written for us.)

- Write for a repository you have never seen. No path, name, or convention from
  this repository may be assumed.
- Standard library only, Python 3.9+. A target repository installs nothing to
  run these, and CI holds that by running the floor and the ceiling.
- Exit 2 means COULD NOT JUDGE. A check that cannot see its subject says so and
  returns 2; it never returns 0.
- A tool only *we* need does not belong here, however convenient the directory
  is. `check_plugin_structure.py` is the standing exception and it is a mistake
  being carried, not a precedent: it checks a `.claude-plugin/`, which almost no
  target repository has, so it ships commented out of the generated `ci.sh`.

`scaffold.py`'s `COPY` table decides what lands where. If you add a directory
here, that table is the thing that has to know about it.
