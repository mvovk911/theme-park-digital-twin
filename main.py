"""Same-origin web gateway for the synthetic backend and real GPU renderer."""
from pathlib import Path
import httpx
from fastapi import HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from backend.app import app

ROOT=Path(__file__).resolve().parent

@app.get('/render/status')
async def render_status():
    try:
        async with httpx.AsyncClient(timeout=2,trust_env=False) as client:
            r=await client.get('http://127.0.0.1:8091/status');r.raise_for_status();return r.json()
    except Exception:
        return {'ready':False,'fps':0,'frame':0,'width':1280,'height':720,'selected_asset':None,
                'camera':{},'error':'Renderer is starting or unavailable','projected_assets':[]}

@app.api_route('/render/{path:path}',methods=['GET','POST'])
async def render_proxy(path:str,request:Request):
    if path not in {'frame.jpg','control','pick'}:raise HTTPException(404)
    try:
        async with httpx.AsyncClient(timeout=20,trust_env=False) as client:
            r=await client.request(request.method,'http://127.0.0.1:8091/'+path,
                content=await request.body(),headers={'Content-Type':'application/json'})
            return Response(r.content,status_code=r.status_code,media_type=r.headers.get('content-type'),
                            headers={'Cache-Control':'no-store'})
    except httpx.HTTPError as e:raise HTTPException(503,'RTX renderer unavailable') from e

app.mount('/',StaticFiles(directory=str(ROOT/'frontend'),html=True),name='frontend')
