from __future__ import annotations
import argparse
import json
from pathlib import Path
from .agent import run_agent

def read_json(filename):
    return json.loads(Path(filename).read_text())

def main():
    parser = argparse.ArgumentParser(description="Evidence-first local browser bug validation")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Reproduce a task-status bug in an authorized local fixture")
    for option in ("bug", "kb", "base-url", "output"):
        run.add_argument("--" + option, required=True)
    run.add_argument("--backend", choices=["deterministic", "local-model"], default="deterministic")
    run.add_argument("--model-config")
    run.add_argument("--browser-config")
    args = parser.parse_args()
    report = run_agent(read_json(args.bug), read_json(args.kb), args.base_url, args.output, args.backend,
                       read_json(args.model_config) if args.model_config else None,
                       read_json(args.browser_config) if args.browser_config else None)
    print(json.dumps({"verdict": report["verdict"], "report": str(Path(args.output).resolve() / "report.json"),
                      "summary": report["summary"]}, indent=2))
    # A valid inconclusive report is not a successful reproduction. Evaluators read the verdict.
    return 0 if report["verdict"] != "inconclusive" else 2

if __name__ == "__main__":
    raise SystemExit(main())
