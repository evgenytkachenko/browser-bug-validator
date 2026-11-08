"""A single fresh browser session serving bounded action IDs over JSONL."""
from __future__ import annotations
import json
import os
import selectors
import shutil
import subprocess
import time
from pathlib import Path
from .common import ValidationError


class BrowserSession:
    def __init__(self, authorization, output_dir, config=None):
        self.config = config or {}
        self.timeout = self.config.get('process_timeout_seconds', 30)
        if type(self.timeout) not in (int, float) or not 1 <= self.timeout <= 60:
            raise ValidationError('Worker response timeout must be between 1 and 60 seconds')
        browser_timeout = self.config.get('timeout_ms', 8000)
        if type(browser_timeout) is not int or not 100 <= browser_timeout <= 30000:
            raise ValidationError('Browser action timeout must be between 100 and 30000 ms')
        node = self.config.get('node_executable') or shutil.which('node')
        if not node:
            raise ValidationError('Existing Node.js is required')
        self.stderr = (Path(output_dir) / 'browser-stderr.txt').open('w')
        self.process = None
        self.buffer = b''
        self.selector = selectors.DefaultSelector()
        try:
            self.process = subprocess.Popen([node, str(Path(__file__).with_name('general_bridge.cjs'))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                env={**os.environ, 'NODE_NO_WARNINGS': '1'})
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            self.runtime = self._request({'command': 'init', 'authorization': authorization,
                'output_dir': str(output_dir), 'config': self.config}).get('runtime', {})
        except Exception:
            self.terminate()
            raise

    def _request(self, payload):
        data = json.dumps(payload, allow_nan=False).encode() + b'\n'
        if len(data) > 65536:
            raise ValidationError('Worker command exceeds byte budget')
        self.process.stdin.write(data)
        self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while b'\n' not in self.buffer:
            if not self.selector.select(max(0, deadline - time.monotonic())):
                raise ValidationError('Browser worker time budget exceeded')
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise ValidationError('Browser worker stopped before returning evidence')
            self.buffer += chunk
            if len(self.buffer) > 262144:
                raise ValidationError('Browser worker evidence exceeds byte budget')
        line, self.buffer = self.buffer.split(b'\n', 1)
        try:
            answer = json.loads(line)
        except ValueError as exc:
            raise ValidationError('Malformed browser-worker response') from exc
        if type(answer) is not dict or answer.get('ok') is not True:
            raise ValidationError('Browser action failed: ' + str(answer.get('error', 'unknown'))[:1500])
        return answer['result']

    def act(self, action_id):
        return self._request({'command': 'act', 'action_id': action_id})

    def close(self):
        try:
            return self._request({'command': 'close'})
        finally:
            self.terminate()

    def terminate(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
        self.selector.close()
        self.stderr.close()
