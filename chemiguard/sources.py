import hashlib
import json
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

import cv2

from .config import ASSETS, DATA, PPE_MEDIA
from .store import store

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}


class Sources:
    def __init__(self):
        self.paths = {}
        self.metadata = {}
        self.playback_lock = threading.Lock()
        self.refresh()

    def refresh(self):
        entries = []
        if ASSETS.exists():
            for path in sorted(ASSETS.rglob('*')):
                relative = str(path.relative_to(ASSETS))
                if path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                if any(word in relative for word in ('탐지결과', '이전모델', '이전편집', 'metadata', '_leak.', '_annotated', '확인사진')):
                    continue
                entries.append((path, path.stem, '사전 준비 · 누출 참고 영상', relative))
        for filename, label in [
            ('V08_donning_76_90s.mp4', '화학보호복 착의 · 부분 착용'),
            ('V08_wide_205_222_5s.mp4', '화학보호복 · 두 사람'),
            ('V12_work_12s.mp4', '보호복 작업 장면'),
            ('V08_p11_donning_doffing.mp4', '화학보호복 착의·탈의 전체'),
            ('V12_mopp_work.mp4', '보호복 현장 작업 전체'),
        ]:
            path = PPE_MEDIA / filename
            if path.exists():
                entries.append((path, label, '사전 준비 · 보호복 교육/작업 영상', filename))
        doffing = PPE_MEDIA.parents[2] / 'research/incomplete_ppe_videos_20261004/previews/V08_doffing_258_282s.mp4'
        if doffing.exists():
            entries.append((doffing, '화학보호복 탈의 · 상태 전환', '사전 준비 · 보호복 교육 영상', doffing.name))
        for row in store.list('source'):
            path = DATA / row['file']
            if path.is_file():
                entries.append((path, row['name'], '본선 등록 영상', row.get('source', '사용자 업로드')))
        for path, label, origin, source in entries:
            source_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
            self.paths[source_id] = path.resolve()
            self.metadata[source_id] = {'id': source_id, 'name': label, 'origin': origin, 'source': source,
                                        'case': '두 사람' if '두 사람' in label else '탈의' if '탈의' in label else '착의' if '착의' in label else '작업' if '보호복' in label else '분출·누출 참고',
                                        'preview_url': f'/api/sources/{source_id}/preview',
                                        'video_url': f'/api/sources/{source_id}/video'}

    def list(self):
        self.refresh()
        return sorted(self.metadata.values(), key=lambda row: (
            0 if row['name'] == '화학보호복 착의 · 부분 착용' else 1 if '보호복' in row['name'] else 2,
            row['name']))

    def path(self, source_id):
        if source_id not in self.paths:
            raise ValueError('등록된 영상을 선택해 주세요.')
        return self.paths[source_id]

    def playback(self, source_id):
        path = self.path(source_id)
        stat = path.stat()
        with self.playback_lock:
            return self._playback(str(path), stat.st_mtime_ns, stat.st_size)

    @lru_cache(maxsize=128)
    def _playback(self, filename, modified, size):
        path = Path(filename)
        try:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                    '-show_entries', 'stream=codec_name,pix_fmt', '-of', 'json', filename],
                                   capture_output=True, text=True, check=True, timeout=15)
            stream = json.loads(probe.stdout)['streams'][0]
            if (path.suffix.lower() == '.mp4' and stream['codec_name'] == 'h264'
                    and stream.get('pix_fmt') == 'yuv420p') or (path.suffix.lower() == '.webm'
                    and stream['codec_name'] in ('vp8', 'vp9')):
                return path
            folder = DATA / 'playback'
            folder.mkdir(exist_ok=True)
            key = hashlib.sha256(f'{filename}:{modified}:{size}'.encode()).hexdigest()[:24]
            output = folder / f'{key}.mp4'
            if not output.exists():
                temporary = folder / f'{key}.partial.mp4'
                try:
                    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', filename,
                                    '-map', '0:v:0', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
                                    '-crf', '20', '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
                                    '-movflags', '+faststart', str(temporary)],
                                   capture_output=True, check=True, timeout=300)
                    temporary.replace(output)
                finally:
                    temporary.unlink(missing_ok=True)
            return output
        except (FileNotFoundError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
            raise ValueError('브라우저용 영상 준비 실패. ffmpeg/ffprobe 설치와 영상 코덱을 확인해 주세요.') from exc

    def preview(self, source_id):
        path = DATA / 'previews' / f'{source_id}.jpg'
        if not path.exists():
            capture = cv2.VideoCapture(str(self.path(source_id)))
            try:
                ok, frame = capture.read()
                if not ok:
                    raise ValueError('영상 미리보기를 읽지 못했습니다.')
                height, width = frame.shape[:2]
                frame = cv2.resize(frame, (min(width, 960), max(1, round(height * min(width, 960) / width))))
                cv2.imwrite(str(path), frame)
            finally:
                capture.release()
        return path


sources = Sources()
