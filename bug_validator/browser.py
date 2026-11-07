from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from .common import ValidationError, write_json


def execute_browser(bug, entry, selectors, origin, output_dir, browser_config=None):
    config = browser_config or {}
    node = config.get("node_executable") or shutil.which("node")
    if not node:
        raise ValidationError("Node.js is unavailable; install dependencies only with permission")
    payload = {"origin": origin, "task_id": bug["target_task_id"], "expected_status": bug["expected_status"],
               "selectors": selectors, "output_dir": str(output_dir),
               "executable_path": config.get("executable_path"),
               "playwright_module": config.get("playwright_module"),
               "headless": config.get("headless", True), "timeout_ms": config.get("timeout_ms", 8000)}
    timeout = config.get("process_timeout_seconds", 60)
    if type(timeout) not in (int, float) or not 10 <= timeout <= 300:
        raise ValidationError("Browser process timeout must be between 10 and 300 seconds")
    # No model or page content can select executable, module, or launch flags.
    try:
        process = subprocess.Popen([node, str(Path(__file__).with_name("browser_bridge.cjs"))],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "NODE_NO_WARNINGS": "1"})
        try:
            stdout, stderr = process.communicate(json.dumps(payload), timeout=timeout)
        except subprocess.TimeoutExpired:
            # The bridge handles SIGTERM by closing only its own fresh browser.
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            (output_dir / "browser-stderr.txt").write_text(stderr[-12000:])
            raise ValidationError("Browser process exceeded its time budget; inconclusive")
    except OSError as exc:
        raise ValidationError("Browser runtime could not be started: " + str(exc)) from exc
    (output_dir / "browser-stderr.txt").write_text(stderr[-12000:])
    if process.returncode:
        raise ValidationError(f"Browser bridge failed (exit {process.returncode}): {stderr[-1200:]}")
    try:
        parsed = json.loads(stdout)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Browser bridge returned malformed evidence") from exc
    write_json(output_dir / "execution.json", parsed)
    return parsed
