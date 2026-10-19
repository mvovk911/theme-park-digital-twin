#!/usr/bin/env python3
"""Reproducible five-page evidence review; defaults to an interim run status."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from xml.sax.saxutils import escape

import fitz
from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/deck-source/fox-review.md'
IMAGES = ROOT / 'docs/images/fox-cycle-20261019'
FONT_ROOT = Path('/usr/share/fonts/truetype/dejavu')
W, H = 960, 540
BG, PANEL, INK, MUTED, TEAL, AMBER = map(HexColor, ['#101d2b', '#1b2d40', '#f3f7fb', '#b4c5d4', '#5de2c2', '#ffd27a'])
REPO = 'https://github.com/mvovk911/theme-park-digital-twin'
FOX = 'https://blogs.nvidia.com/blog/factory-operations-fox-blueprint-ai-brain/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('Run timestamp must be text')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Run timestamp needs timezone')
    return parsed


def run_summary(path):
    if path is None:
        return None
    # Retain the complete interval and source-transition evidence. A 30-second
    # cadence can yield ~960 small gaps, exceeding the former64KiB contract.
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Run summary exceeds4MiB')
    data = json.loads(path.read_text())
    # One dependency-free producer/consumer validator owns duration, coverage,
    # pause and identity-verification rules. The deck does not redefine success.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from operators.analyze_fox_run import validate_review_contract
    validate_review_contract(data)
    return data


class Deck:
    def __init__(self, output, revision, summary):
        self.c = canvas.Canvas(str(output), pagesize=(W, H), invariant=1, pageCompression=1)
        self.c.setTitle('Aster Park — FOX-inspired evidence review')
        self.c.setAuthor('Aster Park project')
        self.c.setCreator('scripts/build_fox_review_deck.py / v1')
        self.c.setSubject('Synthetic digital twin evidence; interim unless both eight-hour tracks are verified complete')
        self.revision, self.summary, self.page = revision, summary, 0
        self.boxes = []

    def text(self, value, x, top, width, size=12, color=INK, max_height=100, bold=False):
        style = ParagraphStyle('body', fontName='ReviewBold' if bold else 'Review', fontSize=size,
                               leading=size * 1.32, textColor=color, spaceAfter=0)
        p = Paragraph(escape(value).replace('\n', '<br/>'), style)
        _, height = p.wrap(width, max_height)
        if height > max_height + .1:
            raise ValueError(f'Page{self.page} text overflow ({height:.1f}>{max_height}): {value[:70]}')
        p.drawOn(self.c, x, H - top - height)
        self.boxes.append({'page': self.page, 'bounds': [x, top, x + width, top + height], 'text': value})
        return height

    def panel(self, x, top, width, height, color=PANEL):
        self.c.setFillColor(color)
        self.c.roundRect(x, H - top - height, width, height, 9, fill=1, stroke=0)

    def image(self, path, x, top, width, height):
        self.panel(x, top, width, height)
        with Image.open(path) as image:
            iw, ih = image.size
        scale = min(width / iw, height / ih)
        dw, dh = iw * scale, ih * scale
        self.c.drawImage(str(path), x + (width - dw) / 2, H - top - (height + dh) / 2, dw, dh, mask='auto')

    def start(self, section, label):
        self.page += 1
        self.c.setFillColor(BG)
        self.c.rect(0, 0, W, H, stroke=0, fill=1)
        self.text('ASTER PARK  /  ' + label, 36, 22, 710, 10, TEAL, 18, True)
        self.text('INTERIM' if self.summary is None else '8H SAMPLED REVIEW', 760, 22, 164, 10, AMBER, 18, True)
        self.text(section['title'], 36, 48, 888, 28, INK, 44, True)
        self.text(section['subtitle'], 36, 95, 888, 11, MUTED, 30)

    def footer(self, sources):
        self.c.setStrokeColor(HexColor('#31465a'))
        self.c.line(36, 26, 924, 26)
        x = 36
        for label, target in sources:
            self.c.setFont('Review', 8)
            self.c.setFillColor(MUTED)
            self.c.drawString(x, 12, label)
            width = pdfmetrics.stringWidth(label, 'Review', 8)
            url = target if target.startswith('https://') else REPO + '/blob/' + self.revision + '/' + target
            self.c.linkURL(url, (x, 9, x + width, 23), relative=0)
            x += width + 18
        self.c.setFillColor(MUTED)
        self.c.drawRightString(924, 12, f'{self.page}/5  •  source {self.revision[:7]}')
        self.c.showPage()


def build(args):
    revision = args.source_revision or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Source revision must be a full40-character Git commit')
    summary = run_summary(args.run_summary)
    output = args.output.resolve()
    if output == (ROOT / 'docs/project-concept.pdf').resolve():
        raise ValueError('Original project concept PDF must remain unchanged')
    output.parent.mkdir(parents=True, exist_ok=True)
    content = json.loads(re.search(r'```deck-json\n(.*?)\n```', SOURCE.read_text(), re.S).group(1))
    for name, file in [('Review', 'DejaVuSans.ttf'), ('ReviewBold', 'DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(FONT_ROOT / file)))
    inputs = [SOURCE, Path(__file__), ROOT / 'docs/progress.md',
              ROOT / 'docs/research/fox-theme-park.md',
              ROOT / 'docs/reviews/2026-10-19-evidence-and-policy-review.md',
              ROOT / 'docs/experiments/2026-10-19-run-status.md',
              IMAGES / 'gpu-incident-afa84a1/report.json',
              IMAGES / 'gpu-incident-afa84a1/direct-proposal-frozen-observations.png']
    incident = json.loads(inputs[-2].read_text())
    if len(incident['checks']) != 6 or incident.get('status') != 'passed':
        raise ValueError('Expected actual six-check GPU incident report')
    native_reports = {}
    for variant in ('baseline', 'dining_connection'):
        folder = IMAGES / 'dining-design' / variant
        report = json.loads((folder / 'report.json').read_text())
        image = folder / 'dining-closeup.png'
        if report.get('complete') is not True or report.get('native_rendered') is not True or report['captures'][0]['sha256'] != sha(image):
            raise ValueError('Native capture evidence mismatch')
        native_reports[variant] = report
        inputs.extend([folder / 'report.json', image, folder / 'dining-closeup-composition.usda'])
    camera_keys = ('eye_m', 'target_m', 'focal_length_mm', 'width', 'height')
    if any(native_reports['baseline']['captures'][0][k] != native_reports['dining_connection']['captures'][0][k] for k in camera_keys):
        raise ValueError('Before/after cameras must match')
    if summary:
        inputs.append(args.run_summary.resolve())
        inputs.append(ROOT / 'operators/analyze_fox_run.py')
    d = Deck(output, revision, summary)

    s = content['architecture']; d.start(s, 'IMPLEMENTED LOOP')
    for i, (title, subtitle, body) in enumerate(s['steps']):
        x = 36 + i * 180
        d.panel(x, 141, 168, 167)
        d.text(title, x + 12, 154, 144, 10, TEAL, 20, True)
        d.text(subtitle, x + 12, 183, 144, 14, INK, 43, True)
        d.text(body, x + 12, 239, 144, 10, MUTED, 60)
        if i < 4:
            d.c.setStrokeColor(TEAL); d.c.line(x + 170, H - 222, x + 178, H - 222)
            d.c.line(x + 175, H - 219, x + 178, H - 222); d.c.line(x + 175, H - 225, x + 178, H - 222)
    for i, (title, body) in enumerate(s['api_groups']):
        x = 36 + i * 302
        d.panel(x, 330, 284, 113)
        d.text(title, x + 14, 344, 256, 10, TEAL if i < 2 else AMBER, 20, True)
        d.text(body, x + 14, 371, 256, 10, MUTED, 62)
    d.text(s['boundary'], 36, 466, 888, 10, AMBER, 36)
    d.footer([('NVIDIA FOX announcement', FOX), ('Implemented / proposed research', 'docs/research/fox-theme-park.md')])

    s = content['incident']; d.start(s, 'CURRENT INCIDENT / ACTUAL GPU APP')
    d.image(IMAGES / 'gpu-incident-afa84a1/direct-proposal-frozen-observations.png', 36, 136, 500, 305)
    d.text('Actual app: frozen source observations', 46, 444, 480, 9, MUTED, 18)
    for i, text in enumerate(s['checks']):
        top = 140 + i * 47
        d.text(f'{i+1:02}', 562, top, 29, 15, TEAL, 25, True)
        d.text(text, 602, top, 322, 11, INK, 42)
    d.text(s['outcome'], 36, 467, 888, 10, TEAL, 30)
    d.text(s['boundary'], 36, 496, 888, 8, MUTED, 16)
    d.footer([('Six-check GPU report', 'docs/images/fox-cycle-20261019/gpu-incident-afa84a1/report.json'), ('Workflow contract', 'docs/bounded-maintenance-workflow.md')])

    s = content['spatial']; d.start(s, 'DESIGN ALTERNATIVE / NATIVE RTX')
    for i, variant in enumerate(('baseline', 'dining_connection')):
        x = 36 + i * 454
        d.text(s['before' if i == 0 else 'after'], x, 130, 434, 12, AMBER if i == 0 else TEAL, 22, True)
        d.image(IMAGES / 'dining-design' / variant / 'dining-closeup.png', x, 160, 434, 271.25)
    for i, item in enumerate(s['controls']):
        d.text(item, 36 + i * 302, 444, 284, 10, INK, 35)
    d.text(s['boundary'], 36, 487, 888, 9, AMBER, 25)
    d.footer([('Spatial contract + limits', 'docs/spatial-api.md'), ('Native capture provenance', 'docs/circulation-native-rendering.md'), ('Actual GPU route/UI report', 'docs/images/fox-cycle-20261019/gpu-spatial-afa84a1/report.json')])

    s = content['value']; d.start(s, 'INDEPENDENT VALUE REVIEW')
    for i, (metric, explanation) in enumerate(s['results']):
        x = 36 + i * 226
        d.panel(x, 143, 210, 108)
        d.text(metric, x + 13, 157, 184, 24, TEAL if i < 2 else AMBER, 35, True)
        d.text(explanation, x + 13, 199, 184, 10, MUTED, 42)
    d.text(s['tradeoff'], 36, 276, 888, 12, INK, 65)
    d.panel(36, 354, 888, 78)
    d.text(s['validation'], 50, 368, 860, 11, MUTED, 62)
    d.text(s['boundary'], 36, 459, 888, 12, AMBER, 43)
    d.footer([('Independent 324-case review', 'docs/reviews/2026-10-19-evidence-and-policy-review.md'), ('Test checkpoint scope', 'docs/progress.md')])

    s = content['pilot']; d.start(s, 'NEXT DECISION / RUN STATUS')
    pilot_width = 528 if summary is None else 434
    for i, (title, body) in enumerate(s['steps']):
        top = 141 + i * 76
        d.text(title, 36, top, pilot_width, 13, TEAL, 23, True)
        d.text(body, 36, top + 26, pilot_width, 11 if summary is None else 10, INK, 45)
    if summary is None:
        d.panel(598, 141, 326, 307)
        d.text('INTERIM\n8-hour observation\nstill in progress', 616, 159, 290, 20, AMBER, 89, True)
        d.text('Two independent tracks:\n• fixed-source API exercise\n• read-only GPU observation\n\nPlanned window: 19 Oct 19:47 to 20 Oct 03:47 UTC. These are planned times, not completion evidence.', 616, 262, 290, 11, MUTED, 133)
        d.text('A known deployment interruption remains in the record. Final counts require both completed ledgers.', 616, 402, 290, 10, AMBER, 41)
    else:
        d.panel(490, 141, 434, 307)
        failures = sum(t['failures'] for t in summary['tracks'].values())
        d.text('Reconciled sampled run evidence', 506, 153, 402, 16, TEAL, 25, True)
        d.text('Elapsed ≥8h + adequate schedule coverage; ' + str(failures) + ' failed checks/samples retained.',
               506, 181, 402, 9, AMBER if failures else MUTED, 25)
        for i, (name, track) in enumerate(summary['tracks'].items()):
            coverage, identity = track['coverage'], track['source_identity']
            verification = identity['verification']
            start = stamp(track['started_at']).astimezone(timezone.utc).isoformat(timespec='seconds')
            end = stamp(track['finished_at']).astimezone(timezone.utc).isoformat(timespec='seconds')
            text = (f"{name.replace('_', ' ').upper()} / {len(track['observed_commits'])} observed deployment(s)\n"
                    f"Start {start}   End {end}\n"
                    f"{track['elapsed_seconds'] / 3600:.3f} h elapsed · {track['cycles']} cycles/samples · {track['failures']} failures\n"
                    f"Cadence {coverage['configured_interval_seconds']:g} s; uncovered {coverage['unobserved_seconds']:.3f} s / max {coverage['max_unobserved_seconds']:.3f} s\n"
                    f"Cycle/sample windows {coverage['functional_observation_window_seconds'] / 3600:.3f} h; recorded pauses {track['pause_seconds']:.3f} s\n"
                    f"Health-only windows {coverage['health_only_pause_seconds']:.3f} s; identities verified/unverified/unknown: "
                    f"{verification['verified_count']}/{verification['unverified_count']}/{verification['unknown_count']}\n"
                    f"Last observed source {identity['commit'][:7]}; full gaps and transitions in manifest")
            d.text(text, 506, 213 + i * 99, 402, 9, MUTED, 96)
        d.text('Schedule windows + fixed 2 s allowance are not continuous uptime. Pauses are health-only; GPU request duration is unknown.',
               506, 416, 402, 9, AMBER, 29)
    d.text(s['boundary'], 36, 474, 888, 12, AMBER, 35)
    d.footer([('Run status / scope', 'docs/experiments/2026-10-19-run-status.md'), ('Integration roadmap', 'docs/research/action-integrations.md'), ('Editable deck + final-run schema', 'docs/deck-source/fox-review.md')])
    d.c.save()

    document = fitz.open(output)
    if len(document) != 5:
        raise ValueError('Review deck must contain five pages')
    validation = {'pages': len(document), 'text_bounds_valid': True, 'text_spans': 0, 'selectable_text': True, 'links': 0, 'mode': 'interim' if summary is None else 'reconciled_sampled_tracks'}
    for number, page in enumerate(document, 1):
        if not page.get_text().strip():
            raise ValueError('Page lacks selectable text')
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    x0, y0, x1, y1 = span['bbox']
                    if not (0 <= x0 <= x1 <= W and 0 <= y0 <= y1 <= H):
                        raise ValueError(f'Page{number} text outside page: {span["text"]}')
                    validation['text_spans'] += 1
        validation['links'] += len(page.get_links())
        page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(output.with_name(f'{output.stem}-page-{number}.png'))
    document.close()
    validation['paragraph_bounds'] = d.boxes
    output.with_suffix('.validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    manifest = {'schema_version': 'aster.review-deck.v1', 'source_revision': revision, 'mode': validation['mode'],
                'pdf_sha256': sha(output), 'run_summary': summary,
                'inputs': {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): sha(path) for path in inputs},
                'fonts': {str(FONT_ROOT / name): sha(FONT_ROOT / name) for name in ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf')},
                'incident_application_identity': incident['health']['source_identity'],
                'native_capture_identities': {k: v['identity'] for k, v in native_reports.items()},
                'reproducibility': 'Invariant PDF metadata; identical input bytes, source revision and options produce identical PDF bytes'}
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'pdf': str(output), 'pages': 5, 'mode': validation['mode'], 'sha256': manifest['pdf_sha256'], 'validated_spans': validation['text_spans'], 'links': validation['links']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/fox-cycle-20261019/review-deck/fox-review-interim.pdf')
    parser.add_argument('--source-revision')
    parser.add_argument('--run-summary', type=Path)
    build(parser.parse_args())
