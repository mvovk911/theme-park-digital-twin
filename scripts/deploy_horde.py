"""Upload the project through audited hgx exec, in small binary-safe chunks.

Only Git-tracked project source and generated assets are transferred. Commit new source files before deployment. The editable Blender binary is omitted because runtime rendering uses USD. No environment or
credentials. This avoids requiring SSH merely for deployment.
"""
import argparse,base64,io,subprocess,tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--worker',default='park-twin-rtx')
args=parser.parse_args()
buf=io.BytesIO()
excluded={'.venv','.git','runtime','__pycache__','.pytest_cache','data','reference','tools'}
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
    tracked=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0')
    for name in sorted(filter(None,tracked)):
        rel=Path(name)
        path=ROOT/rel
        if path.name.startswith('.env') or path.suffix in {'.pem','.key','.p12','.pfx'}:continue
        if any(p in excluded for p in rel.parts) or not path.is_file():continue
        if path.suffix in {'.pyc','.db','.log','.zip','.gz','.blend'}:continue
        tar.add(path,arcname=str(rel))
data=buf.getvalue()
def remote(command):
    subprocess.run(['hgx','exec',args.worker,'--timeout','120','--',command],check=True)
remote('mkdir -p /home/horde/park-twin/runtime; : > /home/horde/park-twin/runtime/deploy.tar.gz')
for i in range(0,len(data),32000):
    encoded=base64.b64encode(data[i:i+32000]).decode()
    remote("python3 -c \"import base64;open('/home/horde/park-twin/runtime/deploy.tar.gz','ab').write(base64.b64decode('"+encoded+"'))\"")
remote('tar -xzf /home/horde/park-twin/runtime/deploy.tar.gz -C /home/horde/park-twin')
print(f'Deployed {len(data)} bytes to {args.worker}')
