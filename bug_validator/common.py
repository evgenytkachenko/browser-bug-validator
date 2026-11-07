from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

class ValidationError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def loopback_origin(url):
    try:
        p = urlsplit(url)
        port = p.port
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid local origin") from exc
    if p.scheme != "http" or p.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValidationError("Only explicit HTTP loopback fixture origins are supported")
    if p.username or p.password or p.query or p.fragment or p.path not in {"", "/"} or port is None:
        raise ValidationError("Origin must contain an explicit port and no credentials, query, or path")
    return f"http://{('[' + p.hostname + ']') if ':' in p.hostname else p.hostname}:{port}"

def validate_bug(bug, base_url):
    if not isinstance(bug, dict):
        raise ValidationError("Bug report must be an object")
    for field in ("id", "title", "description"):
        if not isinstance(bug.get(field), str) or not bug[field].strip() or len(bug[field]) > 12000:
            raise ValidationError(f"Missing or invalid bug field: {field}")
    target = bug.get("target_task_id")
    if not isinstance(target, str) or not re.fullmatch(r"T-[0-9]{1,6}", target):
        raise ValidationError("Missing or invalid target_task_id; do not guess which task to modify")
    status = bug.get("expected_status")
    if not isinstance(status, str) or status not in {"todo", "doing", "done"}:
        raise ValidationError("Missing or unsupported expected_status")
    origin = loopback_origin(base_url)
    auth = bug.get("authorization", {})
    if not isinstance(auth, dict) or auth.get("origin") != origin:
        raise ValidationError("Explicit authorization must name the exact fixture origin")
    allowed_ids = auth.get("allowed_task_ids")
    if (not isinstance(allowed_ids, list) or len(allowed_ids) > 20
        or not all(isinstance(value, str) and re.fullmatch(r"T-[0-9]{1,6}", value) for value in allowed_ids)):
        raise ValidationError("allowed_task_ids must be a bounded list of exact task IDs")
    if target not in allowed_ids:
        raise ValidationError("Target task is outside the authorized mutation scope")
    actions = auth.get("allowed_actions")
    if (not isinstance(actions, list) or len(actions) > 10 or not all(isinstance(value, str) for value in actions)
        or not {"select_status", "save", "reload"}.issubset(set(actions))):
        raise ValidationError("Authorization must permit select_status, save, and reload in a list of actions")
    return origin

WORKFLOW = ["observe_initial", "select_status", "save", "observe_saved", "reload", "observe_reloaded"]

def validate_entry(entry, target):
    if entry.get("id") != "task-status-persistence" or entry.get("route") != "/":
        raise ValidationError("Unsupported journey; v0.1 supports only the fictional task-status workflow")
    if entry.get("workflow") != WORKFLOW:
        raise ValidationError("Knowledge-base workflow is unsupported or changed; review before running")
    selectors = entry.get("selectors", {})
    required = {"ready", "blocked", "row", "status", "save", "persisted"}
    if set(selectors) != required:
        raise ValidationError("Knowledge-base selectors are incomplete")
    exact = {"ready": "board-ready", "blocked": "access-blocked", "row": "task-row-{task_id}",
             "status": "task-status-{task_id}", "save": "save-task-{task_id}", "persisted": "persisted-status-{task_id}"}
    if selectors != exact:
        raise ValidationError("Selectors do not match the reviewed task-board adapter; review new selectors before running")
    resolved = {}
    for key, value in selectors.items():
        if not isinstance(value, str):
            raise ValidationError("Selectors must be data-testid strings")
        value = value.replace("{task_id}", target)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
            raise ValidationError("Only bounded data-testid selectors are supported")
        resolved[key] = value
    return resolved
