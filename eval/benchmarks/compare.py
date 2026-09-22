#!/usr/bin/env python3
"""Compare complete memory benchmark evidence from the same harness/environment."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from protocol import compare_reports, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('head', type=Path)
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_reports(read_json(args.base), read_json(args.head))
    except (OSError, ValueError, TypeError) as exc:
        result = {'code': 2, 'markdown': '# Offline memory benchmark comparison\n\nCould not judge: %s\n' % exc}
    if args.summary:
        try:
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_text(result['markdown'], encoding='utf-8')
        except OSError as exc:
            print('could not write benchmark summary: ' + str(exc), file=sys.stderr)
            return 2
    print(result['markdown'], end='')
    return result['code']


if __name__ == '__main__':
    sys.exit(main())
