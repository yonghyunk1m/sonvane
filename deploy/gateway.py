"""Authenticated relay for an isolated demo instance; never serves the owner's workspace."""
from __future__ import annotations
import hashlib,hmac,json,os,re,secrets,sqlite3,time
from pathlib import Path
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ['SONVANE_DEMO_DATA'])
TOKEN=os.environ['SONVANE_RELAY_TOKEN']
CORE=os.environ['SONVANE_CORE_URL']
COOKIE='sonvane_demo_session'
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
# Serve only known application assets, never arbitrary files from static/report or production captures.
ASSETS=set()
for d in ['assets','studio','updates','brand']:
 for p in (ROOT/'app/static'/d).rglob('*'):
  if p.is_file() and p.suffix in {'.css','.js','.svg','.woff2','.wasm','.tflite','.task','.txt','.html'}:ASSETS.add('/'+str(p.relative_to(ROOT/'app/static')))
for name in ['index.html','film.html','film.css','film.js','sonvane-demo.mp4','sonvane-demo-poster.jpg','experience.css','experience.js','sound-sketch.js','face-volume.js','face-worker.js','situation-brief-v1.png','situation-clarify-v1.png','situation-criteria-v2.png','situation-compare-v2.png','situation-record-v1.png']:
 ASSETS.add('/demo/'+name)
for name in ['index.html','report.css','sonvane-technical-report.pdf','pipeline.svg','pipeline.png','pipeline.pdf','recovery.svg','recovery.pdf']:
 ASSETS.add('/report/'+name)
ASSETS.update(['/','/demo/','/studio/','/report/','/updates/','/brand/','/favicon.ico'])
def db():
 DATA.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DATA/'relay.sqlite',timeout=10)
 c.execute('CREATE TABLE IF NOT EXISTS owners(profile TEXT PRIMARY KEY, session TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS hits(session TEXT, at REAL)')
 return c
def signature(s):return hmac.new(TOKEN.encode(),s.encode(),hashlib.sha256).hexdigest()
def session_from(cookie):
 if not cookie:return None
 parts=cookie.split('.')
 return parts[0] if len(parts)==2 and re.fullmatch('[a-f0-9]{32}',parts[0]) and hmac.compare_digest(signature(parts[0]),parts[1]) else None
def owned(profile,session,claim=False):
 if not re.fullmatch('[a-f0-9]{32}',profile or ''):return False
 with db() as c:
  if claim:c.execute('INSERT OR IGNORE INTO owners(profile,session) VALUES (?,?)',(profile,session))
  row=c.execute('SELECT session FROM owners WHERE profile=?',(profile,)).fetchone()
 return bool(row and hmac.compare_digest(row[0],session))
def fail(status,message):return JSONResponse({'detail':message},status_code=status)
@app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','DELETE','PATCH'])
async def relay(request:Request,path:str):
 if not hmac.compare_digest(request.headers.get('authorization',''), 'Bearer '+TOKEN):return fail(403,'Access denied')
 path='/'+path
 if not path.startswith('/api/studio/') and path not in ASSETS:return fail(404,'Not found')
 session=session_from(request.cookies.get(COOKIE));fresh=session is None
 if fresh:
  if request.method not in ('GET','HEAD'):return fail(403,'Open the demo page before making a request.')
  session=secrets.token_hex(16)
 if request.method not in ('GET','HEAD'):
  with db() as c:
   c.execute('DELETE FROM hits WHERE at<?',(time.time()-60,))
   count=c.execute('SELECT COUNT(*) FROM hits WHERE session=?',(session,)).fetchone()[0]
   if count>=25:return fail(429,'Please wait a minute before trying again.')
   c.execute('INSERT INTO hits VALUES (?,?)',(session,time.time()))
 body=bytearray()
 async for chunk in request.stream():
  body.extend(chunk)
  if len(body)>32*1024*1024:return fail(413,'For this hosted demo, use a video under 32 MB.')
 body=bytes(body)
 if path.startswith('/api/studio/profiles/'):
  profile=path.split('/')[4]
  if not owned(profile,session,claim=request.method=='GET'):return fail(404,'Profile not found')
 if path=='/api/studio/projects':
  if request.method=='GET':profile=request.query_params.get('profile_id','')
  elif request.method=='POST':
   # A bounded body can be parsed and replayed without forwarding private browser cookies.
   request._body=body
   try:profile=str((await request.form()).get('profile_id',''))
   except Exception:return fail(400,'Invalid upload')
  else:return fail(405,'Method not allowed')
  if not owned(profile,session):return fail(404,'Profile not found')
  if request.method=='POST':
   projects=list((DATA/'projects').glob('*/project.json'))
   if len(projects)>=40:return fail(429,'The demo is at capacity. Please try again later.')
   mine=sum(json.loads(p.read_text()).get('profile_id')==profile for p in projects)
   if mine>=3:return fail(429,'This demo allows three videos per visitor.')
 m=re.match(r'^/api/studio/projects/([^/]+)',path)
 if m:
  if not re.fullmatch('[a-f0-9]{32}',m[1]):return fail(404,'Project not found')
  try:project=json.loads((DATA/'projects'/m[1]/'project.json').read_text())
  except (OSError,ValueError):return fail(404,'Project not found')
  if not owned(project.get('profile_id',''),session):return fail(404,'Project not found')
 headers={k:v for k,v in request.headers.items() if k.lower() not in {'host','authorization','cookie','origin','connection','content-length','accept-encoding'}}
 headers['origin']=CORE
 try:
  async with httpx.AsyncClient(timeout=180) as client:
   result=await client.request(request.method,CORE+path,params=request.query_params,headers=headers,content=body)
 except httpx.HTTPError:return fail(503,'The GPU server is reconnecting. Please try again shortly.')
 output_headers={k:v for k,v in result.headers.items() if k.lower() not in {'content-length','content-encoding','transfer-encoding','connection','set-cookie'}}
 output_headers['content-security-policy']=output_headers.get('content-security-policy',"default-src 'self'").replace("frame-ancestors 'none'","frame-ancestors https://huggingface.co https://*.hf.space")
 output=Response(result.content,status_code=result.status_code,headers=output_headers)
 if fresh:output.set_cookie(COOKIE,session+'.'+signature(session),max_age=7*86400,httponly=True,secure=True,samesite='none')
 return output
