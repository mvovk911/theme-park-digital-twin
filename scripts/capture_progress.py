"""Capture real OVRTX views for review; temporarily changes the shared camera."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import time
import urllib.request

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:8100')
parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/images')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)

def request(path,data=None,with_headers=False):
    payload=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request(args.url+path,data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        body=response.read()
        return (body, dict(response.headers)) if with_headers else body

def status():return json.loads(request('/render/status'))

captures=[]
try:
    for name,control in [
        ('render-overview',{'action':'home'}),
        ('render-wheel',{'action':'focus','asset_id':'RIDE_WHEEL'}),
        ('render-coaster',{'action':'focus','asset_id':'RIDE_COASTER'}),
        ('render-utilities',{'action':'focus','asset_id':'POWER_HUB'}),
    ]:
        before=status()
        if not before.get('ready'):raise RuntimeError('Renderer is not ready')
        request('/render/control',control)
        deadline=time.monotonic()+15
        while True:
            current=status()
            if current.get('frame',0)>before['frame']+15:break
            if time.monotonic()>deadline:raise TimeoutError('No fresh GPU frame')
            time.sleep(.15)
        path=args.output/(name+'.jpg')
        jpeg,headers=request('/render/frame.jpg',with_headers=True)
        evidence={key.lower():value for key,value in headers.items() if key.lower().startswith('x-')}
        context=json.loads(evidence.get('x-frame-context','{}'))
        if not context or not evidence.get('x-source-revision'):
            raise RuntimeError('JPEG lacks exact frame/source evidence')
        path.write_bytes(jpeg)
        captures.append({'file':path.name,'captured_at':datetime.now(timezone.utc).isoformat(),
                         'engine':current['engine'],'ovrtx_version':current['ovrtx_version'],
                         'ovstage_version':current['ovstage_version'],
                         'source_identity':current.get('source_identity'),
                         'sha256':hashlib.sha256(jpeg).hexdigest(),
                         'camera':context.get('camera'),
                         'frame':int(evidence['x-frame-number']),
                         'frame_headers':evidence,'control':control})
        print(path)
finally:
    request('/render/control',{'action':'home'})
(args.output/'render-captures.json').write_text(json.dumps(captures,indent=2)+'\n')
