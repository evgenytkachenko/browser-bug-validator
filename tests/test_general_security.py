"""Independent gateway/host regression controls.

These tests run the actual Node controller with an explicitly MOCKED Playwright
module. HTTP transport tests use real disposable loopback servers, but do NOT
establish real-browser or real-model quality or an OS-level security boundary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bug_validator.general_contracts import request_path
from bug_validator.common import ValidationError

ROOT = Path(__file__).resolve().parent.parent
MOCK_PLAYWRIGHT = r"""
const fs=require('fs');
const scenario=JSON.parse(process.env.REVIEW_NETWORK_SCENARIO||'{}');
exports.chromium={launch:async()=>{
 let url='about:blank',routeHandler,responseWaiter;
 const dispatch=async target=>{
  const request={url:()=>target.url,method:()=>target.method||'GET',postData:()=>target.body===undefined?null:JSON.stringify(target.body),postDataJSON:()=>target.body,frame:()=>target.subframe?{}:page};
  let result;
  await routeHandler({request:()=>request,fulfill:async r=>{result={url:()=>target.url,ok:()=>r.status>=200&&r.status<300,status:()=>r.status,request:()=>request};if(responseWaiter&&responseWaiter.predicate(result))responseWaiter.resolve(result)},abort:async()=>{throw Error('MOCK browser received blocked request')}});
  return result;
 };
 const element={count:async()=>1,inputValue:async()=>'ok',innerText:async()=>'ok',fill:async()=>{},selectOption:async()=>{},click:async()=>{for(const req of scenario.click||[])await dispatch(req)}};
 const page={setDefaultTimeout(){},on(){},url:()=>url,mainFrame:()=>page,getByTestId:()=>element,locator:()=>element,
 goto:async(next)=>{url=next;const result=scenario.network?await dispatch({url:next}):{ok:()=>true};for(const req of scenario.on_open||[])await dispatch(req);return result},
 waitForResponse:predicate=>new Promise(resolve=>{responseWaiter={predicate,resolve}}),
 screenshot:async({path})=>{const b=Buffer.from('MOCK IMAGE: NOT REAL BROWSER EVIDENCE');fs.writeFileSync(path,b);return b},close:async()=>{}};
 const ctx={newPage:async()=>page,on(){},routeWebSocket:async()=>{},route:async(_p,f)=>{routeHandler=f},close:async()=>{}};
 return{newContext:async()=>ctx,version:()=> 'MOCK-review-only',close:async()=>{}};
}};
"""


class CanonicalPathSecurityTests(unittest.TestCase):
    def test_noncanonical_paths_rejected_before_browser(self):
        for path in ['/a\0', '/a\1', '/a\x7f', '/café', '/a?x=é', '/a"b',
                     "/a?x='b", '/a<b', '/a>b', '/a^b', '/a`b', '/a{b', '/a}b',
                     '//evil', '/a/../admin', '/a%2fadmin', '/a?x=\\evil']:
            with self.subTest(path=path), self.assertRaises(ValidationError):
                request_path(path)
        for path in ['/start', '/api/search?q=alpha', '/a_b-1.2~3']:
            request_path(path)


@unittest.skipUnless(shutil.which('node'), 'Node unavailable: gateway mock controls not run')
class MockedBrowserGatewaySecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='validator-security-unit-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.module = self.directory / 'mock-playwright.cjs'
        self.module.write_text(MOCK_PLAYWRIGHT)

    def run_worker(self, auth, actions, scenario=None):
        output = self.directory / ('evidence-' + str(len(list(self.directory.glob('evidence-*')))))
        output.mkdir()
        commands = [{'command': 'init', 'authorization': auth, 'output_dir': str(output),
                     'config': {'playwright_module': str(self.module)}}]
        commands.extend({'command': 'act', 'action_id': name} for name in actions)
        commands.append({'command': 'close'})
        process = subprocess.run([shutil.which('node'), str(ROOT / 'bug_validator' / 'general_bridge.cjs')],
            input=''.join(json.dumps(value) + '\n' for value in commands), capture_output=True,
            text=True, timeout=15, env={**os.environ, 'REVIEW_NETWORK_SCENARIO': json.dumps(scenario or {})})
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), len(commands), process.stdout + process.stderr)
        self.assertTrue(responses[0]['ok'], responses)
        return responses

    def test_prototype_names_cannot_bypass_action_caps_mock_browser(self):
        for name in ['normal', 'constructor', 'toString', 'hasOwnProperty']:
            with self.subTest(action=name):
                auth = {'origin': 'http://127.0.0.1:18349', 'get_paths': ['/'],
                        'actions': {'open': {'kind': 'navigate', 'path': '/'},
                                    name: {'kind': 'observe', 'max_uses': 1}},
                        'probes': {'value': {'test_id': 'value', 'kind': 'text'}}}
                rows = self.run_worker(auth, ['open', name, name])
                self.assertTrue(rows[2]['ok'])
                self.assertFalse(rows[3]['ok'])
                self.assertIn('budget exceeded', rows[3]['error'])
                self.assertFalse(rows[-1]['result']['completed'])

    def test_network_boundaries_actual_gateway_mock_browser(self):
        received, sink = [], []

        class Sink(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_GET(self):
                sink.append(self.path)
                self.send_response(200)
                self.end_headers()

        class App(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_GET(self):
                received.append(('GET', self.path, None))
                self.send_response(302 if self.path == '/redirect' else 200)
                if self.path == '/redirect':
                    self.send_header('Location', sink_origin + '/sink')
                self.end_headers()
                self.wfile.write(b'hello')
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append(('POST', self.path, body))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')

        servers = [ThreadingHTTPServer(('127.0.0.1', 0), handler) for handler in (App, Sink)]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{servers[0].server_port}'
        sink_origin = f'http://127.0.0.1:{servers[1].server_port}'
        request = {'url': origin + '/write', 'method': 'POST', 'body': {'status': 'done'}}
        cases = [
            ('allowed-once', {}, [request], '/start', True, 1),
            ('wrong-body', {}, [dict(request, body={'status': 'todo'})], '/start', False, 0),
            ('extra-body-field', {}, [dict(request, body={'status': 'done', 'steal': True})], '/start', False, 0),
            ('duplicate-mutation', {}, [request, request], '/start', False, 1),
            ('unarmed-mutation', {'on_open': [request]}, None, '/start', False, 0),
            ('off-origin', {'on_open': [{'url': sink_origin + '/sink'}]}, None, '/start', False, 0),
            ('ungranted-query', {'on_open': [{'url': origin + '/start?leak=data'}]}, None, '/start', False, 0),
            ('subframe', {'on_open': [{'url': origin + '/start', 'subframe': True}]}, None, '/start', False, 0),
            ('redirect', {}, None, '/redirect', False, 0),
        ]
        try:
            for name, scenario, clicks, start, expected_ok, expected_posts in cases:
                with self.subTest(case=name):
                    received.clear()
                    sink.clear()
                    scenario = dict(scenario, network=True)
                    if clicks is not None:
                        scenario['click'] = clicks
                    auth = {'origin': origin, 'get_paths': ['/start', '/redirect'],
                            'actions': {'open': {'kind': 'navigate', 'path': start},
                                        'write': {'kind': 'click', 'test_id': 'write',
                                                  'request': {'method': 'POST', 'path': '/write', 'json': {'status': 'done'}}}},
                            'probes': {'value': {'test_id': 'value', 'kind': 'text'}}}
                    rows = self.run_worker(auth, ['open'] + (['write'] if clicks is not None else []), scenario)
                    self.assertIs(rows[-2]['ok'], expected_ok, rows)
                    self.assertEqual(sum(row[0] == 'POST' for row in received), expected_posts, received)
                    self.assertEqual(sink, [], 'A forbidden destination received a request')
                    if not expected_ok:
                        self.assertFalse(rows[-1]['result']['completed'])
            # The inherited-name regression also must preserve one-shot writes.
            auth['actions']['open']['path'] = '/start'
            auth['actions']['constructor'] = auth['actions'].pop('write')
            received.clear()
            rows = self.run_worker(auth, ['open', 'constructor', 'constructor'], {'network': True, 'click': [request]})
            self.assertTrue(rows[2]['ok'])
            self.assertFalse(rows[3]['ok'])
            self.assertEqual(sum(row[0] == 'POST' for row in received), 1)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
