"""Repeated controlled evaluation of the general agent, preserving every trial.

`scripted-control` runs real browser actions with an explicit policy test double.
`local-model` runs the actual Ollama-driven decision loop. Never combine scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

from fixture_app.general_server import GeneralFixture
from .general_grading import grade
from .general_tasks import TASKS, exercise_required, public_inputs
from .identity import resolve_local_model
from .metrics import summarize
from .trial_metrics import summarize_trials
from .run import dump, source_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def fingerprint():
    return {"agent": source_fingerprint([ROOT / "bug_validator"]),
            "fixture": source_fingerprint([ROOT / "fixture_app"]),
            "evaluator": source_fingerprint([ROOT / "evaluations"])}


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path else None


def decision_counts(report):
    """Count attempts separately from schema-valid completed model responses."""
    calls = report.get("model_calls", [])
    real = [call for call in calls if call.get("backend") == "ollama"]
    return {"model_calls_attempted": len(calls),
            "model_calls_completed": sum(call.get("status") == "completed" for call in calls),
            "real_model_calls_attempted": len(real),
            "real_model_calls_completed": sum(call.get("status") == "completed" for call in real),
            "finished_with_assessment": any(call.get("status") == "completed" and call.get("answer", {}).get("action_id") == "finish" for call in calls)}


def participation_summary(rows):
    return {"model_calls_attempted": sum(row["model_calls_attempted"] for row in rows),
            "model_calls_completed": sum(row["model_calls_completed"] for row in rows),
            "real_model_calls_attempted": sum(row["real_model_calls_attempted"] for row in rows),
            "real_model_calls_completed": sum(row["real_model_calls_completed"] for row in rows),
            "trials_with_successful_decisions": sum(row["model_calls_completed"] > 0 for row in rows),
            "real_model_attempted_trials": sum(row["real_model_calls_attempted"] > 0 for row in rows),
            "real_model_successful_decision_trials": sum(row["real_model_calls_completed"] > 0 for row in rows),
            "real_model_evidence_bearing_trials": sum(row["real_model_calls_completed"] > 0 and row["browser_observations"] > 0 for row in rows)}


def model_quality_eligible(backend, identity_stable, source_frozen, rows):
    return backend == "local-model" and identity_stable and source_frozen and any(
        row["browser_started"] and row["browser_observations"] > 0 and row["real_model_calls_completed"] > 0 for row in rows)


def agent_process(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=["scripted-control", "local-model"], required=True)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--browser-config", type=Path)
    args = parser.parse_args(argv)
    from bug_validator.general import run_agent
    from .general_control import ScriptedControl
    data = json.loads(args.input.read_text())
    model = ScriptedControl(args.output) if args.backend == "scripted-control" else None
    report = run_agent(data["bug"], data["knowledge_base"], data["authorization"], args.output,
                       json.loads(args.model_config.read_text()) if args.model_config else None,
                       json.loads(args.browser_config.read_text()) if args.browser_config else None, model=model)
    return 2 if report["verdict"] == "inconclusive" else 0


def run_trial(task, trial_index, output, backend, model_config=None, browser_config=None, timeout=180):
    trial_id = f"{task['id']}--{trial_index:03}"
    directory = output / trial_id
    directory.mkdir()
    agent_dir = directory / "agent"
    started = time.monotonic()
    with GeneralFixture(task["family"], task["mode"], query=task.get("query", "alpha"), expected_status=task.get("expected_status", "done"), quantity=task.get("quantity", -2)) as fixture:
        bug, kb, auth = public_inputs(task, fixture.base_url)
        public = {"bug": bug, "knowledge_base": kb, "authorization": auth}
        dump(directory / "public-input.json", public)
        dump(directory / "oracle-private.json", task)
        before = fixture.snapshot()
        dump(directory / "state-before.json", before)
        command = [sys.executable, "-m", "evaluations.general_run", "_agent", "--input", str(directory / "public-input.json"), "--output", str(agent_dir), "--backend", backend]
        if model_config:
            command += ["--model-config", str(model_config)]
        if browser_config:
            command += ["--browser-config", str(browser_config)]
        process = {"state": "not_started"}
        try:
            with (directory / "stdout.txt").open("w") as stdout, (directory / "stderr.txt").open("w") as stderr:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, start_new_session=True)
                try:
                    code = child.wait(timeout=timeout)
                    process = {"state": "exited", "return_code": code}
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    process = {"state": "timeout", "return_code": child.returncode}
        except Exception as exc:
            process = {"state": "launch_error", "error": f"{type(exc).__name__}: {exc}"}
        after, journal = fixture.snapshot(), fixture.audit_log()
        dump(directory / "state-after.json", after)
        dump(directory / "server-journal.json", journal)
        try:
            report = json.loads((agent_dir / "report.json").read_text())
            if not isinstance(report, dict):
                raise ValueError("Report must be an object")
        except (ValueError, OSError) as exc:
            report = {}
            process["report_error"] = str(exc)
        try:
            trace = [json.loads(line) for line in (agent_dir / "trace.jsonl").read_text().splitlines() if line.strip()] if (agent_dir / "trace.jsonl").exists() else []
            result = grade(task, report, before, after, journal, agent_dir, auth, trace, backend,
                           expected_model_config=json.loads(model_config.read_text()) if model_config else None,
                           source_root=ROOT, knowledge_base=kb)
        except Exception as exc:
            result = {"passed": False, "checks": [], "semantic_status": "unverified", "grader_error": f"{type(exc).__name__}: {exc}"}
        process_ok = process.get("state") == "exited" and process.get("return_code") == (2 if report.get("verdict") == "inconclusive" else 0)
        result["checks"].append({"name": "agent_process_completed", "passed": process_ok, "detail": process})
        result["passed"] = result["passed"] and process_ok
        dump(directory / "grade.json", result)
        dump(directory / "process.json", process)
        row = {"trial_id": trial_id, "task_id": task["id"], "family": task["family"], "split": task["split"],
               "trial_index": trial_index, "backend": backend, "expected_verdict": task["expected_verdict"],
               "actual_verdict": report.get("verdict"), "deterministic_pass": result["passed"],
               "semantic_status": "unverified", "requires_exercise": exercise_required(task),
               "model_calls": len(report.get("model_calls", [])), "browser_observations": len(report.get("observations", [])),
               "real_model_calls": sum(call.get("backend") == "ollama" for call in report.get("model_calls", [])),
               "browser_started": bool(report.get("provenance", {}).get("browser_runtime", {}).get("browser")),
               **decision_counts(report),
               "failed_checks": [check["name"] for check in result["checks"] if not check["passed"]],
               "grader_error": result.get("grader_error"), "process_status": process, "elapsed_seconds": round(time.monotonic() - started, 4)}
        dump(directory / "trial.json", row)
        dump(directory / "artifact-hashes.json", {str(path.relative_to(directory)): _hash(path) for path in sorted(directory.rglob("*")) if path.is_file()})
        return row


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_agent":
        return agent_process(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=["scripted-control", "local-model"], required=True)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--split", choices=["development", "reserved-transfer"], default="development")
    parser.add_argument("--task", action="append", choices=[task["id"] for task in TASKS])
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--browser-config", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--frozen-manifest", type=Path)
    parser.add_argument("--holdout-ledger", type=Path, help="Optional consume-once author-visible reservation ledger")
    parser.add_argument("--acknowledge-author-visible-holdout", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.trials <= 100 or not 1 <= args.timeout <= 1800:
        parser.error("Trials must be 1..100 and timeout 1..1800 seconds")
    if args.backend == "local-model" and args.model_config is None:
        parser.error("A real local-model evaluation requires --model-config")
    tasks = [task for task in TASKS if task["split"] == args.split and (not args.task or task["id"] in args.task)]
    if not tasks or args.task and any(task_id not in {task["id"] for task in tasks} for task_id in args.task):
        parser.error("Choose tasks only from the selected split")
    sources = fingerprint()
    if args.holdout_ledger and args.split != "reserved-transfer":
        parser.error("--holdout-ledger applies only to reserved-transfer")
    if args.holdout_ledger and args.task:
        parser.error("Ledger-controlled evaluation requires the full reserved split")
    if args.split == "reserved-transfer":
        if not args.acknowledge_author_visible_holdout or args.frozen_manifest is None:
            parser.error("Reserved transfer requires --frozen-manifest and --acknowledge-author-visible-holdout; it is not a blind benchmark")
        frozen = json.loads(args.frozen_manifest.read_text())
        if frozen.get("sources") != sources or frozen.get("source_frozen_through_run") is not True:
            parser.error("Agent, fixture, and evaluator must match the frozen development manifest")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    model_path = args.model_config.resolve() if args.model_config else None
    browser_path = args.browser_config.resolve() if args.browser_config else None
    model_config = json.loads(model_path.read_text()) if model_path else {}
    identity = resolve_local_model(model_config) if args.backend == "local-model" else {"status": "not_applicable", "reason": "scripted control is not a model"}
    manifest = {"schema_version": 1, "suite": "general-loop-v1", "split": args.split,
                "holdout_status": "development" if args.split == "development" else "untracked-author-visible-transfer-not-blind", "backend": args.backend,
                "completed": False, "integrity_version": 1,
                "task_ids": [task["id"] for task in tasks], "trials_per_task": args.trials,
                "sources": sources, "model_config_sha256": _hash(model_path), "browser_config_sha256": _hash(browser_path),
                "model_identity_before": identity, "runtime": {"python": sys.version, "platform": platform.platform()},
                "model_quality_claim_eligible": False,
                "frozen_manifest_sha256": _hash(args.frozen_manifest) if args.frozen_manifest else None,
                "created_unix": time.time(), "separation_limit": "Private fixture state withheld from model and separate agent process; same filesystem user, not OS-isolated."}
    if args.holdout_ledger:
        from .holdout import consume
        binding = {key: manifest.get(key) for key in ("sources", "backend", "model_config_sha256", "browser_config_sha256", "model_identity_before")}
        try:
            manifest["holdout_reservation"] = consume(args.holdout_ledger, tasks, binding, manifest["frozen_manifest_sha256"], output)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        manifest["holdout_status"] = "consumed-author-visible-not-blind"
    dump(output / "manifest.json", manifest)
    rows = []
    for task in tasks:
        for trial in range(1, args.trials + 1):
            row = run_trial(task, trial, output, args.backend, model_path, browser_path, args.timeout)
            rows.append(row)
            with (output / "trials.jsonl").open("a") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
            print(json.dumps(row), flush=True)
    after_identity = resolve_local_model(model_config) if args.backend == "local-model" else identity
    manifest["model_identity_after"] = after_identity
    manifest["model_identity_stable"] = identity == after_identity and identity.get("status") in {"verified", "not_applicable"}
    manifest["source_frozen_through_run"] = sources == fingerprint() and manifest["model_config_sha256"] == _hash(model_path) and manifest["browser_config_sha256"] == _hash(browser_path)
    manifest["model_quality_claim_eligible"] = model_quality_eligible(args.backend, manifest["model_identity_stable"], manifest["source_frozen_through_run"], rows)
    dump(output / "manifest.json", manifest)
    summary = summarize(rows)
    summary.update(participation_summary(rows))
    summary.update(summarize_trials(rows))
    summary.update(backend=args.backend, split=args.split, source_frozen_through_run=manifest["source_frozen_through_run"], model_identity_stable=manifest["model_identity_stable"],
                   full_exercise_trials=sum(row["requires_exercise"] for row in rows),
                   full_exercise_passes=sum(row["requires_exercise"] and row["deterministic_pass"] for row in rows),
                   trials_with_decision_calls=sum(row["model_calls"] > 0 for row in rows),
                   trials_with_browser_evidence=sum(row["browser_observations"] > 0 for row in rows),
                   trials_with_finish_assessment=sum(row["finished_with_assessment"] for row in rows),
                   real_model_trials=sum(row["real_model_calls"] > 0 for row in rows),
                   real_browser_started_trials=sum(row["browser_started"] for row in rows),
                   nonexercise_passes=sum(not row["requires_exercise"] and row["deterministic_pass"] for row in rows),
                   qualification=("Real-model controlled evaluation" if manifest["model_quality_claim_eligible"] else "Real-model evaluation attempted; execution or provenance not qualified") if args.backend == "local-model" else "Scripted policy integration control, not model performance")
    summary["limitations"] += ["Three controlled workflows do not establish arbitrary-website capability.", "Reserved transfer cases are visible to authors and must not be called a blind/unseen benchmark.", "Author changes after inspecting reserved results contaminate that split; version a new reserved set before another generalization claim."]
    dump(output / "summary.json", summary)
    manifest["completed"] = True
    dump(output / "manifest.json", manifest)
    dump(output / "run-artifact-hashes.json", {str(path.relative_to(output)): _hash(path) for path in sorted(output.rglob("*")) if path.is_file()})
    print(json.dumps(summary, indent=2))
    return 0 if summary["failures"] == 0 and manifest["source_frozen_through_run"] and manifest["model_identity_stable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
