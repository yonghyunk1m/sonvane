"""Hosted entrypoint regressions: asset base URL and credential boundaries."""
import importlib.util
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def space(monkeypatch):
    monkeypatch.setenv('SONVANE_BACKEND_URL', 'https://private-backend.invalid')
    monkeypatch.setenv('SONVANE_RELAY_TOKEN', 'server-only-fixture')
    monkeypatch.setenv('SONVANE_PUBLIC_ORIGIN', 'https://public.invalid')
    spec = importlib.util.spec_from_file_location('space_entrypoint', Path(__file__).parents[1] / 'deploy/huggingface/app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_root_redirect_preserves_relative_asset_base(space):
    client = TestClient(space.app)
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/demo/'
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/healthz').json()['version'] == (Path(__file__).parents[1] / 'VERSION').read_text().strip()

def test_cross_origin_write_never_reaches_backend(space):
    client = TestClient(space.app)
    assert client.post('/api/studio/projects', headers={'origin': 'https://unrelated.invalid'}).status_code == 403

def test_browser_cannot_override_server_authorization(space, monkeypatch):
    class Upstream:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def request(self, method, url, **kwargs):
            assert kwargs['headers']['authorization'] == 'Bearer server-only-fixture'
            return httpx.Response(200, text='public response')
    monkeypatch.setattr(space.httpx, 'AsyncClient', lambda **kwargs: Upstream())
    response = TestClient(space.app).get('/demo/', headers={'authorization': 'Bearer browser-value'})
    assert response.text == 'public response'
    assert 'server-only-fixture' not in str(response.headers)

def test_connection_error_does_not_disclose_backend(space, monkeypatch):
    class Upstream:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def request(self, method, url, **kwargs):
            raise httpx.ConnectError('cannot reach ' + url)
    monkeypatch.setattr(space.httpx, 'AsyncClient', lambda **kwargs: Upstream())
    response = TestClient(space.app).get('/demo/')
    assert response.status_code == 503
    assert 'private-backend' not in response.text

def test_packaged_film_plays_without_backend_credentials(space, monkeypatch, tmp_path):
    monkeypatch.setattr(space, 'MEDIA_ROOT', tmp_path)
    monkeypatch.delenv('SONVANE_BACKEND_URL', raising=False)
    monkeypatch.delenv('SONVANE_RELAY_TOKEN', raising=False)
    payload = b'0123456789-film-fixture'
    (tmp_path / 'sonvane-demo.mp4').write_bytes(payload)
    client = TestClient(space.app)
    response = client.get('/demo/sonvane-demo.mp4?v=final', headers={'range': 'bytes=2-5'})
    assert response.status_code == 206
    assert response.content == payload[2:6]
    assert response.headers['content-range'] == f'bytes 2-5/{len(payload)}'
    assert response.headers['content-type'] == 'video/mp4'
    response = client.head('/demo/sonvane-demo.mp4')
    assert response.status_code == 200
    assert response.content == b''
    assert int(response.headers['content-length']) == len(payload)


def test_packaged_player_uses_local_assets_when_gpu_is_unavailable(space, monkeypatch, tmp_path):
    monkeypatch.setattr(space, 'MEDIA_ROOT', tmp_path)
    monkeypatch.delenv('SONVANE_BACKEND_URL', raising=False)
    (tmp_path / 'film.html').write_text('<video src="sonvane-demo.mp4" controls></video>')
    (tmp_path / 'film.css').write_text('video{width:100%}')
    client = TestClient(space.app)
    response = client.get('/demo/film.html')
    assert response.status_code == 200
    assert '<video' in response.text
    assert response.headers['cache-control'] == 'no-cache'
    assert client.get('/demo/film.css').headers['content-type'].startswith('text/css')
    # The working application still reports the missing backend, rather than serving film files as APIs.
    assert client.get('/api/studio/projects').status_code == 503
