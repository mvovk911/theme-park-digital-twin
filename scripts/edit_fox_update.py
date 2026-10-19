"""Validate and caption a successful capture_fox_update.py recording.

Preserves normal-speed 1920x960 application footage, trims only the recorded setup
and post-content tail, and adds a 120-pixel caption band below it. No GPU/network
access. Requires Pillow, imageio-ffmpeg and system DejaVu Sans fonts.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

BG = '#142a30'
WHITE = '#f5f7f2'
ACCENT = '#d5e89b'
MUTED = '#b8cbc5'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def sha256_file(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite numeric time')
    return float(value)


def identity(service, expected, label):
    value = service.get('source_identity', {})
    if (value.get('verified') is not True or value.get('disposition') != 'verified_manifest'
            or value.get('commit') != expected):
        raise ValueError(f'{label} is not the same verified expected release')
    if not re.fullmatch('[a-f0-9]{64}', value.get('scene_sha256', '')):
        raise ValueError(f'{label} has no valid scene hash')
    return value


def validate_capture(doc):
    """Pure metadata gates; container duration and raw SHA are checked separately."""
    if doc.get('schema_version') != 'aster.fox-feature-update.v1' or doc.get('status') != 'captured' or doc.get('error'):
        raise ValueError('A successful FOX feature-update capture is required')
    for field in ('page_errors', 'finalization_errors', 'observation_errors'):
        if field not in doc or doc[field] != []:
            raise ValueError(f'Capture {field} must be present and empty')
    if not re.fullmatch('[a-f0-9]{64}', doc.get('recorder_script_sha256', '')):
        raise ValueError('Recorder source hash is required')
    if any(not isinstance(row.get('status'), int) or not 200 <= row['status'] < 300 for row in doc.get('responses', [])):
        raise ValueError('A recorded POST response was not successful')
    if doc.get('resolution') != {'width': 1920, 'height': 960}:
        raise ValueError('The capture must declare a 1920x960 application viewport')
    expected = doc.get('expected_commit', '')
    if not re.fullmatch('[a-f0-9]{40}', expected):
        raise ValueError('An exact full expected commit is required')
    initial = doc.get('preflight', {})
    services = [('initial gateway', initial.get('health', {})),
                ('initial renderer', initial.get('renderer', {})),
                ('final gateway', doc.get('final_health', {})),
                ('final renderer', doc.get('final_renderer', {}))]
    scene = None
    for label, service in services:
        verified = identity(service, expected, label)
        if scene is not None and verified['scene_sha256'] != scene:
            raise ValueError('Scene identity changed between gateway/renderer or capture boundaries')
        scene = verified['scene_sha256']
        if 'renderer' in label:
            if service.get('ready') is not True or 'NVIDIA OVRTX' not in service.get('engine', ''):
                raise ValueError(f'{label} was not an actual ready OVRTX renderer')
            if service.get('scene_revision') != scene:
                raise ValueError(f'{label} scene revision differs from its release identity')
        elif service.get('status') != 'ok' or service.get('synthetic') is not True:
            raise ValueError(f'{label} was not a healthy synthetic gateway')
    cleanup = doc.get('cleanup')
    if not isinstance(cleanup, list) or not cleanup or any(row.get('ok') is not True for row in cleanup):
        raise ValueError('All attempted cleanup operations must have succeeded')
    paths = [row.get('path') for row in cleanup]
    if '/api/view' not in paths or '/api/actions' not in paths or paths.count('/render/control') < 2:
        raise ValueError('Required live/reset/home/layer cleanup attempts are missing')
    if doc.get('cleanup_scenario') != 'normal' or doc.get('cleanup_view', {}).get('mode') != 'live':
        raise ValueError('Cleanup readback must confirm live/normal')
    if not re.fullmatch('[a-f0-9]{64}', doc.get('video_sha256', '')):
        raise ValueError('Capture raw-video SHA256 is missing')
    start = finite(doc.get('presentation_start_seconds'), 'presentation_start_seconds')
    end = finite(doc.get('recording_content_end_seconds'), 'recording_content_end_seconds')
    close = finite(doc.get('browser_close_requested_seconds'), 'browser_close_requested_seconds')
    if start < 0 or not 75 <= end - start <= 100 or close < end:
        raise ValueError('Content must be 75–100 seconds and end before browser finalization')
    ignored_aborts = []
    for failure in doc.get('request_failures', []):
        at = finite(failure.get('at_seconds'), 'request failure timestamp')
        text = str(failure.get('failure', ''))
        if failure.get('path') == '/render/frame.jpg' and at >= close - .25 and 'ERR_ABORTED' in text:
            ignored_aborts.append(failure)
        else:
            raise ValueError(f'Non-shutdown request failure occurred: {failure.get("path")} at {at}s')
    chapters = doc.get('chapters')
    if not isinstance(chapters, list) or not chapters:
        raise ValueError('Chapter evidence is required')
    previous = -1.0
    editorial = []
    for index, chapter in enumerate(chapters):
        raw_start = finite(chapter.get('start_seconds'), 'chapter start')
        raw_end = finite(chapter.get('end_seconds'), 'chapter end')
        if raw_start <= previous or raw_end <= raw_start or raw_start < start or raw_end > end + .1:
            raise ValueError('Chapter intervals are unordered or outside the recorded content')
        if not all(isinstance(chapter.get(field), str) and 0 < len(chapter[field]) <= 500 for field in ('title', 'caption')):
            raise ValueError('Chapter title/caption must be nonempty bounded text')
        next_start = finite(chapters[index+1]['start_seconds'], 'next chapter start') if index+1 < len(chapters) else end
        if abs(raw_end - next_start) > .1:
            raise ValueError('Chapter boundaries have an unexplained gap or overlap')
        if index == 0 and abs(raw_start - start) > .5:
            raise ValueError('First chapter does not begin with the ready content')
        edited_start = 0.0 if index == 0 else raw_start - start
        edited_end = min(end, next_start) - start
        editorial.append({**chapter, 'raw_start_seconds':raw_start, 'raw_end_seconds':raw_end,
                          'edited_start_seconds':edited_start, 'edited_end_seconds':edited_end})
        previous = raw_start
    return {'trim_start_seconds':start, 'trim_end_seconds':end, 'content_seconds':end-start,
            'scene_sha256':scene, 'commit':expected, 'chapters':editorial,
            'ignored_shutdown_frame_aborts':ignored_aborts}



def bounded_tail(validated, measured_duration, allow_clip=False):
    """Keep strict default; an explicit opt-in may trim <=0.5s unencoded tail.

    This does not estimate or correct the browser's first-encoded-frame offset.
    Raw chapter timestamps remain historical capture evidence, never rewritten.
    """
    measured_duration = finite(measured_duration, 'measured raw duration')
    result = copy.deepcopy(validated)
    requested_end = validated['trim_end_seconds']
    overflow = max(0.0, requested_end - measured_duration)
    if overflow and not allow_clip:
        raise ValueError('Captured content end extends beyond measured raw duration; explicit --clip-unencoded-tail is required for a bounded clip')
    if overflow > .5 + 1e-9:
        raise ValueError('Unencoded tail exceeds the maximum permitted 0.5 seconds')
    effective_end = min(requested_end, measured_duration)
    last = result['chapters'][-1]
    if effective_end <= last['raw_start_seconds'] or any(chapter['raw_end_seconds'] > effective_end for chapter in result['chapters'][:-1]):
        raise ValueError('Tail clipping would remove or alter an earlier chapter')
    result['requested_trim_end_seconds'] = requested_end
    result['requested_content_seconds'] = validated['content_seconds']
    result['trim_end_seconds'] = effective_end
    result['content_seconds'] = effective_end - result['trim_start_seconds']
    result['unencoded_tail'] = {
        'explicitly_allowed': bool(allow_clip), 'maximum_seconds': .5,
        'clipped_seconds': overflow, 'measured_raw_duration_seconds': measured_duration,
        'policy': 'Clip only the unavailable tail to the measured container bound; no tail padding, freeze frame, speed change or first-frame offset inference.',
        'first_encoded_frame_alignment': 'approximate; no offset correction has been inferred',
    }
    # Only this final edited boundary changes. All raw_start/raw_end values and
    # the original capture manifest retain the recorder's monotonic evidence.
    last['requested_edited_end_seconds'] = last['edited_end_seconds']
    last['edited_end_seconds'] = result['content_seconds']
    return result


def measure(path):
    import imageio_ffmpeg
    reader = imageio_ffmpeg.read_frames(str(path))
    try:
        metadata = next(reader)
    finally:
        reader.close()
    duration = finite(metadata.get('duration'), 'measured container duration')
    if duration <= 0:
        raise ValueError('The video has no measurable positive duration')
    return {**metadata, 'duration':duration}


def run(ffmpeg, arguments, log, timeout=1200):
    with log.open('wb') as stream:
        result = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-y', *arguments],
                                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f'FFmpeg failed; inspect {log}')


def wrap(draw, text, font, width):
    lines, line = [], ''
    for word in text.split():
        candidate = f'{line} {word}'.strip()
        if draw.textlength(candidate, font=font) > width:
            if not line:
                raise ValueError('Caption contains a word wider than the available band')
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def caption_band(path, chapter, number, total):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1920, 120), BG)
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(BOLD, 25)
    caption_font = ImageFont.truetype(FONT, 22)
    number_font = ImageFont.truetype(BOLD, 20)
    if draw.textlength(chapter['title'], font=title_font) > 1710:
        raise ValueError('Chapter title does not fit the lower caption band')
    lines = wrap(draw, chapter['caption'], caption_font, 1710)
    if len(lines) > 2:
        raise ValueError('Chapter caption exceeds two lines; edit its wording explicitly')
    draw.rectangle((0,0,1920,3),fill=ACCENT)
    draw.text((32,20),f'{number:02d} / {total:02d}',font=number_font,fill=ACCENT)
    draw.text((165,11),chapter['title'],font=title_font,fill=WHITE)
    for index,line in enumerate(lines):
        draw.text((165,47+29*index),line,font=caption_font,fill=MUTED)
    image.save(path)
    return lines


def timecode(value):
    milliseconds = round(value * 1000)
    return f'{milliseconds//3600000:02d}:{milliseconds//60000%60:02d}:{milliseconds//1000%60:02d},{milliseconds%1000:03d}'


def edit(args):
    import imageio_ffmpeg
    manifest_path = args.manifest.resolve(strict=True)
    manifest_bytes = manifest_path.read_bytes()
    capture = json.loads(manifest_bytes)
    validated = validate_capture(capture)
    raw = Path(capture['video'])
    if not raw.is_absolute():
        raw = manifest_path.parent / raw
    raw = raw.resolve(strict=True)
    raw_hash = sha256_file(raw)
    if raw_hash != capture['video_sha256']:
        raise ValueError('Actual raw video bytes differ from the capture manifest SHA256')
    raw_metadata = measure(raw)
    if tuple(raw_metadata.get('size', ())) != (1920,960):
        raise ValueError('Raw container dimensions differ from the declared unscaled application viewport')
    validated = bounded_tail(validated,raw_metadata['duration'],args.clip_unencoded_tail)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    assets = output / 'edit-assets'
    assets.mkdir()
    report = {
        'schema_version':'aster.fox-feature-edit.v1','status':'encoding',
        'started_at':datetime.now(timezone.utc).isoformat(),
        'source_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
        'raw_video_sha256':raw_hash,'raw_video_bytes':raw.stat().st_size,
        'editor_script_sha256':sha256_file(Path(__file__)),
        'recorder_script_sha256':capture.get('recorder_script_sha256'),
        'capture':capture,'edit':validated,'raw_container_metadata':raw_metadata,
        'dimensions':[1920,1080],'encoded_fps':30,'audio':'none',
        'footage_policy':'Normal-speed original 1920x960 browser footage, no resize or in-viewport overlays; 120px editorial band below UI; no intro/outro.',
        'timing_basis':'Trim uses capture monotonic timestamps relative to page creation; first encoded-frame alignment remains approximate. Container durations are measured independently by FFmpeg.',
        'caption_boundary_policy':'First caption covers the ready-content start (within0.5s of its logged start); later captions use logged boundaries relative to trim. No chapter footage is individually cut or repeated.',
    }
    report_path = output / 'edit-manifest.json'
    verification = {'status':'pending'}
    try:
        bands, subtitles = [], []
        chapters = validated['chapters']
        for number,chapter in enumerate(chapters,1):
            png = assets / f'caption-{number:02d}.png'
            lines = caption_band(png,chapter,number,len(chapters))
            bands.append((png,chapter['edited_end_seconds']-chapter['edited_start_seconds']))
            chapter['rendered_caption_lines'] = lines
            chapter['caption_png_sha256'] = sha256_file(png)
            subtitles.append(f'{number}\n{timecode(chapter["edited_start_seconds"])} --> {timecode(chapter["edited_end_seconds"])}\n{chapter["title"]}\n'+ '\n'.join(lines)+'\n')
        listing = assets / 'caption-bands.ffconcat'
        def quoted(path):
            return "'" + str(path.resolve()).replace("'", "'\\''") + "'"
        # A final repeated image gives the concat demuxer a terminal timestamp.
        listing.write_text('ffconcat version 1.0\n' + ''.join(f'file {quoted(path)}\nduration {duration:.6f}\n' for path,duration in bands) + f'file {quoted(bands[-1][0])}\n')
        srt = output / 'aster-park-fox-update.srt'
        srt.write_text('\n'.join(subtitles),encoding='utf-8')
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        report['ffmpeg_version'] = subprocess.run([ffmpeg,'-version'],capture_output=True,text=True,check=True,timeout=20).stdout.splitlines()[0]
        report['ffmpeg_executable_sha256'] = sha256_file(ffmpeg)
        video = output / 'aster-park-fox-update.mp4'
        graph = '[0:v]setpts=PTS-STARTPTS,pad=1920:1080:0:0:color=0x142a30[screen];[1:v]fps=30,setpts=PTS-STARTPTS[band];[screen][band]overlay=0:960:shortest=1:format=auto[out]'
        encode = ['-ss',str(validated['trim_start_seconds']),'-i',str(raw),'-f','concat','-safe','0','-i',str(listing),
                  '-filter_complex_threads','1','-filter_complex',graph,'-map','[out]',
                  '-t',str(validated['content_seconds']),'-an','-c:v','libx264','-preset','fast','-crf','21',
                  '-pix_fmt','yuv420p','-r','30','-threads','4','-movflags','+faststart',str(video)]
        report['encode_arguments'] = encode
        run(ffmpeg,encode,assets/'encode.log')
        metadata = measure(video)
        if tuple(metadata.get('size',())) != (1920,1080) or abs(metadata['duration']-validated['content_seconds']) > .15:
            raise RuntimeError('Encoded video dimensions or measured duration differ from the continuous trimmed content')
        decode_log = assets / 'full-decode.log'
        run(ffmpeg,['-v','error','-xerror','-err_detect','explode','-i',str(video),'-map','0:v:0','-an',
                    '-progress','pipe:1','-nostats','-f','null','-'],decode_log,600)
        text = decode_log.read_text()
        counts = re.findall(r'^frame=(\d+)\s*$',text,re.MULTILINE)
        if not counts or int(counts[-1]) <= 0 or 'progress=end' not in text:
            raise RuntimeError('Full decode did not report a completed nonempty video stream')
        verification = {'status':'passed','method':'FFmpeg full-stream decode with -xerror -err_detect explode',
                        'decoded_frames':int(counts[-1]),'measured_output_duration_seconds':metadata['duration'],
                        'measured_raw_duration_seconds':raw_metadata['duration'],'output_metadata':metadata,
                        'decode_log_sha256':sha256_file(decode_log),'decode_log':'edit-assets/full-decode.log',
                        'visual_inspection':'required separately; automated decode does not establish visual quality'}
        poster = output / 'poster.png'
        run(ffmpeg,['-ss','3','-i',str(video),'-frames:v','1',str(poster)],assets/'poster.log',60)
        report.update(status='encoded_and_decode_verified',video=video.name,video_sha256=sha256_file(video),
                      video_bytes=video.stat().st_size,measured_output_duration_seconds=metadata['duration'],
                      subtitles=srt.name,subtitles_sha256=sha256_file(srt),poster=poster.name,poster_sha256=sha256_file(poster),
                      verification_report='verification.json')
        print(json.dumps({'status':report['status'],'video':str(video),'duration_seconds':metadata['duration'],
                          'decoded_frames':verification['decoded_frames'],'visual_inspection':'still required'},indent=2),flush=True)
    except Exception as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
        report_path.write_text(json.dumps(report,indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path,help='Successful capture_fox_update.py capture-manifest.json')
    parser.add_argument('--output',type=Path,required=True,help='New exclusive editing output directory')
    parser.add_argument('--clip-unencoded-tail',action='store_true',help='Explicitly permit clipping at most0.5s of unavailable final content to measured raw duration; never pad or speed up')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('--output must name a new directory; existing edits are never overwritten')
    try:
        edit(args)
    except (ValueError,KeyError,TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
