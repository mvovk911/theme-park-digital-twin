"""Optional immutable native previews, matched to the installed graph identity.

No renderer or USD SDK is loaded. Reports are consistency evidence, not signed
attestations. Fixed artifact paths never come from the report or HTTP caller.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import struct
from types import MappingProxyType
import zlib

from .service import _hash, _json

PREVIEW_ROOT = Path('docs/images/fox-cycle-20261019/dining-design')
VARIANTS = ('baseline', 'dining_connection')
IMAGE_NAME = 'dining-closeup.png'
COMPOSITION_NAME = 'dining-closeup-composition.usda'
MAX_REPORT_BYTES = 128 * 1024
MAX_COMPOSITION_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024
CAMERA = {'eye_m': [-1., -43., 17.], 'target_m': [-9., -26.4, .3],
          'focal_length_mm': 42, 'width': 1600, 'height': 1000}


class PreviewUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class _Preview:
    image: bytes
    metadata_json: bytes
    headers_json: bytes


def _read(root, relative, limit):
    root = root.resolve()
    path = root / relative
    if any((root / Path(*relative.parts[:end])).is_symlink() for end in range(1, len(relative.parts) + 1)):
        raise ValueError('Preview symlinks are not supported')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Preview path is outside project')
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('Preview must be a regular file')
        data = handle.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError('Preview file is empty or exceeds its size bound')
    return data


def _png_dimensions(data):
    """Check bounded PNG chunks/CRCs without a GPU or image-package dependency."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Preview is not PNG')
    cursor, dimensions, has_pixels = 8, None, False
    while cursor + 12 <= len(data):
        size = struct.unpack('>I', data[cursor:cursor + 4])[0]
        end = cursor + size + 12
        if end > len(data):
            raise ValueError('Truncated PNG chunk')
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:end - 4]
        expected_crc = struct.unpack('>I', data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != expected_crc:
            raise ValueError('PNG chunk checksum mismatch')
        if dimensions is None:
            if kind != b'IHDR' or size != 13:
                raise ValueError('PNG has no valid first header')
            dimensions = struct.unpack('>II', payload[:8])
        elif kind == b'IHDR':
            raise ValueError('Duplicate PNG header')
        has_pixels |= kind == b'IDAT' and bool(payload)
        if kind == b'IEND':
            if size or end != len(data) or not has_pixels:
                raise ValueError('Invalid PNG end or missing pixels')
            return dimensions
        cursor = end
    raise ValueError('PNG has no end chunk')


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Capture timestamp must be text')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Capture timestamp must include timezone')
    return parsed


class SpatialPreviews:
    """Capture optional verified bytes once; missing/bad assets stay unavailable.

    Restart to install new captures, exactly as for the immutable graph snapshot.
    A bad optional preview never prevents the core graph API from installing.
    """
    def __init__(self, project_root, service):
        snapshots = {}
        for variant in VARIANTS:
            try:
                snapshots[variant] = self._load(Path(project_root), variant, service.graph(variant)['identity'])
            except (OSError, ValueError, KeyError, TypeError, RecursionError, OverflowError, struct.error):
                snapshots[variant] = None
        if all(snapshots.values()):
            cameras = [json.loads(snapshots[v].metadata_json)['camera'] for v in VARIANTS]
            if cameras[0] != cameras[1]:
                snapshots = {variant: None for variant in VARIANTS}
        self._snapshots = MappingProxyType(snapshots)

    @staticmethod
    def _load(root, variant, identity):
        folder = PREVIEW_ROOT / variant
        report_raw = _read(root, folder / 'report.json', MAX_REPORT_BYTES)
        image = _read(root, folder / IMAGE_NAME, MAX_IMAGE_BYTES)
        composition = _read(root, folder / COMPOSITION_NAME, MAX_COMPOSITION_BYTES)
        report = _json(report_raw)
        if not isinstance(report, dict):
            raise ValueError('Preview report must be an object')
        required = {'kind': 'static_ovstage_ovrtx_circulation_design_review', 'variant': variant,
                    'mode': 'native_render', 'overlay_mode': 'none', 'execution_authority': 'none'}
        if any(report.get(key) != value for key, value in required.items()):
            raise ValueError('Unexpected preview report mode')
        if any(report.get(key) is not True for key in ('complete', 'native_rendered', 'prepared', 'synthetic')):
            raise ValueError('Incomplete native preview')
        if report.get('live_telemetry') is not False or report.get('cleanup_errors') != [] or report.get('error') or report.get('errors'):
            raise ValueError('Preview has live data or rendering errors')
        if report.get('identity') != identity:
            raise ValueError('Preview does not match installed graph identity')
        for key, expected in {'graph_sha256': identity['graph_sha256'], 'scene_sha256': identity['baseline_scene_sha256'],
                              'variant_layer_sha256': identity['variant_layer_sha256'], 'overlay_sha256': None,
                              'overlay_authoring_helper_sha256': None}.items():
            if report.get(key) != expected:
                raise ValueError('Preview source hash mismatch')
        layers = report['composition_layers_strongest_first']
        expected_layers = [('baseline_scene', identity['baseline_scene_sha256'], 'assets/park.usdc')]
        if variant == 'dining_connection':
            expected_layers.insert(0, ('physical_design_variant', identity['variant_layer_sha256'], 'assets/variants/dining_connection.usda'))
        if not isinstance(layers, list) or len(layers) != len(expected_layers):
            raise ValueError('Unexpected composition layers')
        for record, (role, sha, suffix) in zip(layers, expected_layers):
            if not isinstance(record, dict) or record['role'] != role or record['sha256'] != sha or not isinstance(record['file'], str) or not record['file'].endswith('/' + suffix):
                raise ValueError('Unexpected layer order or identity')
        # Inspect strings only. Remote paths are never opened locally.
        source = composition.decode('utf-8')
        matches = re.findall(r'\bsubLayers\s*=\s*\[([^\]]*)\]', source)
        paths = re.findall(r'@([^@]+)@', matches[0]) if len(matches) == 1 else []
        if len(paths) != len(expected_layers) or any(not path.endswith('/' + suffix) for path, (_, _, suffix) in zip(paths, expected_layers)):
            raise ValueError('Composition does not declare reported layer order')
        captures = report['captures']
        if not isinstance(captures, list) or len(captures) != 1 or not isinstance(captures[0], dict):
            raise ValueError('Expected exactly one close-up capture')
        capture = captures[0]
        if capture['name'] != 'dining-closeup' or capture['file'] != IMAGE_NAME or capture['composition_file'] != COMPOSITION_NAME:
            raise ValueError('Unexpected capture artifact names')
        if capture.get('native_rendered') is not True or type(capture['frames']) is not int or not 20 <= capture['frames'] <= 240:
            raise ValueError('Capture is not a completed native render')
        camera = {key: capture[key] for key in CAMERA}
        if camera != CAMERA or _png_dimensions(image) != (CAMERA['width'], CAMERA['height']):
            raise ValueError('Preview camera or image dimensions mismatch')
        if capture['sha256'] != _hash(image) or capture['composition_sha256'] != _hash(composition):
            raise ValueError('Capture image or composition hash mismatch')
        prepared = {key: capture[key] for key in ('name', 'eye_m', 'target_m', 'focal_length_mm', 'composition_file', 'composition_sha256')}
        if report['prepared_views'] != [prepared]:
            raise ValueError('Prepared and rendered camera evidence disagree')
        if _timestamp(report['finished_at']) < _timestamp(report['started_at']):
            raise ValueError('Capture timestamps are reversed')
        versions = {key: report[key] for key in ('ovstage_version', 'ovrtx_version')}
        if any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9.+_-]{1,80}', value) for value in versions.values()):
            raise ValueError('Invalid native SDK version metadata')
        hashes = {'image_sha256': _hash(image), 'report_sha256': _hash(report_raw), 'composition_sha256': _hash(composition)}
        metadata = {'variant': variant, 'mode': 'static_native', 'identity': identity, 'camera': camera,
                    'native_sdk_versions': versions, **hashes, 'capture_started_at': report['started_at'],
                    'capture_finished_at': report['finished_at'], 'verified_at': datetime.now(timezone.utc).isoformat(),
                    'snapshot_policy': 'immutable_until_restart', 'native_rendered': True,
                    'live_telemetry': False, 'synthetic': True, 'execution_authority': 'none',
                    'integrity_scope': 'Artifact consistency only; no cryptographic signature or independent rendering attestation',
                    'limitations': ['Static authored geometry; not live telemetry, physical guidance, accessibility certification or operational benefit']}
        headers = {'X-Spatial-Graph-Sha256': identity['graph_sha256'],
                   'X-Spatial-Scene-Sha256': identity['baseline_scene_sha256'],
                   'X-Spatial-Variant-Layer-Sha256': identity['variant_layer_sha256'] or '',
                   'X-Spatial-Preview-Image-Sha256': hashes['image_sha256'],
                   'X-Spatial-Preview-Report-Sha256': hashes['report_sha256'],
                   'X-Spatial-Preview-Mode': 'static_native', 'Cache-Control': 'no-store'}
        return _Preview(image, json.dumps(metadata).encode(), json.dumps(headers).encode())

    def get(self, variant):
        snapshot = self._snapshots.get(variant)
        if snapshot is None:
            raise PreviewUnavailable('Verified native preview is unavailable for this installed design; no fallback image is served')
        return snapshot.image, json.loads(snapshot.metadata_json), json.loads(snapshot.headers_json)
