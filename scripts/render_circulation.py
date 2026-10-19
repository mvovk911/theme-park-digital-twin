"""Render a static circulation design review with real OVStage and OVRTX.

Loads the original park and additive diagnostic overlay into a separate native
stage. It does not connect to, control or impersonate the live park application.
Run with the GPU environment's Python; output includes exact input/image hashes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=60)
    args = parser.parse_args()
    if not 20 <= args.frames <= 240:
        parser.error('--frames must be between 20 and 240')
    from modeling.circulation import load_graph
    graph = load_graph()
    scene = ROOT / 'assets/park.usdc'
    overlay = ROOT / 'assets/circulation_overlay.usda'
    if digest(scene) != graph['source_scene_sha256']:
        raise ValueError('Circulation graph is registered to a different park scene')
    if any('@' in str(p) or '\n' in str(p) for p in (scene, overlay)):
        raise ValueError('Unsupported USD reference path')
    args.output.mkdir(parents=True, exist_ok=True)
    import numpy as np
    import ovstage
    import ovrtx
    from PIL import Image

    report = {'kind': 'static_ovstage_ovrtx_circulation_design_review',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'live_telemetry': False, 'synthetic': True,
              'scene_sha256': digest(scene), 'overlay_sha256': digest(overlay),
              'graph_sha256': digest(ROOT / 'assets/circulation_graph.json'),
              'script_sha256': digest(Path(__file__)),
              'ovstage_version': ovstage.__version__, 'ovrtx_version': ovrtx.__version__,
              'legend': {'cyan': 'authored partial circulation', 'amber_dashes': 'missing connection',
                         'red_dashes': 'known obstruction', 'yellow_sphere': 'authored entrance or approach'},
              'limitations': graph['scope'], 'captures': [], 'cleanup_errors': [], 'complete': False}
    renderer = stage = None
    attached = False
    product = '/Render/Camera'
    width, height = 1600, 1000
    begin = time.monotonic()
    try:
        renderer = ovrtx.Renderer(config=ovrtx.RendererConfig(log_file_path=str(args.output / 'ovrtx.log')))
        stage = ovstage.Stage('aster.circulation.design-review')
        renderer.attach_ovstage(stage)
        attached = True
        ordinal = 0
        for name, eye in [('overview', (170., -220., 220.)), ('plan-view', (0., -35., 245.))]:
            back = np.array(eye) - np.array((0., 0., 0.))
            back /= np.linalg.norm(back)
            right = np.cross((0., 0., 1.), back)
            right /= np.linalg.norm(right)
            up = np.cross(back, right)
            matrix = np.eye(4)
            matrix[0, :3], matrix[1, :3], matrix[2, :3], matrix[3, :3] = right, up, back, eye
            transform = '(' + ', '.join('(' + ', '.join(str(float(v)) for v in row) + ')' for row in matrix) + ')'
            source = f'''#usda 1.0
(subLayers = [@{overlay}@, @{scene}@]
 metersPerUnit = 1
 upAxis = "Z")
over "World" {{
  over "Camera" {{
    float focalLength = 32
    float horizontalAperture = 36
    float verticalAperture = {36 * height / width}
    matrix4d xformOp:transform = {transform}
    uniform token[] xformOpOrder = ["xformOp:transform"]
  }}
}}
def Scope "Render" {{
 def RenderProduct "Camera" {{
  rel camera = </World/Camera>
  uint[] deviceIds = [0]
  int2 resolution = ({width}, {height})
  token omni:rtx:rendermode = "RealTimePathTracing"
  rel orderedVars = [<LdrColor>]
  def RenderVar "LdrColor" {{
   string sourceName = "LdrColor"
  }}
 }}
}}'''
            ordinal += 1
            ovstage.population.open_usd_from_string(stage, source, ordinal=ordinal)
            stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()
            pixels = None
            for _ in range(args.frames):
                products = renderer.step(render_products={product}, delta_time=1 / 30, ordinal=ordinal)
                frames = products[product].frames
                for frame in frames:
                    mapped = frame.render_vars[product + '/LdrColor'].map(device=ovrtx.Device.CPU)
                    pixels = np.from_dlpack(mapped).copy()
                    mapped.unmap()
                    del mapped, frame
                del frames, products
            if pixels is None:
                raise RuntimeError('Native renderer returned no color frame')
            output = args.output / (name + '.png')
            Image.fromarray(pixels).convert('RGB').save(output)
            report['captures'].append({'file': output.name, 'sha256': digest(output),
                                       'eye_m': list(eye), 'target_m': [0, 0, 0],
                                       'width': width, 'height': height, 'frames': args.frames})
        report['complete'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        for operation in ([renderer.detach_ovstage] if attached else []) + ([stage.destroy] if stage else []) + ([renderer.destroy] if renderer else []):
            try:
                operation()
            except Exception as exc:
                report['cleanup_errors'].append(f'{type(exc).__name__}: {exc}')
        if report['cleanup_errors']:
            report['complete'] = False
        report['elapsed_seconds'] = round(time.monotonic() - begin, 3)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
