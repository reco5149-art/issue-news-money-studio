"""Bounded, public YouTube frame extraction. No browser cookies or login bypass."""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def youtube_url(url):
    p=urlparse(url)
    if p.scheme not in ('https','http') or p.username or p.password or p.port not in (None,80,443):
        raise ValueError('공개 유튜브 영상 주소를 입력하세요.')
    if p.hostname=='youtu.be': vid=p.path.strip('/')
    elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
        vid=p.path.split('/')[-1] if p.path.startswith('/shorts/') else parse_qs(p.query).get('v',[''])[0]
    else: raise ValueError('유튜브 링크만 지원합니다. 다른 영상은 파일을 선택하세요.')
    if not re.fullmatch(r'[\w-]{11}',vid):raise ValueError('유튜브 영상 주소를 확인하세요.')
    return 'https://www.youtube.com/watch?v='+vid


def capture_times(duration,count):
    if not math.isfinite(duration) or duration<=0 or duration>1200:
        raise ValueError('20분 이하의 일반 영상만 자동 캡처할 수 있습니다.')
    return [duration*(i+.5)/count for i in range(count)]


def youtube_frames(url,count,data_dir):
    url=youtube_url(url)
    ffmpeg=shutil.which('ffmpeg');probe=shutil.which('ffprobe')
    if not ffmpeg or not probe:raise ValueError('FFmpeg 설치 후 서버를 다시 실행하거나 영상 파일을 선택하세요.')
    with tempfile.TemporaryDirectory(prefix='video-',dir=data_dir) as temp:
        root=Path(temp)
        cmd=[sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-progress',
             '--socket-timeout','15','--retries','0','--max-filesize','150M',
             '--match-filters','duration <= 1200 & !is_live',
             '-f','bestvideo[height<=720][ext=mp4]/best[height<=720][ext=mp4]',
             '-o',str(root/'source.%(ext)s'),url]
        try:
            r=subprocess.run(cmd,capture_output=True,timeout=180)
            file=root/'source.mp4'
            if r.returncode or not file.is_file():raise ValueError('영상에 접근할 수 없습니다. 로그인·접근 제한을 우회하지 않습니다. 사용 가능한 영상 파일을 선택하세요.')
            if file.stat().st_size>150_000_000:raise ValueError('영상은 150MB 이하만 지원합니다.')
            info=subprocess.run([probe,'-v','error','-show_entries','format=duration','-of','json',str(file)],capture_output=True,timeout=20,check=True)
            duration=float(json.loads(info.stdout)['format']['duration'])
            frames=[]
            for i,at in enumerate(capture_times(duration,count)):
                dest=root/f'{i}.jpg'
                subprocess.run([ffmpeg,'-v','error','-nostdin','-ss',str(at),'-i',str(file),'-frames:v','1','-vf','scale=1280:-2','-y',str(dest)],capture_output=True,timeout=20,check=True)
                frames.append((at,dest.read_bytes()))
            return frames
        except (subprocess.SubprocessError,KeyError,json.JSONDecodeError,OSError) as e:
            raise ValueError('영상 캡처가 지연되거나 실패했습니다. 영상 파일을 선택해 다시 시도하세요.') from e
