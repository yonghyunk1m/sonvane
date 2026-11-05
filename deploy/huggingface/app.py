"""Public Space entrypoint. Connection details exist only in Space Secrets."""
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response,RedirectResponse,FileResponse
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
@app.get('/healthz')
async def health():return {'service':'Sonvane','version':Path(__file__).with_name('VERSION').read_text().strip(),'configured':bool(os.getenv('SONVANE_BACKEND_URL') and os.getenv('SONVANE_RELAY_TOKEN'))}
# Only explicitly packaged presentation files are served here; application APIs stay proxied.
MEDIA_ROOT=Path(__file__).with_name('media')
FILM_ASSETS={
 '/demo/film.html':('film.html','text/html'),
 '/demo/film.css':('film.css','text/css'),
 '/demo/film.js':('film.js','text/javascript'),
 '/demo/sonvane-demo.mp4':('sonvane-demo.mp4','video/mp4'),
 '/demo/sonvane-demo-poster.jpg':('sonvane-demo-poster.jpg','image/jpeg'),
 '/assets/inter.woff2':('inter.woff2','font/woff2'),
 '/assets/inter-OFL.txt':('inter-OFL.txt','text/plain'),
}
def film_endpoint(filename,media_type):
 async def serve(request:Request):
  asset=MEDIA_ROOT/filename
  if not asset.is_file():return await proxy(request,request.url.path.lstrip('/'))
  return FileResponse(asset,media_type=media_type,headers={
   'cache-control':'no-cache' if filename.endswith(('.html','.css','.js')) else 'public, max-age=3600',
   'x-content-type-options':'nosniff',
  })
 return serve
for route,(filename,media_type) in FILM_ASSETS.items():
 app.add_api_route(route,film_endpoint(filename,media_type),methods=['GET','HEAD'])

@app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','DELETE','PATCH'])
async def proxy(request:Request,path:str):
 if not path:return RedirectResponse('/demo/',status_code=307,headers={'cache-control':'no-store'})
 backend=os.getenv('SONVANE_BACKEND_URL','').rstrip('/');token=os.getenv('SONVANE_RELAY_TOKEN','')
 if not backend or not token:return JSONResponse({'detail':'Sonvane is being connected. Please check back shortly.'},503)
 if request.method not in ('GET','HEAD'):
  origin=request.headers.get('origin','')
  if origin!=os.getenv('SONVANE_PUBLIC_ORIGIN'):return JSONResponse({'detail':'Origin mismatch'},403)
 body=bytearray()
 async for chunk in request.stream():
  body.extend(chunk)
  if len(body)>32*1024*1024:return JSONResponse({'detail':'For this demo, use a video under 32 MB.'},413)
 headers={k:v for k,v in request.headers.items() if k.lower() not in {'host','authorization','origin','connection','content-length','accept-encoding'}}
 headers['authorization']='Bearer '+token
 target='/demo/' if not path else '/'+path
 try:
  async with httpx.AsyncClient(timeout=190,follow_redirects=False) as client:
   result=await client.request(request.method,backend+target,params=request.query_params,headers=headers,content=bytes(body))
 except httpx.HTTPError:return JSONResponse({'detail':'The GPU server is reconnecting. Please try again shortly.'},503)
 output_headers={k:v for k,v in result.headers.items() if k.lower() not in {'content-length','content-encoding','transfer-encoding','connection','server'}}
 return Response(result.content,status_code=result.status_code,headers=output_headers)
