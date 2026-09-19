#!/usr/bin/env bash
set -euo pipefail

git init -q
git config core.hooksPath /dev/null
cat > README.md <<'EOF'
# Bluefin Counter

Bluefin Counter is a tiny teaching service that increments integer values.
EOF
git add README.md
git -c user.name=fixture -c user.email=fixture@example.invalid commit -qm fixture
