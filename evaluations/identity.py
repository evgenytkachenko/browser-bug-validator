"""Resolve existing Ollama model artifacts without downloads or model execution."""
import json
import re
import urllib.request
from urllib.parse import urlsplit

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('Model-identity endpoint redirects are forbidden')

def resolve_local_model(config):
    try:
        endpoint = config.get('endpoint', 'http://127.0.0.1:11434').rstrip('/')
        p = urlsplit(endpoint)
        if p.scheme != 'http' or p.hostname not in {'127.0.0.1','localhost','::1'} or not p.port or p.path or p.query or p.fragment or p.username or p.password:
            raise ValueError('Model identity requires an explicit loopback origin')
        requested = config.get('model', 'llama3.1:8b')
        normalized = requested if ':' in requested.rsplit('/', 1)[-1] else requested + ':latest'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(endpoint + '/api/tags', timeout=5) as response:
            raw = response.read(1024*1024+1)
        if len(raw) > 1024*1024:
            raise ValueError('Model list exceeds size budget')
        matches = [m for m in json.loads(raw).get('models', []) if m.get('name') in {requested, normalized} or m.get('model') in {requested, normalized}]
        if len(matches) != 1 or not re.fullmatch('[0-9a-f]{64}', matches[0].get('digest', '')):
            raise ValueError('Could not resolve one existing model digest')
        return {'status':'verified', 'endpoint':endpoint, 'requested_model':requested,
                'resolved_name':matches[0].get('name'), 'digest':matches[0]['digest']}
    except Exception as exc:
        return {'status':'unverified', 'reason':f'{type(exc).__name__}: {exc}'}
