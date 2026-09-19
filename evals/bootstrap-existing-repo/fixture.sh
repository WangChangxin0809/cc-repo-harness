#!/usr/bin/env bash
set -euo pipefail

git init -q
git config core.hooksPath /dev/null
mkdir -p src tests
cat > src/counter.py <<'PY'
def increment(value):
    return value + 1
PY
cat > tests/test_counter.py <<'PY'
import unittest
from src.counter import increment

class CounterTest(unittest.TestCase):
    def test_increment(self):
        self.assertEqual(increment(3), 4)

if __name__ == "__main__":
    unittest.main()
PY
cat > CLAUDE.md <<'EOF'
# Tiny counter

PROJECT_SENTINEL: preserve-this-line
Run tests with: python3 -m unittest discover -s tests
EOF
git add .
git -c user.name=fixture -c user.email=fixture@example.invalid commit -qm fixture
