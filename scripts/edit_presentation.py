"""Edit a real browser recording into a captioned 1080p presentation.

Requires Pillow and imageio-ffmpeg. Captions are editorial; footage stays intact.
Input: a successful record_presentation.py capture manifest, with optional edited chapters.
Relative video paths resolve against the manifest. No application data is altered.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

BG = '#142a30'
WHITE = '#f5f7f2'
ACCENT = '#d5e89b'
MUTED = '#b8cbc5'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def draw_lines(draw, value, pos, size, width, color, bold=False):
    f = font(size, bold)
    lines = []
    line = ''
    for word in value.split():
        candidate = f'{line} {word}'.strip()
        if line and draw.textlength(candidate, font=f) > width:
            lines.append(line); line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    for i, line in enumerate(lines):
        draw.text((pos[0], pos[1] + i * (size + 10)), line, font=f, fill=color)
    return len(lines)


def title_card(path, closing=False):
    im = Image.new('RGB', (1920, 1080), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((100, 150, 112, 880), fill=ACCENT)
    d.text((160, 160), 'ASTER PARK  /  OPERATIONS TWIN', font=font(28, True), fill=ACCENT)
    heading = 'From observation\nto operational context.' if closing else 'One park.\nA connected operating view.'
    d.multiline_text((155, 270), heading, font=font(78, True), fill=WHITE, spacing=24)
    text = ('Inspect assets. Explore incidents. Trace decisions.\nReturn to the evidence whenever you need it.' if closing else 'A live application walkthrough\nOpenUSD + OVStage + NVIDIA OVRTX')
    d.multiline_text((160, 530), text, font=font(36), fill=MUTED, spacing=20)
    d.text((160, 790), 'Synthetic operations  ·  Actual GPU-rendered application', font=font(28), fill=ACCENT)
    if closing:
        d.text((160, 860), 'github.com/mvovk911/theme-park-digital-twin', font=font(27), fill=WHITE)
    else:
        d.text((160, 860), 'Navigation  /  Incidents  /  Utilities  /  Source health  /  Replay', font=font(27), fill=WHITE)
    im.save(path)


def footer(path, chapter, index, count):
    im = Image.new('RGB', (1920, 120), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1920, 3), fill=ACCENT)
    d.text((36, 23), f'{index:02d} / {count:02d}', font=font(22, True), fill=ACCENT)
    d.text((180, 14), chapter['title'], font=font(30, True), fill=WHITE)
    lines = draw_lines(d, chapter['caption'], (180, 58), 24, 1690, MUTED)
    if lines > 1:
        raise ValueError('Chapter caption must fit one line; shorten it')
    im.save(path)


def run(ffmpeg, args, log):
    with log.open('wb') as output:
        result = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-y', *args], stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Video encoding failed; inspect {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('--output must be a new directory')
    doc = json.loads(args.manifest.read_text())
    identity = doc.get('preflight', {}).get('renderer', {}).get('source_identity', {})
    final_identity = doc.get('final_renderer', {}).get('source_identity', {})
    if (doc.get('status') != 'captured' or doc.get('error')
            or doc.get('evidence_kind') != 'actual_browser_and_gpu_application'
            or identity.get('verified') is not True or not identity.get('commit')
            or final_identity.get('commit') != identity['commit']):
        parser.error('A successful capture of the same verified GPU release is required')
    raw = Path(doc['video'])
    if not raw.is_absolute(): raw = args.manifest.parent / raw
    raw = raw.resolve(strict=True)
    chapters = doc['chapters']
    duration = float(doc['duration_seconds'])
    starts = [float(c['start_seconds']) for c in chapters]
    if (not chapters or not all(math.isfinite(n) for n in [duration, *starts])
            or starts != sorted(set(starts)) or starts[0] < 0 or starts[-1] >= duration):
        parser.error('Invalid chapter timing')
    probe = imageio_ffmpeg.read_frames(str(raw))
    try:
        metadata = next(probe)
    finally:
        probe.close()
    if duration > metadata['duration']:
        parser.error('Requested content extends beyond the measured raw video duration')
    args.output.mkdir(parents=True)
    assets = args.output / 'edit-assets'; assets.mkdir()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    segments = []
    common = ['-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-pix_fmt', 'yuv420p', '-r', '30']
    for label, closing, seconds in [('intro', False, 7), ('outro', True, 7)]:
        png = assets / f'{label}.png'; title_card(png, closing)
        clip = assets / f'{label}.mp4'
        run(ffmpeg, ['-loop', '1', '-i', str(png), '-t', str(seconds), *common, str(clip)], assets / f'{label}.log')
    segments.append(assets / 'intro.mp4')
    editorial = []
    running = 7.0
    for i, chapter in enumerate(chapters):
        start = starts[i]; end = starts[i+1] if i+1 < len(starts) else duration
        length = end - start
        png = assets / f'caption-{i:02d}.png'; footer(png, chapter, i+1, len(chapters))
        clip = assets / f'chapter-{i:02d}.mp4'
        graph = '[0:v]fps=30,scale=1920:960:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:0:color=0x142a30[screen];[screen][1:v]overlay=0:960:shortest=1[v]'
        run(ffmpeg, ['-ss', str(start), '-i', str(raw), '-loop', '1', '-i', str(png), '-filter_complex', graph, '-map', '[v]', '-t', str(length), *common, str(clip)], assets / f'chapter-{i:02d}.log')
        segments.append(clip)
        editorial.append({**chapter, 'presentation_start_seconds': running, 'duration_seconds': length})
        running += length
        print(f'Encoded chapter {i+1}/{len(chapters)}: {chapter["title"]}', flush=True)
    segments.append(assets / 'outro.mp4')
    listing = assets / 'concat.txt'
    listing.write_text(''.join("file '" + str(p.resolve()).replace("'", "'\\''") + "'\n" for p in segments))
    final = args.output / 'aster-park-functionality-demo.mp4'
    run(ffmpeg, ['-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', '-movflags', '+faststart', str(final)], assets / 'concat.log')
    def timecode(value):
        millis = round(value * 1000)
        return f'{millis//3600000:02}:{millis//60000%60:02}:{millis//1000%60:02},{millis%1000:03}'
    subtitles = []
    for i, chapter in enumerate(editorial, 1):
        start = chapter['presentation_start_seconds']
        subtitles.append(f'{i}\n{timecode(start)} --> {timecode(start + chapter["duration_seconds"])}\n{chapter["title"]}\n{chapter["caption"]}\n')
    (args.output / 'aster-park-functionality-demo.srt').write_text('\n'.join(subtitles))
    run(ffmpeg, ['-ss', '12', '-i', str(final), '-frames:v', '1', str(args.output / 'poster.png')], assets / 'poster.log')
    report = {'video': final.name, 'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
              'bytes': final.stat().st_size, 'planned_duration_seconds': running+7,
              'dimensions': [1920,1080], 'fps': 30, 'audio': 'none',
              'footage': 'Actual application browser recording; editorial title cards and captions added',
              'raw_video_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
              'source_manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              'capture': doc, 'chapters': editorial}
    (args.output / 'presentation-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(final, flush=True)


if __name__ == '__main__':
    main()
