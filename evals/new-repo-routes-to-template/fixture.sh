#!/usr/bin/env bash
set -euo pipefail

git init -q
git config core.hooksPath /dev/null
printf '# New project\n' > README.md
git add README.md
git -c user.name=fixture -c user.email=fixture@example.invalid commit -qm fixture
