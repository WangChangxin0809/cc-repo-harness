"""Local operator inspection and explicitly approved external-drift reconciliation."""
import argparse, json, sys
try:
    from .store import Room
    from .workspace import Workspace
    from .localio import read_bytes, sha
except ImportError:
    from store import Room
    from workspace import Workspace
    from localio import read_bytes, sha

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default='.')
    ap.add_argument('--backend', choices=['rga', 'pycrdt'], default='rga')
    sub = ap.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    sub.add_parser('export-events').add_argument('--after', type=int, default=0)
    r = sub.add_parser('reconcile')
    r.add_argument('path'); r.add_argument('--choose', choices=['room', 'disk'], required=True)
    r.add_argument('--expected-sha'); r.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    try:
        room = Room(a.root, name='operator')
        workspace = Workspace(room, a.backend)
        if a.action == 'status':
            result = workspace.status()
        elif a.action == 'export-events':
            result = room.read(a.after, 100)
        else:
            digest = sha(read_bytes(room.root / room.path_key(a.path)))
            result = {'apply': a.apply, 'observed_disk_sha': digest, 'strategy': a.choose}
            if a.apply:
                if a.expected_sha != (digest or 'absent'):
                    raise ValueError('pass the reviewed --expected-sha (or absent) explicitly')
                result = workspace.reconcile(a.path, a.choose, digest)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except Exception as exc:
        print(f'could not judge: {exc}', file=sys.stderr); return 2

if __name__ == '__main__':
    sys.exit(main())
