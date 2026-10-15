"""A real OVRTX renderer with OVStage scene ownership and a small HTTP control API.

The render loop alone touches native SDK objects. HTTP handlers submit commands
through a queue; JPEG output is an actual GPU render, never a substitute scene.
"""
import io
import json
import math
import os
from pathlib import Path
import queue
import threading
import time
import traceback
import sys

import numpy as np
from PIL import Image
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
import uvicorn
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modeling.animate import wheel_transforms, CoasterRoute
RUNTIME = ROOT / 'runtime'
RUNTIME.mkdir(exist_ok=True)
WIDTH, HEIGHT = 1280, 720
FOCAL, APERTURE = 32., 36.
PRODUCT = '/Render/Camera'
COLOR = PRODUCT + '/LdrColor'
app = FastAPI(title='Aster Park OVRTX render service')
commands = queue.Queue(maxsize=128)
lock = threading.Lock()
state = dict(ready=False, fps=0, frame=0, width=WIDTH, height=HEIGHT,
             selected_asset=None, camera={}, error=None, projected_assets=[],
             engine='NVIDIA OVRTX + OVStage', phase='initializing', layer='operations')
latest_jpeg = b''
registry = {}


class Control(BaseModel):
    action: str
    dx: float = Field(0, ge=-2, le=2)
    dy: float = Field(0, ge=-2, le=2)
    delta: float = Field(0, ge=-2000, le=2000)
    asset_id: str | None = None
    layer: str = 'operations'


class Pick(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


@app.get('/status')
def status():
    with lock:
        return dict(state)


@app.get('/frame.jpg')
def frame():
    with lock:
        data = latest_jpeg
    if not data:
        raise HTTPException(503, 'RTX renderer is warming up')
    return Response(data, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@app.post('/control')
def control(data: Control):
    if data.action not in {'orbit', 'zoom', 'home', 'focus', 'select', 'layer'}:
        raise HTTPException(400, 'Unknown control')
    if data.asset_id and data.asset_id not in registry:
        raise HTTPException(404, 'Unknown scene asset')
    try:
        commands.put_nowait(('control', data.model_dump(), None))
    except queue.Full:
        raise HTTPException(429, 'Renderer control queue is full')
    return {'accepted': True}


@app.post('/pick')
def pick(data: Pick):
    if not state['ready']:
        raise HTTPException(503, 'Renderer not ready')
    completion = {'event': threading.Event(), 'result': None}
    try:
        commands.put_nowait(('pick', data.model_dump(), completion))
    except queue.Full:
        raise HTTPException(429, 'Renderer control queue is full')
    if not completion['event'].wait(15):
        raise HTTPException(504, 'Renderer pick timed out')
    if 'error' in completion['result']:
        raise HTTPException(500, completion['result']['error'])
    return completion['result']


def unit(x):
    x = np.asarray(x, dtype=np.float64)
    return x / max(np.linalg.norm(x), 1e-9)


def camera_matrix(target, radius, yaw, pitch):
    eye = np.array(target) + radius * np.array([
        math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)])
    back = unit(eye-target)
    right = unit(np.cross([0,0,1], back))
    up = np.cross(back, right)
    mat = np.eye(4, dtype=np.float64)
    mat[0,:3], mat[1,:3], mat[2,:3], mat[3,:3] = right,up,back,eye
    return mat


def project_assets(mat):
    out=[]
    for aid,a in registry.items():
        p=np.array(a['position'], dtype=float)+[0,0,3]
        rel=p-mat[3,:3]; depth=-np.dot(rel,mat[2,:3])
        if depth<=0: continue
        xx=.5+np.dot(rel,mat[0,:3])*FOCAL/(depth*APERTURE)
        yy=.5-np.dot(rel,mat[1,:3])*FOCAL/(depth*APERTURE*HEIGHT/WIDTH)
        out.append({'id':aid,'x':float(xx),'y':float(yy),'visible':bool(0<xx<1 and 0<yy<1)})
    return out


def render_loop():
    global latest_jpeg, registry
    # Import SDKs only in the process owning the GPU. Do not import pxr here.
    import ovrtx
    import ovstage
    renderer=stage=paths=None
    queries={}
    try:
        registry={a['asset_id']:a for a in json.loads((ROOT/'assets/asset_registry.json').read_text())['assets']}
        ride=json.loads((ROOT/'assets/ride_paths.json').read_text())
        route=CoasterRoute(ride['coaster']['points'])
        state['phase']='compiling GPU shaders'
        renderer=ovrtx.Renderer(config=ovrtx.RendererConfig(
            log_file_path=str(RUNTIME/'ovrtx.log'), selection_outline_width=3))
        stage=ovstage.Stage('aster.park.live')
        renderer.attach_ovstage(stage)
        source=f'''#usda 1.0
        (subLayers = [@{ROOT / 'assets/park.usdc'}@]
         metersPerUnit = 1
         upAxis = "Z")
        over "World"
        {{
          over "Camera"
          {{
          float focalLength = {FOCAL}
          float horizontalAperture = {APERTURE}
          float verticalAperture = {APERTURE*HEIGHT/WIDTH}
          }}
        }}
        def Scope "Render" {{
          def RenderProduct "Camera" {{
            rel camera = </World/Camera>
            uint[] deviceIds = [0]
            int2 resolution = ({WIDTH}, {HEIGHT})
            token omni:rtx:rendermode = "RealTimePathTracing"
            rel orderedVars = [<LdrColor>]
            def RenderVar "LdrColor"
            {{
              string sourceName = "LdrColor"
            }}
          }}
        }}'''
        ovstage.population.open_usd_from_string(stage,source,ordinal=1)
        stage.advance_write_floor(1,ovstage.Scope.ALL).wait()
        paths=ovstage.PathDictionary(stage)
        attr=paths.intern_token('omni:xform')
        moving=['/World/Camera','/World/Park/RIDE_COASTER/Train',*wheel_transforms(0)]
        for p in moving:
            pl=paths.create_path_list_from_strings([p])
            queries[p]=(pl,stage.query_from_path_list(pl))
        dtype=ovstage.numpy_to_dldatatype(np.dtype(np.float64),lanes=16)
        def write_transform(path,mat,ordinal):
            a=np.ascontiguousarray(mat,dtype=np.float64).reshape(1,4,4)
            t=ovstage.make_dltensor(a,dtype=dtype,shape=[1],ndim=1)
            stage.write_attribute(queries[path][1],attr,ordinal=ordinal,tensors=t,is_array=False).wait()

        target=np.array([0.,0.,3.]); radius=285.; yaw=math.radians(-54); pitch=math.radians(40)
        ordinal=1; last=time.monotonic(); wheel_angle=0.; train_phase=0.
        last_api=0.; assets={}; selection=[]; pending=None; step_count=0
        client=httpx.Client(timeout=.25,trust_env=False)
        state['phase']='rendering first frame'
        while True:
            begin=time.monotonic(); interval=begin-last; dt=min(interval,.25); last=begin
            if begin-last_api>1.:
                try:
                    response=client.get(os.environ.get('PARK_API_URL','http://127.0.0.1:8100')+'/api/state');response.raise_for_status()
                    snapshot=response.json();assets={a['id']:a for a in snapshot['assets']}
                    state['api_connected']=True
                except Exception:
                    state['api_connected']=False
                last_api=begin
            for _ in range(40):
                if pending: break
                try:kind,data,completion=commands.get_nowait()
                except queue.Empty:break
                if kind=='pick': pending=(data,completion);break
                a=data['action']
                if a=='orbit':
                    yaw-=data['dx']*4.;pitch=np.clip(pitch+data['dy']*3.,.12,1.45)
                elif a=='zoom':radius=float(np.clip(radius*math.exp(data['delta']*.001),18,470))
                elif a=='home':target=np.array([0.,0.,3.]);radius=285.;yaw=math.radians(-54);pitch=math.radians(40)
                elif a in {'focus','select'} and data['asset_id']:
                    aid=data['asset_id'];state['selected_asset']=aid
                    if a=='focus':target=np.array(registry[aid]['position'],dtype=float);radius=83.
                    if selection: renderer.set_selection_outline_group_strings(selection,0)
                    selection=[registry[aid]['prim_path']];renderer.set_selection_outline_group_strings(selection,1)
                elif a=='layer':state['layer']=data['layer']
            mat=camera_matrix(target,radius,yaw,pitch)
            ordinal+=1
            write_transform('/World/Camera',mat,ordinal)
            if assets.get('RIDE_WHEEL',{}).get('status') not in {'closed','fault'}:wheel_angle+=dt*.16
            for path, transform in wheel_transforms(wheel_angle).items():
                write_transform(path,transform,ordinal)
            if assets.get('RIDE_COASTER',{}).get('status') not in {'closed','fault'}:
                train_phase=(train_phase+dt/42)%1
            write_transform('/World/Park/RIDE_COASTER/Train',route.transform(train_phase),ordinal)
            stage.advance_write_floor(ordinal,ovstage.Scope.ALL).wait()
            if pending:
                p,_=pending;x=min(p['x'],1-1/WIDTH);y=min(p['y'],1-1/HEIGHT)
                renderer.enqueue_pick_query(render_product_path=PRODUCT,left_ndc=x,top_ndc=y,
                    right_ndc=min(1,x+1/WIDTH),bottom_ndc=min(1,y+1/HEIGHT),flags=ovrtx.OVRTX_PICK_FLAG_INCLUDE_TRACKED_INFO)
            products=renderer.step(render_products={PRODUCT},delta_time=max(dt,.001),ordinal=ordinal)
            frames=products[PRODUCT].frames
            for frame in frames:
                mapping=frame.render_vars[COLOR].map(device=ovrtx.Device.CPU)
                pixels=np.from_dlpack(mapping).copy();mapping.unmap();del mapping
                if pending:
                    _,completion=pending
                    try:
                        rv=frame.render_vars[ovrtx.OVRTX_RENDER_VAR_PICK_HIT]
                        mp=rv.map(device=ovrtx.Device.CPU)
                        magic=int(np.from_dlpack(mp.params['magic']).reshape(-1)[0])
                        version=int(np.from_dlpack(mp.params['version']).reshape(-1)[0])
                        count=int(np.from_dlpack(mp.params['hitCount']).reshape(-1)[0])
                        hitids=np.from_dlpack(mp['primPath']).copy().reshape(-1)
                        mp.unmap()
                        if magic!=ovrtx.OVRTX_PICK_HIT_MAGIC or version!=ovrtx.OVRTX_PICK_HIT_VERSION:raise RuntimeError('Unexpected pick schema')
                        hit=None
                        if count:
                            value=hitids[0]
                            if isinstance(value,(str,np.str_)): hit=str(value)
                            elif isinstance(value,(bytes,np.bytes_)): hit=value.decode()
                            else: hit=renderer.resolve_prim_path_id(int(value))
                        aid=next((k for k,v in registry.items() if hit and (hit==v['prim_path'] or hit.startswith(v['prim_path']+'/'))),None)
                        if selection:renderer.set_selection_outline_group_strings(selection,0)
                        selection=[hit] if aid else []
                        if selection:renderer.set_selection_outline_group_strings(selection,1)
                        state['selected_asset']=aid
                        completion['result']={'asset_id':aid,'prim_path':hit,'engine':'ovrtx_pick_hit'}
                    except Exception as e:completion['result']={'error':str(e)}
                    completion['event'].set();pending=None
                buf=io.BytesIO();Image.fromarray(pixels).convert('RGB').save(buf,format='JPEG',quality=87)
                step_count+=1;elapsed=max(time.monotonic()-begin,.001)
                with lock:
                    latest_jpeg=buf.getvalue()
                    state.update(ready=True,phase='rendering',frame=step_count,fps=round(1/max(interval,.001),1),
                        camera={'target':target.tolist(),'radius':radius,'yaw':float(yaw),'pitch':float(pitch)},
                        projected_assets=project_assets(mat),error=None,
                        ovrtx_version=ovrtx.__version__,ovstage_version=ovstage.__version__,
                        ride_motion={'coaster_phase':train_phase,'wheel_angle':wheel_angle},
                        ride_status={k:assets.get(k,{}).get('status') for k in ('RIDE_COASTER','RIDE_WHEEL')})
                if step_count==20:
                    Image.fromarray(pixels).save(RUNTIME/'first-render.png')
                del frame
            del frames,products
            time.sleep(max(0,.08-(time.monotonic()-begin)))
    except Exception as e:
        traceback.print_exc()
        with lock:state.update(ready=False,error=str(e),phase='failed')
        # Keep HTTP diagnostics available after initialization failure.
        while True:time.sleep(1)
    finally:
        for pl,q in queries.values():
            q.release().wait();paths.destroy_path_list(pl)
        if paths:paths.destroy()
        if renderer and stage:renderer.detach_ovstage()
        if stage:stage.destroy()
        if renderer:renderer.destroy()


if __name__=='__main__':
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8091,log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True)
    thread.start()
    deadline=time.monotonic()+10
    while not server.started:
        if not thread.is_alive() or time.monotonic()>deadline:
            raise SystemExit('Render HTTP service failed to start; check port 8091')
        time.sleep(.05)
    render_loop()
