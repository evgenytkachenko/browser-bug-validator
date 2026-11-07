from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from .browser import execute_browser
from .common import ValidationError, digest, file_digest, validate_bug, validate_entry, write_json
from .knowledge import retrieve
from .model import LocalModel
from .schemas import plan_schema, assessment_schema

VERDICTS = {"confirmed", "not_reproduced", "inconclusive"}


def classify_execution(execution, bug):
    """Trust controller observations, never model claims, for verdict admissibility."""
    if not execution.get("completed"):
        return "inconclusive", []
    observations = execution.get("observations", [])
    if not isinstance(observations, list) or len(observations) != 3:
        return "inconclusive", []
    if not all(isinstance(o, dict) and isinstance(o.get("id"), str) and o["id"] for o in observations):
        return "inconclusive", []
    if len({o["id"] for o in observations}) != 3 or [o.get("phase") for o in observations] != ["initial", "saved", "reloaded"]:
        return "inconclusive", []
    phases = {o["phase"]: o for o in observations}
    if not {"initial", "saved", "reloaded"}.issubset(phases):
        return "inconclusive", []
    initial, saved, final = (phases[key] for key in ("initial", "saved", "reloaded"))
    target = bug["target_task_id"]
    expected = bug["expected_status"]
    for observation in (initial, saved, final):
        if observation.get("values", {}).get("target_task_id") != target:
            return "inconclusive", []
        if observation.get("values", {}).get("persisted_status") not in {"todo", "doing", "done"}:
            return "inconclusive", []
    if initial["values"]["persisted_status"] == expected or saved["values"]["persisted_status"] != expected:
        return "inconclusive", []
    actual = final["values"]["persisted_status"]
    assertion = {"criterion_id": "status-persists-after-reload", "expected": expected, "observed": actual,
                 "met": actual == expected, "evidence_ids": [saved["id"], final["id"]]}
    return ("not_reproduced" if actual == expected else "confirmed"), [assertion]


def assessment_verdict(answer, observations, expected_status):
    """Check the model's observable proposition, then map it to the bug verdict.

    Never use the allegation or a model success label as the outcome. Neither
    incorrect extraction nor an incorrect persistence judgment can pass.
    """
    expected_fields = {"saved_status", "reloaded_status", "status_persisted", "evidence_ids", "explanation"}
    if not isinstance(answer, dict) or set(answer) != expected_fields:
        raise ValidationError("Model assessment has unexpected or missing evidence fields")
    phases = {o["phase"]: o for o in observations}
    saved, reloaded = phases["saved"], phases["reloaded"]
    ids = answer.get("evidence_ids")
    known_ids = {o["id"] for o in observations}
    required_ids = {saved["id"], reloaded["id"]}
    if (not isinstance(ids, list) or not all(isinstance(value, str) for value in ids)
        or len(ids) != len(set(ids)) or not required_ids.issubset(set(ids)) or not set(ids).issubset(known_ids)
        or not isinstance(answer.get("explanation"), str) or not answer["explanation"].strip()
        or len(answer["explanation"]) > 2000):
        raise ValidationError("Model assessment cited unsupported evidence or lacked an explanation")
    saved_actual = saved["values"]["persisted_status"]
    reloaded_actual = reloaded["values"]["persisted_status"]
    if answer["saved_status"] != saved_actual or answer["reloaded_status"] != reloaded_actual:
        raise ValidationError("Model-extracted statuses disagree with actual browser observations")
    if saved_actual != expected_status:
        raise ValidationError("Saved observation does not establish the requested status precondition")
    observed_persistence = saved_actual == expected_status and reloaded_actual == expected_status
    if type(answer["status_persisted"]) is not bool or answer["status_persisted"] is not observed_persistence:
        raise ValidationError("Model persistence judgment is uncertain or disagrees with browser evidence")
    return "not_reproduced" if observed_persistence else "confirmed"


def verify_controller_artifacts(execution, output_dir):
    for observation in execution.get("observations", []):
        name = observation.get("screenshot", "")
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".png"):
            raise ValidationError("Controller screenshot path is invalid")
        path = output_dir / name
        if not path.is_file() or file_digest(path) != observation.get("screenshot_sha256"):
            raise ValidationError("Controller screenshot evidence is missing or hash-mismatched")
    if execution.get("trace") != "trace.jsonl" or file_digest(output_dir / "trace.jsonl") != execution.get("trace_sha256"):
        raise ValidationError("Controller trace evidence is missing or hash-mismatched")


def run_agent(bug_report, knowledge_base, base_url, output_dir, backend="deterministic", model_config=None, browser_config=None):
    """Run a bounded reproduction. No fixture truth or expected verdict is accepted."""
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValidationError("Output directory must be empty; preserve prior trial evidence")
    started = time.monotonic()
    root = Path(__file__).resolve().parent.parent
    skill_path = root / "skills" / "browser-bug-validator" / "SKILL.md"
    source_paths = list(Path(__file__).parent.glob("*.py")) + list(Path(__file__).parent.glob("*.cjs"))
    report = {"schema_version": 1, "agent_version": "0.3.0", "scenario_id": bug_report.get("id") if isinstance(bug_report, dict) else None,
              "backend": backend, "verdict": "inconclusive", "summary": "Reproduction was not completed.",
              "observations": [], "steps": [], "assertions": [], "limitations": [], "model_calls": [],
              "knowledge_retrieval": [], "started_at": datetime.now(timezone.utc).isoformat(),
              "provenance": {"bug_sha256": digest(bug_report), "knowledge_base_sha256": digest(knowledge_base),
                             "source_sha256": {p.name: file_digest(p) for p in sorted(source_paths)},
                             "skill_sha256": file_digest(skill_path) if skill_path.exists() else None}}
    model = None
    try:
        if backend not in {"deterministic", "local-model"}:
            raise ValidationError("Unsupported backend; choose deterministic or local-model explicitly")
        origin = validate_bug(bug_report, base_url)
        best, retrieved = retrieve(bug_report, knowledge_base)
        report["knowledge_retrieval"] = [{"id": row["entry"]["id"], "score": row["score"], "matched_terms": row["matched_terms"]} for row in retrieved]
        entry = best["entry"]
        selectors = validate_entry(entry, bug_report["target_task_id"])
        report["journey_id"] = entry["id"]
        report["target_task_id"] = bug_report["target_task_id"]
        if not skill_path.exists():
            raise ValidationError("Required browser-bug-validator skill entrypoint is missing")
        skill_references = {stage: skill_path.parent / "references" / f"{stage}.md" for stage in ("plan", "assess")}
        if not all(path.is_file() for path in skill_references.values()):
            raise ValidationError("Required phase-specific skill reference is missing")
        report["provenance"]["skill_reference_sha256"] = {stage: file_digest(path) for stage, path in skill_references.items()}
        if backend == "local-model":
            model = LocalModel(model_config or {}, output)
            plan = model.ask("plan", skill_references["plan"].read_text(),
                {"bug": {k: bug_report[k] for k in ("id", "title", "description", "target_task_id", "expected_status")},
                 "retrieved_journey": entry}, plan_schema(entry["id"]))
            expected_plan = {"journey_id": entry["id"], "target_task_id": bug_report["target_task_id"],
                             "expected_status": bug_report["expected_status"]}
            if plan != expected_plan:
                raise ValidationError("Model plan was ambiguous, unsupported, or outside the authorized target/status")
        execution = execute_browser(bug_report, entry, selectors, origin, output, browser_config)
        report["observations"] = execution.get("observations", [])
        report["steps"] = execution.get("steps", [])
        report["limitations"].extend(execution.get("limitations", []))
        verify_controller_artifacts(execution, output)
        report["provenance"]["trace_sha256"] = execution["trace_sha256"]
        report["provenance"]["browser_runtime"] = execution.get("runtime", {})
        verdict, assertions = classify_execution(execution, bug_report)
        report["assertions"] = assertions
        if model is not None and verdict != "inconclusive":
            answer = model.ask("assess", skill_references["assess"].read_text(),
                {"requirement": {"target_task_id": bug_report["target_task_id"],
                                 "expected_status": bug_report["expected_status"],
                                 "expected_behavior": "The status shown after saving must survive reload."},
                 "unverified_report": {k: bug_report[k] for k in ("title", "description")},
                 "observations": [{k: o[k] for k in ("id", "phase", "visible_text", "values")} for o in report["observations"]]},
                assessment_schema([o["id"] for o in report["observations"]]))
            report["model_assessment"] = answer
            model_verdict = assessment_verdict(answer, report["observations"], bug_report["expected_status"])
            report["assessment_mapping"] = {"version": "status-persistence-v1",
                "mode": "deterministic_after_model_checked_evidence", "expected_status": bug_report["expected_status"],
                "saved_status": answer["saved_status"], "reloaded_status": answer["reloaded_status"],
                "status_persisted": answer["status_persisted"], "mapped_verdict": model_verdict,
                "evidence_ids": answer["evidence_ids"]}
            if model_verdict != verdict:
                raise ValidationError("Model evidence assessment disagreed with admissible browser verdict; human review required")
        report["verdict"] = verdict
        if verdict == "confirmed":
            report["summary"] = f"The reported bug was reproduced: {bug_report['target_task_id']} showed {bug_report['expected_status']} after save, then {assertions[0]['observed']} after reload."
        elif verdict == "not_reproduced":
            report["summary"] = f"The reported bug was not reproduced in this trial: {bug_report['target_task_id']} remained {bug_report['expected_status']} after reload. This does not prove the bug is absent in other conditions."
        else:
            report["summary"] = "Inconclusive: the required browser reproduction and evidence chain did not complete."
    except Exception as exc:
        report["verdict"] = "inconclusive"
        report["limitations"].append(f"{type(exc).__name__}: {str(exc)[:2500]}")
        report["summary"] = "Inconclusive: required inputs, execution, or evidence checks were not satisfied."
    finally:
        if model is not None:
            report["model_calls"] = model.calls
        if backend == "deterministic":
            report["limitations"].append("Deterministic reference backend: this trial did not call a language model.")
        report["limitations"].append("Scope: one isolated fictional local task-board trial; not a production defect or general reliability claim.")
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "report.json", report)
        lines = ["# Browser bug validation", "", f"Verdict: {report['verdict']}", "", report["summary"], "", "## Evidence"]
        for o in report["observations"]:
            lines.append(f"- {o['id']} ({o['phase']}): {o['values']}. Screenshot: {o['screenshot']}")
        lines += ["", "## Limitations"] + [f"- {limitation}" for limitation in report["limitations"]]
        (output / "report.md").write_text("\n".join(lines) + "\n")
    return report
