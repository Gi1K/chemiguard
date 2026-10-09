import copy
import json
import os
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import cv2

from . import decisions
from .config import DATA, ROOT, fingerprint
from .sources import sources
from .store import now, store, uid
from .vision import Vision, crop, identity, jpeg

OBSERVATION_TTL = 5.0
TRACK_TTL = 1.2
CONSENSUS_WINDOW = 10.0


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0


class Run:
    def __init__(self, source_id, policy, size):
        self.id = uid('run')
        self.path = DATA / 'runs' / self.id
        (self.path / 'evidence').mkdir(parents=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.policy = copy.deepcopy(policy)
        self.source_id = source_id
        self.size = size
        self.state = 'LOADING'
        self.error = None
        self.generation = 1
        self.seek_to = None
        self.slot = None
        self.reader_done = False
        self.frames = deque(maxlen=12)
        self.tracks = {}
        self.scene = {'processing_state': 'WAITING', 'detections': [], 'suspected': False}
        self.scene_chain = None
        self.last_scene = 0
        self.last_request = 0
        self.cooldowns = {}
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='decisions')
        self.width = self.height = 0
        self.source_time = self.duration = 0
        self.frame_seq = 0
        self.started = time.monotonic()
        self.last_processed = 0
        self.metrics = {'processed_frames': 0, 'api_calls': 0, 'api_errors': 0, 'api_discarded': 0,
                        'api_latency_ms': [], 'input_tokens': 0, 'output_tokens': 0, 'events': 0,
                        'local_latency_ms': 0, 'processing_fps': 0}
        try:
            code_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            code_sha = 'uncommitted'
        self.record = store.put('run', {'id': self.id, 'source_id': source_id,
            'source': sources.metadata[source_id], 'source_mode': 'live_file_processing',
            'policy': policy, 'person_size': size, 'generation': self.generation,
            'status': 'LOADING', 'code_sha': code_sha, 'implementation': 'hackathon-finals-2026-10-09'})
        self.references = [row for row in store.list('reference') if row['revision'] <= policy['reference_revision']]
        self.thread = threading.Thread(target=self._work, daemon=True, name=self.id)
        self.thread.start()

    def _save(self):
        with self.lock:
            self.record.update(status=self.state, error=self.error, duration=self.duration,
                               source_time=self.source_time, generation=self.generation, metrics=copy.deepcopy(self.metrics))
            record = copy.deepcopy(self.record)
        store.put('run', record, replace=True)
        (self.path / 'run.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')

    def control(self, action, position=None):
        with self.lock:
            if action == 'stop':
                self.state = 'STOPPED'
                self.stop_event.set()
            elif self.state not in ('RUNNING', 'PAUSED'):
                raise ValueError('실행 중인 영상에서만 사용할 수 있습니다.')
            elif action == 'pause':
                self.state = 'PAUSED'
            elif action == 'resume':
                self.state = 'RUNNING'
            elif action == 'seek':
                if position is None or not 0 <= position < self.duration:
                    raise ValueError('영상 범위를 벗어난 위치입니다.')
                self.seek_to = float(position)
                self.source_time = float(position)
                self.slot = None
            else:
                raise ValueError('지원하지 않는 동작입니다.')
            self.generation += 1
            self.tracks.clear()
            self.scene_chain = None
            self.scene = {'processing_state': 'STALE', 'detections': [], 'suspected': False}
        self._save()
        return self.snapshot()

    def _read(self, capture, fps):
        frame_index = 0
        deadline = time.monotonic()
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    target, paused = self.seek_to, self.state == 'PAUSED'
                    if target is not None:
                        self.seek_to = None
                if target is not None:
                    frame_index = int(target * fps)
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                    deadline = time.monotonic()
                if paused:
                    deadline = time.monotonic()
                    self.stop_event.wait(0.05)
                    continue
                if self.stop_event.wait(max(0, deadline - time.monotonic())):
                    break
                with self.lock:
                    epoch = self.generation
                ok, frame = capture.read()
                if not ok:
                    break
                captured = time.monotonic()
                with self.lock:
                    if epoch == self.generation and self.state == 'RUNNING':
                        self.slot = (epoch, frame_index, frame_index/fps, captured, frame)
                frame_index += 1
                deadline += 1/fps
        finally:
            capture.release()
            self.reader_done = True

    def _work(self):
        reader = None
        try:
            video = sources.path(self.source_id)
            self.record['input_sha256'] = fingerprint(video)
            vision = Vision(self.size, self.policy['release_monitoring'])
            self.record['models'] = vision.manifest
            if self.references:
                identity.load()
                self.record['models']['identity'] = {'model': 'siglip2-base-patch16-384', 'sha256': identity.model_hash}
            capture = cv2.VideoCapture(str(video))
            if not capture.isOpened():
                raise ValueError('영상을 열 수 없습니다.')
            fps = capture.get(cv2.CAP_PROP_FPS)
            count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps <= 0 or count <= 0:
                capture.release()
                raise ValueError('영상 FPS 또는 길이를 읽지 못했습니다.')
            self.duration = count/fps
            self.width, self.height = int(capture.get(3)), int(capture.get(4))
            with self.lock:
                if self.stop_event.is_set():
                    capture.release()
                    return
                self.state = 'RUNNING'
            self._save()
            reader = threading.Thread(target=self._read, args=(capture, fps), daemon=True)
            reader.start()
            previous = None
            epoch = self.generation
            last_save = time.monotonic()
            last_tick = None
            while not self.stop_event.is_set():
                with self.lock:
                    slot = self.slot
                    paused = self.state == 'PAUSED'
                if paused:
                    self.stop_event.wait(0.08)
                    continue
                if slot is None or (slot[0], slot[1]) == previous:
                    if self.reader_done:
                        break
                    self.stop_event.wait(0.015)
                    continue
                current_epoch, seq, timestamp, captured, frame = slot
                if current_epoch != self.generation:
                    continue
                if epoch != current_epoch:
                    vision.reset_tracking()
                    epoch = current_epoch
                previous = (current_epoch, seq)
                tick = time.monotonic()
                if last_tick is not None:
                    self.metrics['processing_fps'] = round(1/max(0.001, tick-last_tick), 1)
                last_tick = tick
                self._process(vision, frame, seq, timestamp, captured, current_epoch)
                self.metrics['local_latency_ms'] = round((time.monotonic()-tick)*1000, 1)
                self.metrics['processed_frames'] += 1
                if time.monotonic()-last_save >= 5:
                    self._save()
                    last_save = time.monotonic()
                self.stop_event.wait(max(0, 0.2-(time.monotonic()-tick)))
            with self.lock:
                if self.state != 'ERROR':
                    self.state = 'STOPPED' if self.stop_event.is_set() else 'FINISHED'
        except Exception as exc:
            with self.lock:
                self.state, self.error = 'ERROR', f'{type(exc).__name__}: {str(exc)[:250]}'
        finally:
            self.stop_event.set()
            if reader:
                reader.join(timeout=3)
            self.pool.shutdown(wait=True, cancel_futures=True)
            self._save()

    def _process(self, vision, frame, seq, timestamp, captured, epoch):
        people_error = None
        try:
            detected = vision.people(frame)
        except Exception as exc:
            detected, people_error = [], f'사람 분석 실패: {type(exc).__name__}'
        scene_result = None
        if self.policy['release_monitoring']:
            try:
                scene_result = vision.scene(frame, self.policy['scene_roi'])
            except Exception as exc:
                with self.lock:
                    self.scene = {'processing_state': 'ERROR', 'detections': [], 'suspected': False,
                                  'error': f'장면 분석 실패: {type(exc).__name__}'}
                    self.scene_chain = None
        with self.lock:
            if epoch != self.generation or self.state != 'RUNNING':
                return
            self.source_time, self.frame_seq = timestamp, seq
            self.last_processed = time.monotonic()
            self.error = people_error
            self.record['people_state'] = 'ERROR' if people_error else 'RUNNING'
            for row in detected:
                key = row['track_id']
                previous = self.tracks.get(key)
                if previous is None or captured-previous['last_seen'] > TRACK_TTL:
                    previous = {'track_id': key, 'token': uid('track'), 'result': None, 'history': [],
                                'last_requested': 0, 'last_identity': 0, 'processing_state': 'WAITING',
                                'identity': {'state': 'UNAVAILABLE', 'candidates': []}, 'pending': False,
                                'reason': '착용 관찰 대기' if self.policy['coverall_required'] else '착용 관찰 비활성'}
                previous.update(row, last_seen=captured)
                self.tracks[key] = previous
            for key in list(self.tracks):
                if captured-self.tracks[key]['last_seen'] > TRACK_TTL:
                    del self.tracks[key]
            self.frames.append((epoch, seq, jpeg(frame, 80)))
            if scene_result is not None:
                self._scene_result(scene_result, frame, seq, timestamp, captured)
            elif not self.policy['release_monitoring']:
                self.scene = {'processing_state': 'DISABLED', 'detections': [], 'suspected': False}
            candidates = sorted([self.tracks[row['track_id']] for row in detected], key=lambda row: row['last_requested'])
        for person in candidates[:2]:
            needs_api = self.policy['coverall_required'] and not person['pending'] and captured-person['last_requested'] >= 2
            api_available = self.future is None or self.future.done()
            needs_identity = bool(self.references) and captured-person['last_identity'] >= 1
            if not (needs_api and api_available or needs_identity):
                continue
            image = crop(frame, person['bbox'])
            body = vision.body(image)
            with self.lock:
                if epoch != self.generation or person['track_id'] not in self.tracks or self.state != 'RUNNING':
                    return
                if body is None:
                    person['reason'] = '몸통 근거 부족 · 확인 필요'
                    person['processing_state'] = 'WAITING'
                    person['last_requested'] = captured
                    person['last_identity'] = captured
                    continue
            if needs_identity:
                try:
                    matching = identity.search(body['images']['torso'], self.references)
                except Exception as exc:
                    matching = {'state': 'UNAVAILABLE', 'candidates': [], 'reason': f'외형 검색 오류: {type(exc).__name__}'}
                with self.lock:
                    person['identity'] = matching
                    person['last_identity'] = captured
            if needs_api and api_available:
                envelope = self._evidence(frame, body['images'], seq, timestamp, person['bbox'])
                envelope.update(track_id=person['track_id'], track_token=person['token'],
                                generation=epoch, observed_monotonic=captured,
                                region_boxes=body['boxes'], coordinate_system='original_frame_pixel_xyxy',
                                policy_revision=self.policy['revision'], reference_revision=self.policy['reference_revision'])
                with self.lock:
                    person.update(pending=True, last_requested=captured)
                    self.metrics['api_calls'] += 1
                self.future = self.pool.submit(decisions.observe, body['images'], self.policy)
                self.future.add_done_callback(lambda future, env=envelope: self._answer(future, env))

    def _evidence(self, frame, images, seq, timestamp, bbox=None):
        observation_id = uid('observation')
        names = {}
        hashes = {}
        for name, image in {'frame': frame, **images}.items():
            filename = f'{observation_id}_{name}.jpg'
            path = self.path / 'evidence' / filename
            path.write_bytes(jpeg(image))
            names[name] = f'/media/runs/{self.id}/evidence/{filename}'
            hashes[name] = fingerprint(path)
        return {'id': observation_id, 'run_id': self.id, 'created_at': now(), 'source_frame': seq,
                'source_time_s': round(timestamp, 3), 'source_width': frame.shape[1], 'source_height': frame.shape[0],
                'bbox': bbox, 'images': names, 'image_hashes': hashes}

    def _answer(self, future, envelope):
        try:
            result = future.result()
        except Exception as exc:
            result = {'wearing': 'UNKNOWN', 'processing_state': 'ERROR', 'error': f'관찰 실패: {type(exc).__name__}'}
        completed = time.monotonic()
        with self.lock:
            track = self.tracks.get(envelope['track_id'])
            discarded = None
            if self.state != 'RUNNING':
                discarded = 'run_not_running'
            elif envelope['generation'] != self.generation:
                discarded = 'generation_changed'
            elif track is None or track['token'] != envelope['track_token'] or completed-track['last_seen'] > TRACK_TTL:
                discarded = 'track_expired'
            elif completed-envelope['observed_monotonic'] > OBSERVATION_TTL:
                discarded = 'observation_expired'
            elif track['result'] and track['result']['observed_monotonic'] >= envelope['observed_monotonic']:
                discarded = 'out_of_order'
            if track and track['token'] == envelope['track_token']:
                track['pending'] = False
            observation = envelope | {'completed_at': now(), 'completed_monotonic': completed,
                                      'result': result, 'applied': discarded is None, 'discard_reason': discarded}
            store.put('observation', observation)
            with (self.path / 'observations.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(observation, ensure_ascii=False) + '\n')
            if result.get('latency_ms') is not None:
                self.metrics['api_latency_ms'].append(result['latency_ms'])
            usage = result.get('usage') or {}
            self.metrics['input_tokens'] += usage.get('input_tokens', 0)
            self.metrics['output_tokens'] += usage.get('output_tokens', 0)
            if result.get('error'):
                self.metrics['api_errors'] += 1
            if discarded:
                self.metrics['api_discarded'] += 1
                return
            track['result'] = result | {'observed_monotonic': envelope['observed_monotonic'],
                                        'source_time_s': envelope['source_time_s'], 'observation_id': envelope['id']}
            track['processing_state'] = result['processing_state']
            track['reason'] = result.get('reason') or result.get('error')
            signature = '|'.join(sorted(result.get('violations', []))) or result['wearing']
            usable = not result.get('error') and (bool(result.get('violations')) or result['wearing'] == 'WORN' and not result.get('review_required'))
            history = track['history']
            if not usable or history and (history[-1]['signature'] != signature or envelope['observed_monotonic']-history[-1]['time'] > OBSERVATION_TTL):
                history.clear()
            if usable:
                history.append({'signature': signature, 'time': envelope['observed_monotonic']})
                history[:] = history[-2:]
            confirmed = len(history) == 2 and history[-1]['time']-history[0]['time'] <= CONSENSUS_WINDOW
            track['confirmed'] = confirmed
            if result.get('violations') and confirmed:
                self._event('VIOLATION_SUSPECTED', track['reason'], observation, str(track['token']))
            elif not usable or self.policy['identity_required']:
                self._event('REVIEW_REQUIRED', track['reason'] if not usable else '등록 제품 확인 필요 · 외형 후보 미확정', observation, str(track['token']))

    def _scene_result(self, detections, frame, seq, timestamp, captured):
        self.last_scene = time.monotonic()
        self.scene = {'processing_state': 'RUNNING', 'detections': detections, 'suspected': False,
                      'source_time_s': round(timestamp, 3)}
        if not detections:
            self.scene_chain = None
            return
        best = max(detections, key=lambda item: item['confidence'])
        chain = self.scene_chain
        if chain is None or captured-chain['last'] > 0.6 or overlap(chain['bbox'], best['bbox']) < 0.3:
            chain = {'start': captured, 'count': 0}
        chain.update(last=captured, bbox=best['bbox'], count=chain['count']+1)
        self.scene_chain = chain
        suspected = chain['count'] >= 3 and captured-chain['start'] >= 1
        self.scene['suspected'] = suspected
        self.scene['persistence_s'] = round(captured-chain['start'], 1)
        if suspected and captured-self.cooldowns.get('RELEASE_SUSPECTED:scene', 0) >= 15:
            envelope = self._evidence(frame, {'release': crop(frame, best['bbox'])}, seq, timestamp, best['bbox'])
            observation = envelope | {'result': {'scene_detections': detections, 'native_class': best['native_class'],
                                      'processing_state': 'RUNNING'}, 'applied': True, 'discard_reason': None,
                                      'generation': self.generation, 'coordinate_system': 'original_frame_pixel_xyxy'}
            store.put('observation', observation)
            self._event('RELEASE_SUSPECTED', '가시적 연무·분출 의심이 연속 관찰되었습니다.', observation, 'scene')

    def _event(self, kind, reason, observation, key):
        cooldown_key = kind + ':' + key
        timestamp = time.monotonic()
        if timestamp-self.cooldowns.get(cooldown_key, 0) < 15:
            return
        self.cooldowns[cooldown_key] = timestamp
        store.put('event', {'run_id': self.id, 'kind': kind, 'reason': reason,
                            'source_time_s': observation['source_time_s'], 'track_id': observation.get('track_id'),
                            'observation_id': observation['id'], 'policy_id': self.policy['id'],
                            'policy_revision': self.policy['revision'], 'source_name': sources.metadata[self.source_id]['name'],
                            'preview_url': observation['images']['frame'], 'review_status': 'OPEN'})
        self.metrics['events'] += 1

    def snapshot(self):
        current = time.monotonic()
        with self.lock:
            tracks = []
            for track in self.tracks.values():
                if current-track['last_seen'] > TRACK_TTL and self.state == 'RUNNING':
                    continue
                result = copy.deepcopy(track.get('result')) or {}
                expired = current-result.get('observed_monotonic', 0) > OBSERVATION_TTL
                halted = self.state != 'RUNNING'
                state = ('STALE' if expired and result else track['processing_state']) if not halted else 'STALE'
                wearing = result.get('wearing', 'UNKNOWN') if not expired and not halted else 'UNKNOWN'
                if not self.policy['coverall_required']:
                    state, wearing = 'DISABLED', 'UNKNOWN'
                tracks.append({key: track[key] for key in ('track_id', 'bbox', 'confidence', 'identity', 'pending')} |
                              {'wearing': wearing, 'processing_state': state, 'parts': result.get('parts', {}) if not expired and not halted else {},
                               'confirmed': track.get('confirmed', False) and not expired and not halted,
                               'violations': result.get('violations', []) if not expired and not halted else [],
                               'reason': '관측 만료' if expired and result else track.get('reason'),
                               'source_time_s': result.get('source_time_s'), 'latency_ms': result.get('latency_ms')})
            scene = copy.deepcopy(self.scene)
            if scene['processing_state'] == 'RUNNING' and (current-self.last_scene > 2 or self.state != 'RUNNING'):
                scene.update(processing_state='STALE', suspected=False)
            metrics = copy.deepcopy(self.metrics)
            latency = metrics.pop('api_latency_ms')
            metrics['api_mean_ms'] = round(sum(latency)/len(latency), 1) if latency else None
            image_key = self.frames[-1][:2] if self.frames else None
            return {'id': self.id, 'status': self.state, 'error': self.error, 'source_id': self.source_id,
                    'source_name': sources.metadata[self.source_id]['name'], 'source_mode': 'live_file_processing',
                    'source_time_s': round(self.source_time, 3), 'duration_s': self.duration,
                    'source_width': self.width, 'source_height': self.height, 'generation': self.generation,
                    'person_size': self.size, 'people_state': self.record.get('people_state', 'WAITING'),
                    'tracks': tracks, 'scene': scene, 'metrics': metrics, 'policy': self.policy,
                    'frame_url': f'/api/runs/{self.id}/frame?generation={image_key[0]}&seq={image_key[1]}' if image_key else None,
                    'updated_at': now(), 'frame_age_s': round(current-self.last_processed, 2) if self.last_processed else None}

    def frame(self, generation, seq):
        with self.lock:
            for epoch, frame_seq, data in self.frames:
                if epoch == generation and frame_seq == seq:
                    return data
        return None


class Monitor:
    def __init__(self):
        self.active = None
        self.lock = threading.Lock()
        for record in store.list('run'):
            if record['status'] in ('RUNNING', 'LOADING', 'PAUSED'):
                store.put('run', record | {'status': 'INTERRUPTED', 'error': '서버 재시작으로 실행 중단'}, replace=True)

    def start(self, source_id, policy, size):
        with self.lock:
            if self.active and self.active.thread.is_alive():
                raise ValueError('기존 실행이 종료된 뒤 다시 시작해 주세요.')
            self.active = Run(source_id, policy, size)
            return self.active.snapshot()

    def busy(self):
        return bool(self.active and self.active.thread.is_alive())


monitor = Monitor()
