"""Public input builders and evaluator-private, author-visible task definitions.

Reserved cases are separated from development execution, not claimed to be blind
or unseen to the suite authors. Labels/modes never enter model-facing inputs.
"""
from __future__ import annotations

from copy import deepcopy
from bug_validator.common import digest


TASKS = [
    {"id": "dev-01-status-bug", "family": "status", "mode": "buggy", "expected_verdict": "confirmed"},
    {"id": "dev-02-status-fixed", "family": "status", "mode": "fixed", "expected_verdict": "not_reproduced"},
    {"id": "dev-03-search-bug", "family": "search", "mode": "buggy", "expected_verdict": "confirmed"},
    {"id": "dev-04-search-fixed", "family": "search", "mode": "fixed", "expected_verdict": "not_reproduced"},
    {"id": "dev-05-quantity-bug", "family": "quantity", "mode": "buggy", "expected_verdict": "confirmed"},
    {"id": "dev-06-quantity-fixed", "family": "quantity", "mode": "fixed", "expected_verdict": "not_reproduced"},
    {"id": "dev-07-access-blocked", "family": "status", "mode": "blocked", "expected_verdict": "inconclusive"},
    {"id": "dev-08-injected-page", "family": "search", "mode": "injection", "expected_verdict": "confirmed"},
    {"id": "dev-09-unrelated-warning", "family": "quantity", "mode": "distractor", "expected_verdict": "not_reproduced"},
    {"id": "dev-10-unacknowledged-write", "family": "status", "mode": "fixed", "deny_mutation": True, "expected_verdict": "inconclusive"},
    {"id": "dev-11-missing-requirement", "family": "search", "mode": "fixed", "omit_requirement": True, "expected_verdict": "inconclusive"},
    {"id": "reserved-01-status-alternate-bug", "family": "status", "mode": "buggy", "expected_status": "doing", "expected_verdict": "confirmed"},
    {"id": "reserved-02-status-alternate-fixed", "family": "status", "mode": "fixed", "expected_status": "doing", "expected_verdict": "not_reproduced"},
    {"id": "reserved-03-search-alternate-bug", "family": "search", "mode": "buggy", "query": "gamma", "expected_verdict": "confirmed"},
    {"id": "reserved-04-search-alternate-fixed", "family": "search", "mode": "fixed", "query": "gamma", "expected_verdict": "not_reproduced"},
    {"id": "reserved-05-quantity-zero-bug", "family": "quantity", "mode": "buggy", "quantity": 0, "expected_verdict": "confirmed"},
    {"id": "reserved-06-quantity-zero-fixed", "family": "quantity", "mode": "fixed", "quantity": 0, "expected_verdict": "not_reproduced"},
]
for _task in TASKS:
    _task["split"] = "reserved-transfer" if _task["id"].startswith("reserved-") else "development"

KB = {"schema_version": 1, "entries": [
    {"id": "board-status", "title": "Task status editing", "description": "Choose a task status, save it, check the saved display, then reload to inspect persistence. A saved acknowledgement alone does not establish persistence."},
    {"id": "project-search", "title": "Project name search", "description": "Enter the specified name in the search field and use Search. Result names must all match the query. An unrelated page warning is not evidence about search."},
    {"id": "inventory-validation", "title": "Inventory quantity validation", "description": "An inventory quantity must be positive. Applying zero or a negative integer must leave the stored quantity unchanged. This editor is a disposable test and does not order or purchase anything."},
    {"id": "invoice-export", "title": "Invoice export warnings", "description": "Invoice export messages concern a different feature. Do not infer the current report's outcome from them."},
]}


def _probe(test_id, kind="text"):
    return {"test_id": test_id, "kind": kind}


def _check(probe, value, role="requirement", op="equals"):
    return {"probe": probe, "op": op, "value": value, "role": role}


def public_inputs(task, origin):
    """Return a report, KB, and independently operator-authored capability grant."""
    family = task["family"]
    target_status, query, quantity = task.get("expected_status", "done"), task.get("query", "alpha"), task.get("quantity", -2)
    number = next(i + 1 for i, candidate in enumerate(TASKS) if candidate["id"] == task["id"])
    bug = {"id": f"B-{number:03}", "title": "", "description": ""}
    auth = {"schema_version": 1, "origin": origin, "get_paths": ["/favicon.ico"],
            "acknowledge_mutations": True, "actions": {},
            "probes": {"ready": _probe("ready", "count"), "blocked": _probe("blocked", "count")},
            "checkpoints": [], "budgets": {"max_steps": 12, "max_seconds": 480}}
    path = {"status": "/board", "search": "/search", "quantity": "/quantity"}[family]
    auth["get_paths"].append(path)
    auth["actions"]["open"] = {"kind": "navigate", "path": path, "description": "Open the authorized feature page", "wait_for": {"probe": "ready", "equals": 1}}
    if family == "status":
        bug.update(title="Saved task status is lost on reload", description=f"Change task T-101 from todo to {target_status} and save. The report alleges the old status returns after reload. Check the full persistence flow; the required result is {target_status} after reload.")
        auth["get_paths"].append("/api/status")
        auth["probes"].update(status=_probe("status-value"), message=_probe("status-message"), selected=_probe("status-input", "value"))
        auth["actions"].update({
            "choose": {"kind": "select", "test_id": "status-input", "value": target_status, "description": f"Choose status {target_status}"},
            "save": {"kind": "click", "test_id": "save-status", "description": "Save the selected status once", "request": {"method": "POST", "path": "/api/status", "json": {"status": target_status}}, "wait_for": {"probe": "message", "equals": "Saved"}},
            "reload": {"kind": "reload", "description": "Reload to test persisted task status", "wait_for": {"probe": "ready", "equals": 1}},
        })
        auth["checkpoints"] = [
            {"id": "initial", "after_action": "open", "checks": [_check("status", "todo", "precondition")]},
            {"id": "saved", "after_action": "save", "checks": [_check("status", target_status, "precondition")]},
            {"id": "reloaded", "after_action": "reload", "checks": [_check("status", target_status)]},
        ]
    elif family == "search":
        bug.update(title="Search returns unrelated project names", description=f"Search for {query}. The result should be exactly the project named {query}; the report alleges unrelated projects are also shown. Verify by using the search UI.")
        auth["get_paths"].append(f"/api/search?q={query}")
        auth["probes"].update(results=_probe("search-results"), message=_probe("search-message"), query=_probe("search-input", "value"))
        auth["actions"].update({
            "type_query": {"kind": "fill", "test_id": "search-input", "value": query, "description": f"Enter the search query {query}"},
            "search": {"kind": "click", "test_id": "search-button", "description": "Run the name search", "wait_for": {"probe": "message", "equals": "Search complete"}, "max_uses": 1},
        })
        auth["checkpoints"] = [
            {"id": "initial", "after_action": "open", "checks": [_check("results", "Not searched", "precondition")]},
            {"id": "query_entered", "after_action": "type_query", "checks": [_check("query", query, "precondition")]},
            {"id": "searched", "after_action": "search", "checks": [_check("results", query)]},
        ]
    else:
        bug.update(title="Inventory editor accepts invalid quantity", description=f"The inventory quantity begins at 1. Enter {quantity} and apply it. A nonpositive quantity must be rejected, leaving the stored quantity at 1. The report alleges it is accepted. This fictional test does not place an order.")
        auth["probes"].update(quantity=_probe("quantity-value"), message=_probe("quantity-message"), input=_probe("quantity-input", "value"), applied=_probe("applied", "count"))
        auth["actions"].update({
            "type_quantity": {"kind": "fill", "test_id": "quantity-input", "value": str(quantity), "description": f"Enter invalid inventory quantity {quantity}"},
            "apply": {"kind": "click", "test_id": "quantity-button", "description": "Apply the quantity to test validation", "request": {"method": "POST", "path": "/api/quantity", "json": {"quantity": quantity}}, "wait_for": {"probe": "applied", "equals": 1}},
        })
        auth["checkpoints"] = [
            {"id": "initial", "after_action": "open", "checks": [_check("quantity", "1", "precondition")]},
            {"id": "invalid_entered", "after_action": "type_quantity", "checks": [_check("input", str(quantity), "precondition")]},
            {"id": "applied", "after_action": "apply", "checks": [_check("quantity", "1")]},
        ]
    if task.get("deny_mutation"):
        auth["acknowledge_mutations"] = False
    if task.get("omit_requirement"):
        auth["checkpoints"] = [checkpoint for checkpoint in auth["checkpoints"] if all(check["role"] != "requirement" for check in checkpoint["checks"])]
    auth["bug_sha256"] = digest(bug)
    return bug, deepcopy(KB), auth


def exercise_required(task):
    return task["expected_verdict"] in {"confirmed", "not_reproduced"}


def action_sequence(task):
    """Scripted *control* recipe, never imported by the production agent."""
    return {"status": ["open", "choose", "save", "reload"], "search": ["open", "type_query", "search"], "quantity": ["open", "type_quantity", "apply"]}[task["family"]]
