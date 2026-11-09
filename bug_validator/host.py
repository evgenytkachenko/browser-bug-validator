"""Drive the unchanged bounded browser controller with the existing host agent.

Start serve in a background tool/job. Poll next; submit a JSON decision to exactly
one request. No Ollama, model API, paid service, or global host config is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .general import run_agent
from .host_protocol import HostDecisionSource, read_json, read_status, submit


def serve(run_dir, bug, knowledge_base, authorization, *, host, browser_config=None,
          decision_origin='host-session', session_label=None):
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=False)
    source = HostDecisionSource(root, host=host, decision_origin=decision_origin, session_label=session_label)
    return run_agent(bug, knowledge_base, authorization, root / 'agent',
                     browser_config=browser_config, host_source=source)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    run = subs.add_parser('serve', help='Hold the real browser in one controller process')
    run.add_argument('--run-dir', type=Path, required=True)
    run.add_argument('--bug', type=Path, required=True)
    run.add_argument('--kb', type=Path, required=True)
    run.add_argument('--authorization', type=Path, required=True)
    run.add_argument('--browser-config', type=Path)
    run.add_argument('--host', choices=['codex', 'claude', 'other'], required=True)
    run.add_argument('--session-label', help='Optional audit label, not proof of host/model identity')
    run.add_argument('--decision-origin', choices=['host-session', 'scripted-control'], default='host-session')
    nxt = subs.add_parser('next', help='Read current request/status without advancing the browser')
    nxt.add_argument('--run-dir', type=Path, required=True)
    send = subs.add_parser('submit', help='Submit exactly one host-selected decision')
    send.add_argument('--run-dir', type=Path, required=True)
    send.add_argument('--request-id', required=True)
    send.add_argument('--decision', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            report = serve(args.run_dir, read_json(args.bug, 24000), read_json(args.kb, 32000),
                           read_json(args.authorization, 48000), host=args.host,
                           browser_config=read_json(args.browser_config, 16000) if args.browser_config else None,
                           decision_origin=args.decision_origin, session_label=args.session_label)
            print(json.dumps({'state': 'completed', 'verdict': report['verdict'], 'report': str(args.run_dir / 'agent/report.json')}))
            return 2 if report['verdict'] == 'inconclusive' else 0
        if args.command == 'next':
            result = read_status(args.run_dir)
        else:
            result = submit(args.run_dir, args.request_id, read_json(args.decision, 12000))
        print(json.dumps(result, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'state': 'error', 'error': f'{type(exc).__name__}: {str(exc)[:1500]}'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
