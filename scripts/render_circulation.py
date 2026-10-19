"""Render static authored circulation designs with real OVStage and OVRTX.

The default preserves the baseline diagnostic overview and plan-view capture.
Choose a dining variant and a shared close-up camera to compare physical designs.
This isolated stage has no live telemetry, renderer connection, or actuation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WIDTH, HEIGHT = 1600, 1000
LEGEND = {'cyan': 'authored partial circulation', 'amber_dashes': 'missing connection',
          'red_dashes': 'known obstruction', 'yellow_sphere': 'authored entrance or approach'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def camera_specs(view=None):
    specs = [
        {'name': 'overview', 'eye_m': [170., -220., 220.], 'target_m': [0., 0., 0.], 'focal_length_mm': 32},
        {'name': 'plan-view', 'eye_m': [0., -35., 245.], 'target_m': [0., 0., 0.], 'focal_length_mm': 32},
        {'name': 'dining-closeup', 'eye_m': [-1., -43., 17.], 'target_m': [-9., -26.4, .3], 'focal_length_mm': 42},
    ]
    if view is None:
        return specs[:2]  # Preserve the original default camera pair.
    if view == 'all':
        return specs
    selected = [spec for spec in specs if spec['name'] == view]
    if not selected:
        raise ValueError('Unknown review camera')
    return selected


def _normalized(vector):
    length = math.sqrt(sum(v * v for v in vector))
    if length < 1e-12:
        raise ValueError('Degenerate camera basis')
    return [v / length for v in vector]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def camera_transform(spec):
    back = _normalized([a - b for a, b in zip(spec['eye_m'], spec['target_m'])])
    right = _normalized(_cross([0., 0., 1.], back))
    up = _cross(back, right)
    rows = [right + [0.], up + [0.], back + [0.], spec['eye_m'] + [1.]]
    return '(' + ', '.join('(' + ', '.join(str(float(v)) for v in row) + ')' for row in rows) + ')'


def composition_source(layers, spec):
    paths = [Path(path).resolve() for path in layers]
    if any('@' in str(p) or '\n' in str(p) or '\r' in str(p) for p in paths):
        raise ValueError('Unsupported USD reference path')
    layer_text = ', '.join('@' + str(path) + '@' for path in paths)
    return f'''#usda 1.0
(
 subLayers = [{layer_text}]
 metersPerUnit = 1
 upAxis = "Z"
)
over "World" {{
  over "Camera" {{
    float focalLength = {spec['focal_length_mm']}
    float horizontalAperture = 36
    float verticalAperture = {36 * HEIGHT / WIDTH}
    matrix4d xformOp:transform = {camera_transform(spec)}
    uniform token[] xformOpOrder = ["xformOp:transform"]
  }}
}}
def Scope "Render" {{
 def RenderProduct "Camera" {{
  rel camera = </World/Camera>
  uint[] deviceIds = [0]
  int2 resolution = ({WIDTH}, {HEIGHT})
  token omni:rtx:rendermode = "RealTimePathTracing"
  rel orderedVars = [<LdrColor>]
  def RenderVar "LdrColor" {{
   string sourceName = "LdrColor"
  }}
 }}
}}
'''


def prepare_inputs(output, variant='baseline', overlay_mode='diagnostic'):
    """Validate all declared identities and author only output-local derivatives."""
    from backend.spatial.service import SpatialService
    from modeling.circulation import write_overlay
    if overlay_mode not in ('diagnostic', 'none'):
        raise ValueError('Unknown overlay mode')
    envelope = SpatialService(ROOT).graph(variant)
    graph = envelope['graph']
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene = ROOT / 'assets/park.usdc'
    layers, source_records = [], []
    overlay = None
    if overlay_mode == 'diagnostic':
        if variant == 'baseline':
            overlay = ROOT / 'assets/circulation_overlay.usda'
            # Verify that the committed diagnostic still matches its declared graph.
            expected = output / 'expected-baseline-overlay.usda'
            write_overlay(graph, expected)
            if digest(expected) != digest(overlay):
                raise ValueError('Baseline diagnostic overlay differs from graph authoring output')
        else:
            overlay = output / 'dining-circulation-overlay.usda'
            write_overlay(graph, overlay)
        layers.append(overlay)
        source_records.append({'role': 'diagnostic_overlay', 'file': str(overlay), 'sha256': digest(overlay)})
    variant_layer = None
    if variant == 'dining_connection':
        variant_layer = ROOT / 'assets/variants/dining_connection.usda'
        layers.append(variant_layer)  # Stronger than baseline, weaker than diagnostics.
        source_records.append({'role': 'physical_design_variant', 'file': str(variant_layer), 'sha256': digest(variant_layer)})
    layers.append(scene)
    source_records.append({'role': 'baseline_scene', 'file': str(scene), 'sha256': digest(scene)})
    return {
        'layers': layers, 'graph': graph, 'identity': envelope['identity'],
        'source_records': source_records, 'scene_sha256': digest(scene),
        'overlay_sha256': digest(overlay) if overlay else None,
        'variant_layer_sha256': digest(variant_layer) if variant_layer else None,
        'graph_sha256': envelope['identity']['graph_sha256'],
        'overlay_authoring_helper_sha256': digest(ROOT / 'modeling/circulation.py') if overlay else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--variant', choices=['baseline', 'dining_connection'], default='baseline')
    parser.add_argument('--view', choices=['overview', 'plan-view', 'dining-closeup', 'all'],
                        help='Omit to preserve the original overview + plan-view pair')
    parser.add_argument('--overlay', choices=['diagnostic', 'none'], default='diagnostic')
    parser.add_argument('--prepare-only', action='store_true',
                        help='Write hash-bound composition sources without importing native rendering libraries')
    args = parser.parse_args()
    if not 20 <= args.frames <= 240:
        parser.error('--frames must be between 20 and 240')
    args.output = args.output.resolve()
    inputs = prepare_inputs(args.output, args.variant, args.overlay)
    specs = camera_specs(args.view)
    prepared = []
    for spec in specs:
        source = composition_source(inputs['layers'], spec)
        path = args.output / (spec['name'] + '-composition.usda')
        path.write_text(source)
        prepared.append({**spec, 'composition_file': path.name, 'composition_sha256': digest(path)})
    report = {'kind': 'static_ovstage_ovrtx_circulation_design_review',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'live_telemetry': False, 'synthetic': True, 'execution_authority': 'none',
              'variant': args.variant, 'overlay_mode': args.overlay,
              'identity': inputs['identity'],
              'scene_sha256': inputs['scene_sha256'], 'overlay_sha256': inputs['overlay_sha256'],
              'variant_layer_sha256': inputs['variant_layer_sha256'],
              'graph_sha256': inputs['graph_sha256'],
              'script_sha256': digest(Path(__file__)),
              'overlay_authoring_helper_sha256': inputs['overlay_authoring_helper_sha256'],
              'composition_layers_strongest_first': inputs['source_records'],
              'prepared_views': prepared,
              'legend': LEGEND if args.overlay == 'diagnostic' else {},
              'limitations': inputs['graph']['scope'],
              'design_limitations': [
                  'Static authored geometry only; no live measurements, guest movement or operating benefit',
                  'A render is not proof of practical passing clearance, accessibility, capacity or physical safety',
                  'The unchanged baseline and design variant use exactly the same requested camera',
              ],
              'captures': [], 'cleanup_errors': [], 'prepared': True, 'native_rendered': False, 'complete': False}
    if args.prepare_only:
        report['mode'] = 'cpu_preparation_only'
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
        return 0
    import numpy as np
    import ovstage
    import ovrtx
    from PIL import Image
    report.update(ovstage_version=ovstage.__version__, ovrtx_version=ovrtx.__version__, mode='native_render')
    renderer = stage = None
    attached = False
    product = '/Render/Camera'
    begin = time.monotonic()
    try:
        renderer = ovrtx.Renderer(config=ovrtx.RendererConfig(log_file_path=str(args.output / 'ovrtx.log')))
        stage = ovstage.Stage('aster.circulation.design-review')
        renderer.attach_ovstage(stage)
        attached = True
        for ordinal, spec in enumerate(prepared, 1):
            source = (args.output / spec['composition_file']).read_text()
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
            output = args.output / (spec['name'] + '.png')
            Image.fromarray(pixels).convert('RGB').save(output)
            report['captures'].append({**spec, 'file': output.name, 'sha256': digest(output),
                                       'width': WIDTH, 'height': HEIGHT, 'frames': args.frames,
                                       'native_rendered': True})
        report['native_rendered'] = True
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
