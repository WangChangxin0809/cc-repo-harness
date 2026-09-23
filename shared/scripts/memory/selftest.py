#!/usr/bin/env python3
"""Run memory's real-Git contracts without the installation plugin."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest


def main():
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))
    suite = unittest.defaultTestLoader.discover(str(here), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2 if '--verbose' in sys.argv else 1).run(suite)
    if result.skipped:
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
