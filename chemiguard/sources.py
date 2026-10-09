import hashlib
import json
import subprocess
import threading
from functools import lru_cache
from fractions import Fraction
from pathlib import Path

import cv2

from .config import ASSETS, DATA, DEMO_MEDIA, PPE_MEDIA
from .store import store

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}
PLAYBACK_VERSION = 'h264-30fps-v2'


def demo_catalog():
    return [
        (PPE_MEDIA / 'V08_wide_205_222_5s.mp4', '화학보호복 · 두 사람', '두 사람'),
        (DEMO_MEDIA / 'Tychem4000S_착용_동작_시연.mp4', 'Tychem 4000 S · 착용 동작', '착용 동작'),
        (ASSETS / '00_최신편집_데모/receiver_valve_centered.mp4', 'receiver_valve_centered', '분출·누출 참고'),
    ]


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
        demonstration = demo_catalog()
        path = DEMO_MEDIA / 'Tychem4000S_착용_동작_시연.mp4'
        label = 'Tychem 4000 S · 착용 동작'
        if path.is_file():
            entries.append((path, label, '제조사 기존 영상 · 본선 발췌',
                            'DuPont Tychem 4000 S | EN · https://www.youtube.com/watch?v=ABFEls_O80Q'))
        selected = {path.resolve(): (order, label, case)
                    for order, (path, label, case) in enumerate(demonstration)}
        for path, label, origin, source in entries:
            source_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
            self.paths[source_id] = path.resolve()
            self.metadata[source_id] = {'id': source_id, 'name': label, 'origin': origin, 'source': source,
                                        'case': '두 사람' if '두 사람' in label else '탈의' if '탈의' in label else '착의' if '착의' in label else '작업' if '보호복' in label else '분출·누출 참고',
                                        'preview_url': f'/api/sources/{source_id}/preview',
                                        'video_url': f'/api/sources/{source_id}/video?v={PLAYBACK_VERSION}'}
            if path.resolve() in selected:
                order, label, case = selected[path.resolve()]
                self.metadata[source_id].update(demo_order=order, name=label, case=case)

    def list(self, include_archive=False):
        self.refresh()
        rows = self.metadata.values()
        if not include_archive:
            rows = [row for row in rows if 'demo_order' in row and self.paths[row['id']].is_file()]
        return sorted(rows, key=lambda row: (row.get('demo_order', 99), row['name']))

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
                                    '-show_entries', 'stream=codec_name,pix_fmt,level,avg_frame_rate,width,height', '-of', 'json', filename],
                                   capture_output=True, text=True, check=True, timeout=15)
            stream = json.loads(probe.stdout)['streams'][0]
            try:
                fps = float(Fraction(stream.get('avg_frame_rate', '0/1')))
            except (ValueError, ZeroDivisionError):
                fps = 0
            if (path.suffix.lower() == '.mp4' and stream['codec_name'] == 'h264'
                    and stream.get('pix_fmt') == 'yuv420p' and 0 < fps <= 30
                    and 0 < stream.get('level', 0) <= 41
                    and stream.get('width', 0) <= 1920 and stream.get('height', 0) <= 1080) or (path.suffix.lower() == '.webm'
                    and stream['codec_name'] in ('vp8', 'vp9')):
                return path
            folder = DATA / 'playback'
            folder.mkdir(exist_ok=True)
            key = hashlib.sha256(f'{PLAYBACK_VERSION}:{filename}:{modified}:{size}'.encode()).hexdigest()[:24]
            output = folder / f'{key}.mp4'
            if not output.exists():
                temporary = folder / f'{key}.partial.mp4'
                try:
                    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', filename,
                                    '-map', '0:v:0', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
                                    '-crf', '20', '-pix_fmt', 'yuv420p', '-profile:v', 'main', '-level:v', '4.1',
                                    '-maxrate', '5M', '-bufsize', '10M',
                                    '-vf', 'scale=w=min(1920\\,iw):h=min(1080\\,ih):force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30',
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
