"""Scripted test-double policy for browser integration controls, not an LLM.

This module is never imported by the production agent. It is deliberately simple
and follows fixture-specific recipes. Results must not be called model quality.
"""
from __future__ import annotations

import json
from pathlib import Path

from bug_validator.common import digest, write_json


class ScriptedControl:
    def __init__(self, output_dir, sequence=None):
        self.calls = []
        self.output_dir = Path(output_dir)
        self.sequence = sequence

    def ask(self, stage, system, payload, schema):
        available = schema["properties"]["action_id"]["enum"]
        if "choose" in available:
            sequence = ["open", "choose", "save", "reload"]
        elif "type_query" in available:
            sequence = ["open", "type_query", "search"]
        else:
            sequence = ["open", "type_quantity", "apply"]
        if self.sequence is not None:
            sequence = self.sequence
        step = len(self.calls)
        if step < len(sequence):
            answer = {"action_id": sequence[step], "reason": "Scripted integration control action; not model reasoning.", "verdict": None, "evidence_ids": []}
        else:
            observations = payload.get("checkpoint_results", [])
            # Contract uses already-observed predicates. No task truth is read.
            records = list(observations.values()) if isinstance(observations, dict) else observations
            requirements = [check for record in records for check in record.get("checks", []) if check.get("role") == "requirement"]
            met = all(check.get("met") is True for check in requirements)
            ids = [record["observation_id"] for record in records]
            answer = {"action_id": "finish", "reason": "Scripted control completes using observed predicates only.", "verdict": "not_reproduced" if met else "confirmed", "evidence_ids": ids}
        request = {"stage": stage, "system": system, "payload": payload, "schema": schema}
        artifact = f"control-{len(self.calls)+1:03}.json"
        write_json(self.output_dir / artifact, {"kind": "scripted-control-not-model", "request": request, "answer": answer})
        self.calls.append({"id": f"control-{len(self.calls)+1:03}", "stage": stage, "backend": "scripted-control",
                           "status": "completed", "artifact": artifact, "request_sha256": digest(request), "answer": answer})
        return answer
