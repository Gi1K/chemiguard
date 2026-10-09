import copy
import json
import os
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import cv2
from scenedetect.detectors import ContentDetector
from scenedetect.scene_detector import FlashFilter

from . import decisions, product_decisions
from .config import DATA, ROOT, fingerprint
from .sources import sources
from .observation import (OBSERVATION_CROP_VERSION, SCHEDULE, WINDOW_SECONDS, combine_observation, eligible_candidates,
                          face_quality, image_quality, request_due, select_candidate)
from .store import now, store, uid
from .vision import Vision, crop, identity, jpeg, observation_image
from .products import current_site_products
from .product_alerts import DECISIONS_VERSION as PRODUCT_ALERT_VERSION, assess_decisions_product, combine_product_check

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
        self.scene_epoch = 0
        self.seek_to = None
        self.slot = None
        self.reader_done = False
        self.frames = deque(maxlen=12)
        self.overlay_frames = deque(maxlen=20)
        self.tracks = {}
        self.scene = {'processing_state': 'WAITING', 'detections': [], 'suspected': False}
        self.scene_chain = None
        self.last_scene = 0
        self.last_request = 0
        self.cooldowns = {}
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='decisions')
        self.product_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='product-decisions')
        self.product_future = None
        self.preparation_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='observation-preparation')
        self.preparation_future = None
        self.product_catalog = None
        self.width = self.height = 0
        self.source_time = self.duration = 0
        self.playback_time = 0
        self.playback_epoch_start = 0
        self.frame_seq = 0
        self.started = time.monotonic()
        self.last_processed = 0
        self.metrics = {'processed_frames': 0, 'api_calls': 0, 'api_errors': 0, 'api_discarded': 0,
                        'product_api_calls': 0, 'product_api_errors': 0, 'product_api_discarded': 0,
                        'product_busy_skipped': 0, 'product_api_latency_ms': [], 'paired_ready_ms': [],
                        'api_latency_ms': [], 'input_tokens': 0, 'output_tokens': 0, 'events': 0,
                        'local_frame_ms': [],
                        'preparation_jobs': 0, 'preparation_busy_skipped': 0,
                        'preparation_errors': 0, 'preparation_latency_ms': 0,
                        'local_latency_ms': 0, 'processing_fps': 0}
        try:
            code_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            code_dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
        except (subprocess.SubprocessError, FileNotFoundError):
            code_sha = 'uncommitted'
            code_dirty = True
        self.record = store.put('run', {'id': self.id, 'source_id': source_id,
            'source': sources.metadata[source_id], 'source_mode': 'live_file_processing',
            'policy': policy, 'person_size': size, 'generation': self.generation,
            'status': 'LOADING', 'code_sha': code_sha, 'code_dirty': code_dirty,
            'pipeline_version': 'parallel-product-decisions-v7', 'decision_schedule_s': SCHEDULE,
            'tracking_pipeline_version': 'bounded-observation-worker-v1',
            'observation_crop_version': OBSERVATION_CROP_VERSION,
            'decision_routing': 'parallel_independent_requests_ppe_gate_on_join',
            'ppe_selection_version': decisions.PPE_SELECTION_VERSION,
            'decision_input_version': decisions.INPUT_VERSION, 'decision_image_detail': decisions.IMAGE_DETAIL,
            'evidence_window_s': WINDOW_SECONDS, 'shot_changes': [],
            'scene_detector': {'library': 'scenedetect-0.6.6', 'detector': 'ContentDetector', 'threshold': 27},
            'implementation': 'hackathon-finals-2026-10-09'})
        self.references = [row for row in store.list('reference') if row['revision'] <= policy['reference_revision']]
        self.site_products = copy.deepcopy(current_site_products(store.list('site_product')))
        self.record['ppe_prompt_version'] = decisions.prompt_version_for(policy, bool(self.site_products))
        self.record['site_products'] = self.site_products
        self.record['product_alert_version'] = PRODUCT_ALERT_VERSION
        self.record['product_alarm_severity'] = 'HIGH'
        self.record['product_primary_backend'] = 'decisions'
        self.record['product_decision_version'] = product_decisions.VERSION
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
                if position is not None and 0 <= position < self.duration:
                    self.seek_to = float(position)
                    self.source_time = self.playback_time = float(position)
            elif action == 'resume':
                self.state = 'RUNNING'
            elif action == 'seek':
                if position is None or not 0 <= position < self.duration:
                    raise ValueError('영상 범위를 벗어난 위치입니다.')
                self.seek_to = float(position)
                self.source_time = float(position)
                self.playback_time = float(position)
                self.slot = None
                self.frames.clear()
            else:
                raise ValueError('지원하지 않는 동작입니다.')
            self.generation += 1
            self.playback_epoch_start = self.playback_time
            self.slot = None
            self.overlay_frames.clear()
            self.tracks.clear()
            self.scene_chain = None
            self.scene = {'processing_state': 'STALE', 'detections': [], 'suspected': False}
        self._save()
        return self.snapshot()

    def _read(self, capture, fps):
        frame_index = 0
        deadline = time.monotonic()
        detector = None
        detector_epoch = None
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    target, paused, seek_epoch = self.seek_to, self.state == 'PAUSED', self.generation
                    if target is not None:
                        self.seek_to = None
                if target is not None:
                    frame_index = int(target * fps)
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                    deadline = time.monotonic()
                    if paused:
                        ok, frame = capture.read()
                        if ok:
                            with self.lock:
                                if seek_epoch == self.generation:
                                    self.frames.append((seek_epoch, frame_index, jpeg(frame, 80)))
                                    self.source_time, self.frame_seq = frame_index/fps, frame_index
                                    self.playback_time = frame_index/fps
                            frame_index += 1
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
                if detector_epoch != epoch:
                    detector = ContentDetector(min_scene_len=1, filter_mode=FlashFilter.Mode.SUPPRESS)
                    detector_epoch = epoch
                cuts = detector.process_frame(frame_index, cv2.resize(frame, (320, 180)))
                with self.lock:
                    if epoch == self.generation and self.state == 'RUNNING':
                        if cuts:
                            self.scene_epoch += 1
                            self.tracks.clear()
                            self.scene_chain = None
                            self.scene = {'processing_state': 'WAITING', 'detections': [], 'suspected': False}
                            self.record['shot_changes'].append({'generation': epoch, 'scene_epoch': self.scene_epoch,
                                                                'source_time_s': frame_index/fps})
                            self.overlay_frames.append({'generation': epoch, 'scene_epoch': self.scene_epoch,
                                'source_time_s': frame_index/fps, 'tracks': [], 'scene': copy.deepcopy(self.scene)})
                        self.slot = (epoch, self.scene_epoch, frame_index, frame_index/fps, captured, frame)
                        self.playback_time = frame_index/fps
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
            self.product_catalog = product_decisions.prepare_catalog(self.references, self.site_products)
            self.record['product_reference_inputs'] = self.product_catalog['image_inputs']
            self.record['product_reference_error'] = self.product_catalog['error']
            if self.references:
                try:
                    identity.load()
                    self.record['models']['identity'] = {'model': 'siglip2-base-patch16-384',
                                                         'sha256': identity.model_hash, 'role': 'supporting_only'}
                except Exception as exc:
                    self.record['models']['identity'] = {'role': 'supporting_only', 'error': type(exc).__name__}
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
            scene_epoch = self.scene_epoch
            last_save = time.monotonic()
            last_tick = None
            while not self.stop_event.is_set():
                with self.lock:
                    slot = self.slot
                    paused = self.state == 'PAUSED'
                if paused:
                    self.stop_event.wait(0.08)
                    continue
                if slot is None or slot[:3] == previous:
                    if self.reader_done:
                        break
                    self.stop_event.wait(0.015)
                    continue
                current_epoch, current_scene, seq, timestamp, captured, frame = slot
                if current_epoch != self.generation:
                    continue
                if epoch != current_epoch or scene_epoch != current_scene:
                    vision.reset_tracking()
                    epoch = current_epoch
                    scene_epoch = current_scene
                previous = (current_epoch, current_scene, seq)
                tick = time.monotonic()
                if last_tick is not None:
                    self.metrics['processing_fps'] = round(1/max(0.001, tick-last_tick), 1)
                last_tick = tick
                self._process(vision, frame, seq, timestamp, captured, current_epoch, current_scene)
                self.metrics['local_latency_ms'] = round((time.monotonic()-tick)*1000, 1)
                self.metrics['local_frame_ms'].append(self.metrics['local_latency_ms'])
                self.metrics['processed_frames'] += 1
                if time.monotonic()-last_save >= 5:
                    self._save()
                    last_save = time.monotonic()
                self.stop_event.wait(max(0, 0.2-(time.monotonic()-tick)))
            with self.lock:
                if self.state != 'ERROR':
                    self.state = 'STOPPED' if self.stop_event.is_set() else 'FINISHED'
                    if self.state == 'FINISHED':
                        self.playback_time = self.duration
        except Exception as exc:
            with self.lock:
                self.state, self.error = 'ERROR', f'{type(exc).__name__}: {str(exc)[:250]}'
        finally:
            self.stop_event.set()
            if reader:
                reader.join(timeout=3)
            self.preparation_pool.shutdown(wait=True, cancel_futures=True)
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.product_pool.shutdown(wait=True, cancel_futures=True)
            self._save()

    def _process(self, vision, frame, seq, timestamp, captured, epoch, scene_epoch):
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
            if epoch != self.generation or scene_epoch != self.scene_epoch or self.state != 'RUNNING':
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
                                'last_attempt': 0, 'last_observed': 0, 'candidates': deque(maxlen=5),
                                'active_violations': [], 'errors': 0,
                                'identity': {'state': 'UNAVAILABLE', 'candidates': []}, 'pending': False,
                                'reason': '착용 관찰 대기' if self.policy['coverall_required'] else '착용 관찰 비활성'}
                previous.update(row, last_seen=captured)
                self.tracks[key] = previous
                image = crop(frame, row['bbox'])
                quality = image_quality(image, row['bbox'], frame.shape, row['confidence'])
                if quality is not None:
                    previous['candidates'].append({'captured': captured, 'seq': seq, 'timestamp': timestamp,
                        'frame': frame, 'image': image, 'bbox': row['bbox'], 'quality': quality,
                        'confidence': row['confidence']})
                    previous['signature'] = quality['signature']
                elif not previous['result'] and not previous['pending']:
                    previous['reason'] = ('사람 검출 불확실 · 확인 필요' if row['confidence'] < 0.45 else
                                          '관찰 해상도 부족 · 확인 필요')
                while previous['candidates'] and captured-previous['candidates'][0]['captured'] > WINDOW_SECONDS:
                    previous['candidates'].popleft()
            for key in list(self.tracks):
                if captured-self.tracks[key]['last_seen'] > TRACK_TTL:
                    del self.tracks[key]
            self.frames.append((epoch, seq, jpeg(frame, 80)))
            if scene_result is not None:
                self._scene_result(scene_result, frame, seq, timestamp, captured)
            elif not self.policy['release_monitoring']:
                self.scene = {'processing_state': 'DISABLED', 'detections': [], 'suspected': False}
            self.overlay_frames.append({'generation': epoch, 'scene_epoch': scene_epoch, 'source_time_s': timestamp,
                'tracks': [row for row in self._public_tracks(time.monotonic(), timestamp)
                           if row['track_id'] in {item['track_id'] for item in detected}],
                'scene': copy.deepcopy(self.scene)})
            candidates = sorted([self.tracks[row['track_id']] for row in detected], key=lambda row: row['last_requested'])
        self._schedule_observations(vision, candidates, epoch, scene_epoch)

    def _schedule_observations(self, vision, candidates, epoch, scene_epoch):
        # Keep tracking responsive; a busy worker drops this tick instead of queuing old frames.
        with self.lock:
            if epoch != self.generation or scene_epoch != self.scene_epoch or self.state != 'RUNNING':
                return
            if self.preparation_future is not None and not self.preparation_future.done():
                self.metrics['preparation_busy_skipped'] += 1
                return
            if candidates:
                self.preparation_future = self.preparation_pool.submit(
                    self._prepare_observations, vision, candidates, epoch, scene_epoch)

    def _current_person(self, person, epoch, scene_epoch):
        return (self.state == 'RUNNING' and epoch == self.generation and scene_epoch == self.scene_epoch
                and self.tracks.get(person['track_id']) is person
                and time.monotonic()-person['last_seen'] <= TRACK_TTL)

    def _prepare_observations(self, vision, candidates, epoch, scene_epoch):
        started = time.monotonic()
        try:
            self._observe_people(vision, candidates, epoch, scene_epoch)
        except Exception as exc:
            with self.lock:
                self.metrics['preparation_errors'] += 1
                self.metrics['preparation_last_error'] = type(exc).__name__
        finally:
            with self.lock:
                self.metrics['preparation_jobs'] += 1
                self.metrics['preparation_latency_ms'] = round((time.monotonic()-started)*1000, 1)

    def _observe_people(self, vision, candidates, epoch, scene_epoch):
        identity_checks = 0
        for person in candidates:
            with self.lock:
                if not self._current_person(person, epoch, scene_epoch):
                    continue
                captured = time.monotonic()
                trigger = request_due(person, captured, person.get('signature')) if person.get('signature') is not None else None
                needs_api = self.policy['coverall_required'] and trigger is not None
                api_available = self.future is None or self.future.done()
                needs_identity = bool(self.references) and ((needs_api and api_available)
                                 or identity_checks < 2 and captured-person['last_identity'] >= 1)
                if not (needs_api and api_available or needs_identity):
                    continue
                if person['confidence'] < 0.45:
                    person.update(reason='사람 검출 불확실 · 확인 필요', last_attempt=captured,
                                  last_identity=captured, processing_state='WAITING')
                    continue
                # Detection appends to the deque concurrently. Hold a bounded snapshot for this preparation.
                candidate_frames = list(person['candidates'])
                last_observed = person['last_observed']
                person['last_attempt'] = captured
            selected = select_candidate(candidate_frames, captured, last_observed)
            if selected is None:
                continue
            if trigger == 'appearance_change':
                selected = candidate_frames[-1]
            prefer_face = (needs_api and api_available
                           and (self.policy['hood_required'] or self.policy.get('respirator_required', False)))
            eligible = eligible_candidates(candidate_frames, captured, last_observed)
            preparation_start = time.monotonic()
            pose_calls = 0
            try:
                for candidate in eligible if prefer_face and trigger != 'appearance_change' else [selected]:
                    with self.lock:
                        if not self._current_person(person, epoch, scene_epoch):
                            return
                    if 'body' not in candidate:
                        pose_calls += 1
                        candidate['body'] = vision.body(candidate['image'])
                        candidate['face_quality'] = face_quality(candidate['body'])
                if prefer_face and trigger != 'appearance_change':
                    selected = select_candidate([row for row in eligible if row.get('body') is not None],
                                                captured, last_observed, prefer_face=True)
                body = selected['body'] if selected is not None else None
                preparation_ms = round((time.monotonic()-preparation_start)*1000, 1)
            except Exception as exc:
                with self.lock:
                    person.update(reason=f'부위 추정 오류: {type(exc).__name__}', last_attempt=captured,
                                  last_identity=captured, processing_state='ERROR')
                continue
            with self.lock:
                if not self._current_person(person, epoch, scene_epoch):
                    continue
                if body is None:
                    person['reason'] = '관찰 해상도 부족 · 확인 필요'
                    person['processing_state'] = 'WAITING'
                    person['last_attempt'] = captured
                    person['last_identity'] = captured
                    continue
            if needs_identity:
                identity_checks += 1
                try:
                    matching = self._identify(body, selected, person, epoch, scene_epoch)
                except Exception as exc:
                    matching = {'state': 'UNAVAILABLE', 'candidates': [], 'reason': f'외형 검색 오류: {type(exc).__name__}'}
                with self.lock:
                    if not self._current_person(person, epoch, scene_epoch):
                        continue
                    person['identity'] = matching
                    person['last_identity'] = captured
            if needs_api and api_available:
                evidence_start = time.monotonic()
                envelope = self._evidence(selected['frame'], body['images'], selected['seq'], selected['timestamp'], selected['bbox'])
                envelope['timings_ms'] = {'candidate_preparation': preparation_ms, 'pose_calls': pose_calls,
                                          'evidence_encoding_and_save': round((time.monotonic()-evidence_start)*1000, 1)}
                envelope.update(track_id=person['track_id'], track_token=person['token'],
                                identity=copy.deepcopy(matching) if needs_identity else {},
                                generation=epoch, scene_epoch=scene_epoch, observed_monotonic=selected['captured'],
                                trigger_reason=trigger, requested_monotonic=time.monotonic(),
                                selection={'window_s': WINDOW_SECONDS, 'candidate_count': len(candidate_frames),
                                           'strategy': 'changed_frame' if trigger == 'appearance_change' else (
                                               'face_quality_and_recency' if prefer_face else 'quality_and_recency'),
                                           'face_quality': selected.get('face_quality'),
                                           'candidates': [{'source_time_s': row['timestamp'],
                                                           'quality_score': row['quality']['score'],
                                                           'face_quality': row.get('face_quality')}
                                                          for row in eligible],
                                           'age_s': round(captured-selected['captured'], 3),
                                           **{key: value for key, value in selected['quality'].items() if key != 'signature'}},
                                region_boxes=body['boxes'], coordinate_system='original_frame_pixel_xyxy',
                                region_coordinate_system='person_crop_pixel_xyxy', input_route=body['route'],
                                input_reason=body['reason'], keypoints=body['keypoints'],
                                keypoint_confidence=body['keypoint_confidence'],
                                pose_match_scores=body.get('pose_match_scores'),
                                head_region=body.get('head_region'),
                                detection_confidence=selected['confidence'],
                                policy_revision=self.policy['revision'], reference_revision=self.policy['reference_revision'])
                with self.lock:
                    if (not self._current_person(person, epoch, scene_epoch)
                            or time.monotonic()-selected['captured'] > OBSERVATION_TTL):
                        continue
                    person.update(pending=True, last_requested=captured, last_observed=selected['captured'],
                                  requested_signature=selected['quality']['signature'], trigger_reason=trigger)
                    self.metrics['api_calls'] += 1
                    self._dispatch_decisions(envelope, body['images'])

    def _dispatch_decisions(self, envelope, images):
        with self.lock:
            product_future = None
            self.future = self.pool.submit(decisions.observe, images, self.policy, bool(self.site_products))
            if self.site_products:
                if self.product_future is not None and not self.product_future.done():
                    self.metrics['product_busy_skipped'] += 1
                else:
                    product_future = self.product_pool.submit(product_decisions.timed_observe_product,
                                                              images, self.product_catalog)
                    self.product_future = product_future
            # Both independent requests are submitted before registering callbacks.
            # PPE is applied immediately; product may join only this exact PPE observation.
            self.future.add_done_callback(lambda future: self._answer(future, envelope, product_future))

    def _identify(self, body, selected, person, epoch, scene_epoch):
        image = body['images'].get('identity_torso')
        if image is None:
            return {'state': 'UNAVAILABLE', 'candidates': [], 'reason': '비교 가능한 몸통 영역 부족'}
        started = time.monotonic()
        matching = identity.search(image, self.references, self.site_products)
        evidence_id = uid('identity')
        image_path = self.path / 'evidence' / f'{evidence_id}.jpg'
        image_path.write_bytes(jpeg(image))
        matching.update(id=evidence_id, source_time_s=selected['timestamp'],
                        source_frame=selected['seq'], observed_monotonic=selected['captured'],
                        query_url=f'/media/runs/{self.id}/evidence/{evidence_id}.jpg',
                        query_box=body['boxes']['identity_torso'], person_box=selected['bbox'],
                        crop_method='pose-torso-context-v1', model_sha256=identity.model_hash,
                        reference_revision=self.policy['reference_revision'],
                        latency_ms=round((time.monotonic()-started)*1000, 1))
        with (self.path / 'identity.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(matching | {'track_id': person['track_id'], 'track_token': person['token'],
                                            'generation': epoch, 'scene_epoch': scene_epoch}, ensure_ascii=False)+'\n')
        return matching

    def _evidence(self, frame, images, seq, timestamp, bbox=None):
        observation_id = uid('observation')
        names = {}
        hashes = {}
        for name, image in {'frame': frame, **images}.items():
            encoded, extension = (observation_image(image, name) if name in ('person', 'torso', 'legs', 'head', 'identity_torso')
                                  else (jpeg(image), 'jpg'))
            filename = f'{observation_id}_{name}.{extension}'
            path = self.path / 'evidence' / filename
            path.write_bytes(encoded)
            names[name] = f'/media/runs/{self.id}/evidence/{filename}'
            hashes[name] = fingerprint(path)
        return {'id': observation_id, 'run_id': self.id, 'created_at': now(), 'source_frame': seq,
                'source_time_s': round(timestamp, 3), 'source_width': frame.shape[1], 'source_height': frame.shape[0],
                'bbox': bbox, 'images': names, 'image_hashes': hashes}

    def _answer(self, future, envelope, product_future):
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
            elif envelope['scene_epoch'] != self.scene_epoch:
                discarded = 'scene_changed'
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
            if not discarded:
                transition = combine_observation(track, result, envelope['observed_monotonic'], envelope['id'],
                                                 OBSERVATION_TTL, CONSENSUS_WINDOW)
                observation['transition'] = transition | {
                    'active_violations': track['active_violations'].copy(),
                    'confirmed': track['confirmed'], 'complete_confirmed': track['complete_confirmed']}
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
                self._join_product(product_future, envelope, result, discarded)
                return
            track['result'] = result | {'observed_monotonic': envelope['observed_monotonic'],
                                        'source_time_s': envelope['source_time_s'], 'observation_id': envelope['id']}
            track['processing_state'] = result['processing_state']
            track['reason'] = result.get('reason') or result.get('error')
            track['errors'] = track.get('errors', 0)+1 if result.get('error') else 0
            if transition['new_violations']:
                self._event('VIOLATION_SUSPECTED', ' · '.join(transition['new_violations']), observation,
                            str(track['token'])+':'+','.join(transition['new_violations']),
                            transition['supporting_observation_ids'])
            if transition['cleared']:
                # A later recurrence is a new episode, not a repeated alarm for this episode.
                for key in list(self.cooldowns):
                    if key.startswith('VIOLATION_SUSPECTED:'+track['token']+':'):
                        del self.cooldowns[key]
            if not transition['usable'] or self.policy['identity_required']:
                self._event('REVIEW_REQUIRED', track['reason'] if not transition['usable'] else '등록 제품 확인 필요 · 외형 후보 미확정', observation, str(track['token']))
            self._join_product(product_future, envelope, result)

    def _join_product(self, future, envelope, ppe, ppe_discard_reason=None):
        if not self.site_products:
            return
        if future is None:
            decision = {'version': product_decisions.VERSION, 'membership': 'uncertain', 'reason': '제품 작업 중 · 대기열 생략',
                        'candidate': None, 'api_called': False, 'latency_ms': 0}
            self._product_answer(None, envelope, ppe, decision, ppe_discard_reason)
            return
        future.add_done_callback(lambda completed: self._product_answer(completed, envelope, ppe,
                                                                        ppe_discard_reason=ppe_discard_reason))

    def _product_answer(self, future, envelope, ppe, decision=None, ppe_discard_reason=None):
        try:
            decision = future.result() if future is not None else decision
        except Exception as exc:
            decision = {'version': product_decisions.VERSION, 'membership': 'uncertain', 'candidate': None,
                        'error': f'제품 관찰 실패: {type(exc).__name__}', 'api_called': False}
        completed = time.monotonic()
        decision = product_decisions.apply_ppe_gate(ppe, decision)
        decision.setdefault('timings_ms', {})['paired_ready_after_dispatch'] = round(
            (completed-envelope['requested_monotonic'])*1000, 1)
        with self.lock:
            track = self.tracks.get(envelope['track_id'])
            discarded = None
            if ppe_discard_reason:
                discarded = 'ppe_' + ppe_discard_reason
            elif self.state != 'RUNNING':
                discarded = 'run_not_running'
            elif envelope['generation'] != self.generation:
                discarded = 'generation_changed'
            elif envelope['scene_epoch'] != self.scene_epoch:
                discarded = 'scene_changed'
            elif track is None or track['token'] != envelope['track_token'] or completed-track['last_seen'] > TRACK_TTL:
                discarded = 'track_expired'
            elif completed-envelope['observed_monotonic'] > OBSERVATION_TTL:
                discarded = 'observation_expired'
            elif max((track.get('product_result') or {}).get('observed_monotonic', 0),
                     (track.get('result') or {}).get('observed_monotonic', 0)) > envelope['observed_monotonic']:
                discarded = 'newer_observation'
            decision['query_url'] = envelope['images'].get('identity_torso')
            check = assess_decisions_product(ppe, decision, envelope.get('identity', {}), self.site_products)
            check['source_time_s'] = envelope['source_time_s']
            observation = envelope | {'id': uid('product_observation'), 'observation_kind': 'product',
                'ppe_observation_id': envelope['id'], 'created_at': now(), 'completed_at': now(),
                'completed_monotonic': completed, 'applied': discarded is None, 'discard_reason': discarded,
                'result': {'product_check': check, 'product_decision': decision, 'wearing': ppe.get('wearing'),
                           'parts': ppe.get('parts'), 'latency_ms': decision.get('latency_ms')}}
            if not discarded:
                transition = combine_product_check(track, check, envelope['observed_monotonic'], observation['id'])
                observation['product_transition'] = transition
                track['product_result'] = {'check': check, 'observed_monotonic': envelope['observed_monotonic']}
            store.put('observation', observation)
            with (self.path / 'observations.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(observation, ensure_ascii=False) + '\n')
            if decision.get('api_called'):
                self.metrics['api_calls'] += 1
                self.metrics['product_api_calls'] += 1
                self.metrics['product_api_latency_ms'].append(decision['latency_ms'])
                self.metrics['paired_ready_ms'].append(decision['timings_ms']['paired_ready_after_dispatch'])
                self.metrics['api_latency_ms'].append(decision['latency_ms'])
                usage = decision.get('usage') or {}
                self.metrics['input_tokens'] += usage.get('input_tokens', 0)
                self.metrics['output_tokens'] += usage.get('output_tokens', 0)
            if decision.get('error'):
                self.metrics['product_api_errors'] += 1
                self.metrics['api_errors'] += int(bool(decision.get('api_called')))
            if discarded:
                self.metrics['product_api_discarded'] += int(bool(decision.get('api_called')))
                self.metrics['api_discarded'] += int(bool(decision.get('api_called')))
            elif transition['new_alerts']:
                self._event('PRODUCT_MISMATCH_SUSPECTED',
                            ' · '.join(check['active_alerts'][key] for key in transition['new_alerts']),
                            observation, track['token']+':'+observation['id'], transition['supporting_observation_ids'])

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
            with (self.path / 'observations.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(observation, ensure_ascii=False) + '\n')
            self._event('RELEASE_SUSPECTED', '누출 징후가 연속 관찰되었습니다.', observation, 'scene')

    def _event(self, kind, reason, observation, key, supporting_observation_ids=None):
        cooldown_key = kind + ':' + key
        timestamp = time.monotonic()
        if timestamp-self.cooldowns.get(cooldown_key, 0) < 15:
            return
        self.cooldowns[cooldown_key] = timestamp
        store.put('event', {'run_id': self.id, 'kind': kind, 'reason': reason,
                            'severity': 'HIGH' if kind in ('VIOLATION_SUSPECTED', 'PRODUCT_MISMATCH_SUSPECTED') else 'REVIEW',
                            'source_time_s': observation['source_time_s'], 'track_id': observation.get('track_id'),
                            'observation_id': observation['id'], 'policy_id': self.policy['id'],
                            'supporting_observation_ids': supporting_observation_ids or [observation['id']],
                            'policy_revision': self.policy['revision'], 'source_name': sources.metadata[self.source_id]['name'],
                            'preview_url': observation['images']['frame'], 'review_status': 'OPEN'})
        self.metrics['events'] += 1

    def _public_tracks(self, current, source_time=None):
        tracks = []
        for track in self.tracks.values():
            if current-track['last_seen'] > TRACK_TTL and self.state == 'RUNNING':
                continue
            result = track.get('result') or {}
            expired = current-result.get('observed_monotonic', 0) > OBSERVATION_TTL
            future = source_time is not None and result.get('source_time_s', 0) > source_time
            halted = self.state != 'RUNNING'
            valid = not expired and not halted and not future
            state = ('STALE' if expired and result else track['processing_state']) if not halted else 'STALE'
            wearing = result.get('wearing', 'UNKNOWN') if valid else 'UNKNOWN'
            confirmed = track.get('confirmed', False) and valid
            reason = '관측 만료' if expired and result else track.get('reason')
            if wearing in ('WORN', 'VISIBLE_WORN') and not confirmed:
                wearing, reason = 'UNKNOWN', '착용 재확인 중 · 연속 2회 필요'
            elif (wearing == 'WORN' and self.policy.get('wearing_assessment') == 'visible_regions'
                  and not track.get('complete_confirmed')):
                wearing, reason = 'VISIBLE_WORN', '보이는 범위 착용 · 전체 필수 부위 재확인 중'
            if not self.policy['coverall_required']:
                state, wearing = 'DISABLED', 'UNKNOWN'
            matching = track['identity']
            product_result = track.get('product_result') or {}
            product_check = product_result.get('check', {})
            if (halted or current-product_result.get('observed_monotonic', 0) > OBSERVATION_TTL
                    or source_time is not None and product_check.get('source_time_s', 0) > source_time):
                product_check = {'state': 'STALE', 'primary_backend': 'decisions'}
            if matching.get('candidates') and (halted
                    or current-matching.get('observed_monotonic', 0) > 3
                    or source_time is not None and matching.get('source_time_s', 0) > source_time):
                matching = {'state': 'STALE', 'candidates': [], 'reason': '외형 비교 관측 만료'}
            tracks.append(copy.deepcopy({key: track[key] for key in ('track_id', 'bbox', 'confidence', 'pending')} |
                          {'identity': matching, 'track_token': track['token'], 'wearing': wearing, 'processing_state': state,
                           'parts': result.get('parts', {}) if valid else {}, 'confirmed': confirmed,
                           'all_required_observed': bool(valid and track.get('complete_confirmed')),
                           'violations': result.get('violations', []) if valid else [],
                           'active_violations': track['active_violations'], 'reason': reason,
                           'product_check': product_check,
                           'product_alerts': dict(track.get('product_alerts', {})),
                           'trigger_reason': track.get('trigger_reason'),
                           'source_time_s': result.get('source_time_s'), 'latency_ms': result.get('latency_ms')}))
        return tracks

    def snapshot(self):
        current = time.monotonic()
        with self.lock:
            tracks = self._public_tracks(current)
            scene = copy.deepcopy(self.scene)
            if scene['processing_state'] == 'RUNNING' and (current-self.last_scene > 2 or self.state != 'RUNNING'):
                scene.update(processing_state='STALE', suspected=False)
            metrics = copy.deepcopy(self.metrics)
            latency = metrics.pop('api_latency_ms')
            product_latency = metrics.pop('product_api_latency_ms')
            metrics['product_api_mean_ms'] = round(sum(product_latency)/len(product_latency), 1) if product_latency else None
            paired_latency = metrics.pop('paired_ready_ms')
            metrics['paired_ready_mean_ms'] = round(sum(paired_latency)/len(paired_latency), 1) if paired_latency else None
            local_latency = metrics.pop('local_frame_ms')
            metrics['local_mean_ms'] = round(sum(local_latency)/len(local_latency), 1) if local_latency else None
            metrics['api_mean_ms'] = round(sum(latency)/len(latency), 1) if latency else None
            image_key = self.frames[-1][:2] if self.frames else None
            return {'id': self.id, 'status': self.state, 'error': self.error, 'source_id': self.source_id,
                    'source_name': sources.metadata[self.source_id]['name'], 'source_mode': 'live_file_processing',
                    'source_time_s': round(self.source_time, 3), 'duration_s': self.duration,
                    'playback_time_s': round(self.playback_time, 3),
                    'playback_epoch_start_s': self.playback_epoch_start,
                    'overlay_frames': copy.deepcopy(list(self.overlay_frames)),
                    'source_width': self.width, 'source_height': self.height, 'generation': self.generation,
                    'scene_epoch': self.scene_epoch,
                    'person_size': self.size, 'people_state': self.record.get('people_state', 'WAITING'),
                    'tracks': tracks, 'scene': scene, 'metrics': metrics, 'policy': self.policy,
                    'site_products': self.site_products,
                    'product_primary_backend': 'decisions',
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
