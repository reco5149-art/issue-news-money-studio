"""Public video transcripts. No cookies, credential collection or login bypass."""
import asyncio
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from . import providers as p

HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be',
         'instagram.com', 'www.instagram.com', 'tiktok.com', 'www.tiktok.com',
         'm.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com'}


def is_video_url(url):
    return (urlparse(url).hostname or '').lower() in HOSTS


def normalize_url(url):
    u = urlparse(url.strip())
    if u.scheme not in ('http', 'https') or u.username or u.password or u.port not in (None, 80, 443):
        raise p.ProviderError('공개 영상 링크를 입력하세요.')
    host = (u.hostname or '').lower()
    if host not in HOSTS:
        raise p.ProviderError('유튜브·인스타그램·틱톡의 공개 영상 링크를 입력하세요.')
    if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        vid = (u.path.strip('/') if host == 'youtu.be' else
               u.path.rstrip('/').split('/')[-1] if u.path.startswith(('/shorts/', '/live/', '/embed/')) else
               parse_qs(u.query).get('v', [''])[0])
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise p.ProviderError('유튜브 영상 주소를 확인하세요.')
        return 'https://www.youtube.com/watch?v=' + vid
    if 'instagram' in host:
        if not re.fullmatch(r'/(?:reel|reels|p|tv)/[A-Za-z0-9_-]+/?', u.path):
            raise p.ProviderError('인스타그램 게시물 또는 릴스 링크를 입력하세요.')
        return 'https://www.instagram.com' + u.path
    if not (re.fullmatch(r'/@[\w.-]+/video/\d+/?', u.path) or
            host in ('vm.tiktok.com', 'vt.tiktok.com') and re.fullmatch(r'/[A-Za-z0-9]+/?', u.path) or
            host == 'www.tiktok.com' and re.fullmatch(r'/t/[A-Za-z0-9]+/?', u.path)):
        raise p.ProviderError('틱톡 영상 공유 링크를 입력하세요.')
    return 'https://' + host + u.path


def run(args, timeout=90):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise p.ProviderError('영상을 가져올 수 없습니다. 비공개·로그인 요구·플랫폼 접근 제한일 수 있습니다. 다른 공개 링크나 직접 확인한 자막을 사용하세요.')
    except (OSError, subprocess.SubprocessError) as exc:
        raise p.ProviderError('영상 분석이 지연되거나 실행 도구가 없습니다. 잠시 후 다시 시도하세요.') from exc


def command():
    return [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
            '--no-progress', '--socket-timeout', '15', '--retries', '0',
            '--extractor-retries', '0', '--match-filters', 'duration <= 1200 & !is_live']


def metadata(url, root):
    run(command() + ['--skip-download', '--write-info-json', '-o', str(root / 'source.%(ext)s'), url])
    file = root / 'source.info.json'
    if not file.exists() or file.stat().st_size > 8_000_000:
        raise p.ProviderError('단일 영상 정보를 확보하지 못했습니다.')
    try:
        info = json.loads(file.read_text(encoding='utf-8'))
        duration = float(info.get('duration') or 0)
    except (ValueError, TypeError) as exc:
        raise p.ProviderError('영상 길이를 확인하지 못했습니다.') from exc
    if info.get('_type') in ('playlist', 'multi_video') or info.get('is_live') or not math.isfinite(duration) or not 0 < duration <= 1200:
        raise p.ProviderError('길이를 확인할 수 있는 20분 이하의 단일 일반 영상만 지원합니다.')
    return info


def subtitle_text(raw, ext):
    if ext == 'json3':
        lines = [''.join(s.get('utf8', '') for s in event.get('segs', []))
                 for event in json.loads(raw).get('events', [])]
    else:
        lines = []
        for block in re.split(r'\n\s*\n', raw.replace('\r', '')):
            parts = block.splitlines()
            timing = next((i for i, line in enumerate(parts) if '-->' in line), None)
            if timing is not None:
                lines.append(' '.join(parts[timing + 1:]))
    output = []
    for line in lines:
        line = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', line))).strip()
        if not line:
            continue
        # Rolling captions repeat their preceding cue. Preserve other repetitions.
        if output and line == output[-1]:
            continue
        if output and line.startswith(output[-1]):
            output[-1] = line
        else:
            output.append(line)
    return '\n'.join(output)


async def subtitles(info):
    for field in ('subtitles', 'automatic_captions'):
        tracks = info.get(field) or {}
        languages = sorted(tracks, key=lambda lang: (not lang.startswith('ko'), not lang.startswith('en'), lang))
        # Avoid downloading dozens of auto-translated tracks on failure.
        for lang in languages[:3]:
            candidates = [x for x in tracks[lang] if x.get('ext') in ('json3', 'vtt') and x.get('url')]
            candidates.sort(key=lambda x: x['ext'] != 'json3')
            for track in candidates[:1]:
                try:
                    raw, _, _ = await p.fetch_public(track['url'], limit=3_000_000)
                    text = subtitle_text(raw.decode('utf-8-sig'), track['ext'])
                    if len(text.strip()) >= 20:
                        return text, '자동 자막' if field == 'automatic_captions' else '제공 자막'
                except (p.ProviderError, ValueError, UnicodeError, TypeError):
                    continue
    return '', ''


def audio_file(url, root):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise p.ProviderError('자막이 없는 영상의 음성 분석에는 FFmpeg 설치가 필요합니다.')
    run(command() + ['--max-filesize', '150M', '-f', 'bestaudio/best',
                     '-o', str(root / 'audio.%(ext)s'), url], 180)
    files = [x for x in root.glob('audio.*') if x.suffix not in ('.part', '.ytdl')]
    if len(files) != 1 or not 0 < files[0].stat().st_size <= 150_000_000:
        raise p.ProviderError('분석 가능한 음성을 확보하지 못했습니다. 영상은 150MB 이하만 지원합니다.')
    out = root / 'speech.mp3'
    run([ffmpeg, '-v', 'error', '-nostdin', '-i', str(files[0]), '-t', '1200',
         '-vn', '-ac', '1', '-ar', '16000', '-b:a', '48k', '-y', str(out)], 90)
    if not out.exists() or not 0 < out.stat().st_size < 25_000_000:
        raise p.ProviderError('음성 파일을 분석 가능한 크기로 변환하지 못했습니다.')
    return out


async def extract_video(url, data_dir):
    canonical = normalize_url(url)
    with tempfile.TemporaryDirectory(prefix='transcript-', dir=data_dir) as folder:
        root = Path(folder)
        info = await asyncio.to_thread(metadata, canonical, root)
        transcript, method = await subtitles(info)
        if not transcript:
            p.require('OPENAI_API_KEY')
            file = await asyncio.to_thread(audio_file, canonical, root)
            with file.open('rb') as audio:
                result = await p.api('POST', 'https://api.openai.com/v1/audio/transcriptions',
                    headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']},
                    data={'model': os.getenv('OPENAI_TRANSCRIPTION_MODEL', 'gpt-transcribe')},
                    files={'file': ('speech.mp3', audio, 'audio/mpeg')})
            transcript = str(result.get('text') or '').strip()
            method = 'AI 음성 전사'
        if len(transcript.strip()) < 20:
            raise p.ProviderError('분석 가능한 발언을 확보하지 못했습니다. 제목·설명만으로 생성하지 않습니다. 확인한 자막을 직접 입력하세요.')
        title = str(info.get('title') or '영상')[:300]
        text = title + '\n\n[영상 발언 — ' + method + ']\n' + transcript
        if len(text) > 30000:
            raise p.ProviderError('영상 발언이 30,000자를 넘습니다. 더 짧은 영상을 사용하세요. 일부만 읽고 전체를 분석했다고 처리하지 않습니다.')
        return {'title': title, 'text': text, 'source_name': str(info.get('uploader') or info.get('channel') or '영상 출처')[:150],
                'source_url': canonical, 'transcript_method': method,
                'warning': method + '를 확보했습니다. 발언의 사실 여부를 검증한 것은 아닙니다. 고유명사·숫자·날짜를 원문과 대조하세요. 화면 속 글자는 분석하지 않습니다.'}
