"""Checks for the hosted-demo boundary, without network calls or model inference."""
import importlib.util,json,sys
import httpx,pytest
from fastapi.testclient import TestClient
from pathlib import Path

@pytest.fixture
def gateway(tmp_path,monkeypatch):
 monkeypatch.setenv('SONVANE_DEMO_DATA',str(tmp_path));monkeypatch.setenv('SONVANE_RELAY_TOKEN','test-relay-secret');monkeypatch.setenv('SONVANE_CORE_URL','http://testserver')
 spec=importlib.util.spec_from_file_location('test_gateway_module',Path(__file__).parents[1]/'deploy/gateway.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 class Upstream:
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def request(self,method,url,**kwargs):
   assert 'authorization' not in kwargs['headers'];assert 'cookie' not in kwargs['headers']
   return httpx.Response(200,json={'ok':True},headers={'content-security-policy':"default-src 'self'; frame-ancestors 'none'"})
 monkeypatch.setattr(mod.httpx,'AsyncClient',lambda **kwargs:Upstream())
 return mod

def visitor(mod):
 c=TestClient(mod.app,base_url='https://example.test',headers={'authorization':'Bearer test-relay-secret'})
 assert c.get('/demo/').status_code==200
 return c

def test_relay_requires_server_credential(gateway):
 c=TestClient(gateway.app);assert c.get('/demo/').status_code==403

def test_private_report_and_production_files_are_not_served(gateway):
 c=visitor(gateway)
 for path in ['/report/training_data.pdf','/demo/storyboard.html','/api/sessions','/.env','/demo/film-v2-assets/source.mp4']:
  assert c.get(path).status_code==404,path

def test_profiles_cannot_be_read_or_deleted_by_another_visitor(gateway):
 a=visitor(gateway);b=visitor(gateway);profile='a'*32
 assert a.get('/api/studio/profiles/'+profile).status_code==200
 assert b.get('/api/studio/profiles/'+profile).status_code==404
 assert b.delete('/api/studio/profiles/'+profile).status_code==404
 assert a.get('/api/studio/projects',params={'profile_id':profile}).status_code==200
 assert b.get('/api/studio/projects',params={'profile_id':profile}).status_code==404

def test_project_media_and_actions_require_ownership(gateway):
 a=visitor(gateway);b=visitor(gateway);profile='a'*32;project='b'*32
 a.get('/api/studio/profiles/'+profile)
 folder=gateway.DATA/'projects'/project;folder.mkdir(parents=True);(folder/'project.json').write_text(json.dumps({'profile_id':profile}))
 for suffix in ['', '/source','/preview','/record','/audio/'+'c'*32]:
  assert a.get('/api/studio/projects/'+project+suffix).status_code==200
  assert b.get('/api/studio/projects/'+project+suffix).status_code==404
 assert b.post('/api/studio/projects/'+project+'/generate',json={}).status_code==404

def test_upload_checks_form_owner_and_replays_bounded_body(gateway):
 a=visitor(gateway);b=visitor(gateway);profile='a'*32
 a.get('/api/studio/profiles/'+profile)
 args={'data':{'profile_id':profile},'files':{'file':('clip.mp4',b'fixture','video/mp4')}}
 assert a.post('/api/studio/projects',**args).status_code==200
 assert b.post('/api/studio/projects',**args).status_code==404

def test_missing_or_forged_cookie_cannot_write(gateway):
 c=TestClient(gateway.app,headers={'authorization':'Bearer test-relay-secret'})
 assert c.post('/api/studio/projects',data={}).status_code==403
 c.cookies.set(gateway.COOKIE,'a'*32+'.forged')
 assert c.post('/api/studio/projects',data={}).status_code==403

def test_oversized_upload_is_rejected_before_upstream(gateway):
 c=visitor(gateway)
 assert c.post('/api/studio/projects',content=b'x'*(32*1024*1024+1)).status_code==413

def test_mutation_rate_is_bounded(gateway):
 c=visitor(gateway)
 for _ in range(25):assert c.post('/api/studio/sound-effects/preview',json={}).status_code==200
 assert c.post('/api/studio/sound-effects/preview',json={}).status_code==429

def test_demo_cookies_are_secure_and_http_only(gateway):
 c=visitor(gateway);r=c.get('/demo/')
 assert 'sonvane_demo_session' in c.cookies
 fresh=TestClient(gateway.app,base_url='https://example.test',headers={'authorization':'Bearer test-relay-secret'}).get('/demo/')
 header=fresh.headers['set-cookie'].lower()
 assert 'httponly' in header and 'secure' in header and 'samesite=none' in header
 assert 'https://huggingface.co' in r.headers['content-security-policy']
