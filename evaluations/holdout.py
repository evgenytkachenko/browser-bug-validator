"""Local author-visible consume-once ledger, not a blind or tamper-proof holdout.

Reserve before evaluation. Consumption happens BEFORE the first trial and is
never rolled back, including on crash. Deleting/copying the ledger defeats this
local guard; independent custody is needed for stronger claims.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from bug_validator.common import digest, file_digest
from .general_integrity import read_json, validate_sources


def split_identity(tasks):
    if not tasks or any(t.get('split') != 'reserved-transfer' for t in tasks):
        raise ValueError('Only the complete reserved-transfer split can be reserved')
    from .general_tasks import TASKS
    expected = sorted((t for t in TASKS if t['split'] == 'reserved-transfer'), key=lambda t: t['id'])
    if sorted(tasks, key=lambda t: t['id']) != expected:
        raise ValueError('Reservation requires the complete current canonical reserved split')
    return digest(expected)


def freeze_binding(manifest):
    validate_sources(manifest.get('sources'))
    if manifest.get('source_frozen_through_run') is not True or manifest.get('model_identity_stable') is not True:
        raise ValueError('Reservation requires a source-frozen, identity-stable development run')
    if manifest.get('integrity_version') == 1 and manifest.get('completed') is not True:
        raise ValueError('Development run is incomplete')
    if manifest.get('split') != 'development':
        raise ValueError('Freeze must precede exposure in a development run')
    return {key: manifest.get(key) for key in ('sources', 'backend', 'model_config_sha256', 'browser_config_sha256', 'model_identity_before')}


@contextmanager
def ledger_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError('Ledger is locked; inspect interrupted operation before recovery') from exc
    try:
        os.close(fd)
        if path.is_symlink():
            raise ValueError('Ledger must not be a symlink')
        yield path
    finally:
        lock.unlink()


def _load(path):
    ledger = read_json(path) if path.exists() else {'schema_version': 1, 'reservations': {}}
    if ledger.get('schema_version') != 1 or not isinstance(ledger.get('reservations'), dict):
        raise ValueError('Invalid holdout ledger')
    return ledger


def _save(path, ledger):
    temporary = path.with_name(path.name + '.pending')
    # Exclusive creation prevents following an attacker-supplied temporary symlink.
    with temporary.open('x') as stream:
        json.dump(ledger, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def reserve(path, frozen_manifest, tasks):
    from .general_integrity import load_general_run
    frozen_manifest = Path(frozen_manifest)
    if frozen_manifest.name != 'manifest.json':
        raise ValueError('Freeze must name a complete run manifest.json')
    manifest, _ = load_general_run(frozen_manifest.parent)
    binding = freeze_binding(manifest)
    key = split_identity(tasks)
    with ledger_lock(path) as path:
        ledger = _load(path)
        if key in ledger['reservations']:
            raise ValueError('This split is already reserved or exposed; cannot reserve again')
        entry = {'split_sha256': key, 'task_ids': sorted(t['id'] for t in tasks),
                 'status': 'reserved', 'reserved_unix': time.time(), 'binding': binding,
                 'frozen_manifest_sha256': file_digest(frozen_manifest),
                 'qualification': 'author-visible local reservation; not blind or tamper-proof'}
        ledger['reservations'][key] = entry
        _save(path, ledger)
    return entry


def consume(path, tasks, binding, frozen_manifest_sha256, run_directory):
    key = split_identity(tasks)
    with ledger_lock(path) as path:
        ledger = _load(path)
        entry = ledger['reservations'].get(key)
        if not entry or entry.get('status') != 'reserved':
            raise ValueError('Reserved split missing or already exposed/consumed')
        if entry.get('binding') != binding or entry.get('frozen_manifest_sha256') != frozen_manifest_sha256:
            raise ValueError('Source, model, config, or frozen manifest changed after reservation')
        entry.update(status='consumed', exposed_unix=time.time(), run_directory=str(Path(run_directory).absolute()))
        _save(path, ledger)
    return entry


def mark_exposed(path, tasks, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Exposure requires a reason')
    key = split_identity(tasks)
    with ledger_lock(path) as path:
        ledger = _load(path)
        entry = ledger['reservations'].setdefault(key, {'split_sha256': key, 'task_ids': sorted(t['id'] for t in tasks)})
        entry.update(status='exposed', exposed_unix=time.time(), reason=reason)
        _save(path, ledger)
    return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['reserve', 'mark-exposed'])
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--frozen-manifest', type=Path)
    parser.add_argument('--reason')
    parser.add_argument('--acknowledge-author-visible-holdout', action='store_true')
    args = parser.parse_args(argv)
    if not args.acknowledge_author_visible_holdout:
        parser.error('Acknowledge the split is author-visible, not blind')
    from .general_tasks import TASKS
    tasks = [t for t in TASKS if t['split'] == 'reserved-transfer']
    try:
        if args.command == 'reserve':
            if not args.frozen_manifest:
                parser.error('reserve requires --frozen-manifest')
            entry = reserve(args.ledger, args.frozen_manifest, tasks)
        else:
            entry = mark_exposed(args.ledger, tasks, args.reason)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(entry, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
