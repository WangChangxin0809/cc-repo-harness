# shared/scripts/ — this is payload

Every `.py` under this directory is **copied into other people's repositories**
by `scaffold.py`. You are not editing our tooling; you are editing a stranger's.

(This file is not: `COPY` takes `.py` only, so the note you are reading stays
here. It is the one thing in this directory written for us.)

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
