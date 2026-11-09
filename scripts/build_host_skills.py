#!/usr/bin/env python3
"""Build two self-contained project-local host adapters; never edit host settings.

The canonical skill is portable. This helper adds a host marker, keeps Codex UI
metadata only in the Codex copy, and records owned content hashes. It refuses
unrecognized or locally edited destinations instead of overwriting them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

NAME = 'browser-bug-validator-host'
ROOT = Path(__file__).resolve().parents[1]
MARKER = '.generated.json'
GENERATOR = 'browser-bug-validator-host-adapters-v1'
HOSTS = {'codex': '.agents', 'claude': '.claude'}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_symlink_path(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'Symlink path is not permitted: {part}')


def read_tree(path: Path) -> dict[str, bytes]:
    reject_symlink_path(path)
    if not path.is_dir():
        raise ValueError(f'Not a real directory: {path}')
    result = {}
    for file in sorted(path.rglob('*')):
        if file.is_symlink():
            raise ValueError(f'Symlink content is not permitted: {file}')
        if file.is_dir():
            continue
        if not file.is_file():
            raise ValueError(f'Not a regular file: {file}')
        result[file.relative_to(path).as_posix()] = file.read_bytes()
    return result


def expected_tree(root: Path, host: str) -> dict[str, bytes]:
    if host not in HOSTS:
        raise ValueError('Unsupported host')
    source = read_tree(root / 'skills' / NAME)
    if 'SKILL.md' not in source or MARKER in source:
        raise ValueError('Canonical source must have SKILL.md and no generated marker')
    if host == 'claude':
        source = {name: data for name, data in source.items() if not name.startswith('agents/')}
    suffix = (
        '\n## Packaged host\n\n'
        + ('This is the Codex project adapter. Use the Codex section of '
           if host == 'codex' else 'This is the Claude Code project adapter. Use the Claude Code section of ')
        + '[the host reference](references/hosts.md).\n'
    )
    source['SKILL.md'] += suffix.encode('utf-8')
    manifest = {'generator': GENERATOR, 'host': host,
                'files': {name: sha256(data) for name, data in source.items()}}
    source[MARKER] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    return source


def validate_owned_tree(path: Path, host: str, expected: dict[str, bytes]) -> None:
    actual = read_tree(path)
    if MARKER not in actual:
        raise ValueError(f'Unrecognized existing skill; refusing overwrite: {path}')
    try:
        manifest = json.loads(actual[MARKER])
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'Invalid generated ownership marker: {path}') from exc
    if (not isinstance(manifest, dict) or manifest.get('generator') != GENERATOR
            or manifest.get('host') != host or not isinstance(manifest.get('files'), dict)):
        raise ValueError(f'Unrecognized generated ownership marker: {path}')
    recorded = manifest['files']
    if set(actual) != set(recorded) | {MARKER}:
        raise ValueError(f'Extra or missing local files; refusing overwrite: {path}')
    if any(sha256(actual[name]) != checksum for name, checksum in recorded.items()):
        raise ValueError(f'Local edits detected; refusing overwrite: {path}')
    if set(actual) - set(expected):
        raise ValueError(f'Generated source removal needs manual review: {path}')


def build(root: Path, *, write: bool = False) -> list[str]:
    root = Path(root).absolute()
    reject_symlink_path(root)
    plans = []
    for host, folder in HOSTS.items():
        target = root / folder / 'skills' / NAME
        reject_symlink_path(target)
        expected = expected_tree(root, host)
        if target.exists():
            validate_owned_tree(target, host, expected)
            if not write and read_tree(target) != expected:
                raise ValueError(f'Generated adapter is stale: {target}')
        elif not write:
            raise ValueError(f'Generated adapter is missing: {target}')
        plans.append((target, expected))
    # Preflight both destinations before changing either.
    if write:
        for target, expected in plans:
            target.mkdir(parents=True, exist_ok=True)
            for name, data in expected.items():
                file = target / name
                reject_symlink_path(file)
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
    return [str(target.relative_to(root)) for target, _ in plans]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Read-only consistency check')
    mode.add_argument('--write', action='store_true', help='Build the two repository-local adapters')
    args = parser.parse_args(argv)
    try:
        paths = build(ROOT, write=args.write)
        print(json.dumps({'status': 'written' if args.write else 'consistent', 'paths': paths}))
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
