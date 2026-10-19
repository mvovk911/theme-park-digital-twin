"""CPU preparation contracts for static native design comparisons."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.render_circulation import ROOT, camera_specs, camera_transform, composition_source, prepare_inputs


def test_default_camera_pair_preserves_prior_capture_names():
    assert [x['name'] for x in camera_specs()] == ['overview', 'plan-view']
    assert camera_specs()[0]['eye_m'] == [170., -220., 220.]
    assert camera_specs()[1]['eye_m'] == [0., -35., 245.]
    assert len(camera_specs('all')) == 3
    with pytest.raises(ValueError):
        camera_specs('unknown')


def test_shared_closeup_camera_has_orthonormal_basis():
    spec = camera_specs('dining-closeup')[0]
    assert spec['target_m'] == [-9., -26.4, .3]
    matrix = ast.literal_eval(camera_transform(spec))
    for i in range(3):
        for j in range(3):
            dot = sum(matrix[i][k] * matrix[j][k] for k in range(3))
            assert dot == pytest.approx(1 if i == j else 0)
    assert matrix[3] == tuple(spec['eye_m']) + (1.,)


def test_baseline_default_uses_committed_overlay(tmp_path):
    inputs = prepare_inputs(tmp_path)
    assert inputs['layers'] == [ROOT / 'assets/circulation_overlay.usda', ROOT / 'assets/park.usdc']
    assert inputs['variant_layer_sha256'] is None
    assert inputs['graph_sha256'] == inputs['identity']['baseline_graph_sha256']


def test_design_layer_is_stronger_than_baseline_and_uses_variant_graph(tmp_path):
    inputs = prepare_inputs(tmp_path, 'dining_connection')
    assert [record['role'] for record in inputs['source_records']] == [
        'diagnostic_overlay', 'physical_design_variant', 'baseline_scene']
    assert inputs['layers'][1] == ROOT / 'assets/variants/dining_connection.usda'
    assert inputs['graph']['asset_entrances']['FOOD_COURT'] == 'food_connector_entrance'
    assert inputs['variant_layer_sha256'] == inputs['identity']['variant_layer_sha256']
    overlay = inputs['layers'][0].read_text()
    assert 'dining_connector_link' in overlay
    assert 'food_missing_link' not in overlay


def test_clean_design_composition_omits_diagnostics(tmp_path):
    inputs = prepare_inputs(tmp_path, 'dining_connection', 'none')
    assert inputs['overlay_sha256'] is None
    assert inputs['overlay_authoring_helper_sha256'] is None
    assert len(inputs['layers']) == 2
    source = composition_source(inputs['layers'], camera_specs('dining-closeup')[0])
    assert source.index('dining_connection.usda@') < source.index('park.usdc@')
    assert 'upAxis = "Z"' in source and 'metersPerUnit = 1' in source
    assert 'def RenderVar "LdrColor" {\n   string sourceName = "LdrColor"\n' in source


def test_unsafe_reference_delimiters_are_rejected():
    for path in ('/tmp/a@b.usda', '/tmp/a\nb.usda', '/tmp/a\rb.usda'):
        with pytest.raises(ValueError, match='reference path'):
            composition_source([path], camera_specs()[0])


def test_preparation_does_not_edit_baseline_or_design_assets(tmp_path):
    assets = [ROOT / name for name in ['assets/park.usdc', 'assets/park.usda',
              'assets/circulation_graph.json', 'assets/circulation_overlay.usda',
              'assets/variants/dining_connection.usda', 'assets/variants/dining_circulation_graph.json']]
    hashes = {path: hashlib.sha256(path.read_bytes()).digest() for path in assets}
    prepare_inputs(tmp_path, 'dining_connection')
    assert all(hashlib.sha256(path.read_bytes()).digest() == value for path, value in hashes.items())


def test_cpu_prepare_report_cannot_be_mistaken_for_native_render(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/render_circulation.py'),
                             '--output', str(tmp_path), '--variant', 'dining_connection',
                             '--view', 'dining-closeup', '--overlay', 'none', '--prepare-only'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['mode'] == 'cpu_preparation_only'
    assert report['prepared'] is True
    assert report['native_rendered'] is report['complete'] is report['live_telemetry'] is False
    assert report['captures'] == [] and report['legend'] == {}
    source = tmp_path / report['prepared_views'][0]['composition_file']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == report['prepared_views'][0]['composition_sha256']
    assert report['variant_layer_sha256'] == report['identity']['variant_layer_sha256']
