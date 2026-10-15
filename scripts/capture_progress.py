"""Capture real OVRTX views for review; temporarily changes the shared camera."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:8100')
parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/images')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)

def request(path,data=None):
    payload=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request(args.url+path,data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return response.read()

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
        path.write_bytes(request('/render/frame.jpg'))
        captures.append({'file':path.name,'captured_at':datetime.now(timezone.utc).isoformat(),
                         'engine':current['engine'],'ovrtx_version':current['ovrtx_version'],
                         'ovstage_version':current['ovstage_version'],'camera':current['camera'],
                         'frame':current['frame'],'control':control})
        print(path)
finally:
    request('/render/control',{'action':'home'})
(args.output/'render-captures.json').write_text(json.dumps(captures,indent=2)+'\n')
