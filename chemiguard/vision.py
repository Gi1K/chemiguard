import threading

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps
from transformers import AutoImageProcessor, SiglipVisionModel
from ultralytics import YOLO

from .config import DEVICE, IDENTITY_MODEL, PERSON_MODELS, POSE_MODEL, RELEASE_MODEL, fingerprint
from .products import rank_references
from .observation import observation_size_ok

GPU_LOCK = threading.RLock()


def bounded_box(box, width, height):
    x1, y1, x2, y2 = [int(round(float(value))) for value in box]
    return [max(0, min(x1, width - 1)), max(0, min(y1, height - 1)),
            max(1, min(x2, width)), max(1, min(y2, height))]


def crop(frame, box):
    x1, y1, x2, y2 = bounded_box(box, frame.shape[1], frame.shape[0])
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2].copy()


def jpeg(frame, quality=85):
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError('이미지 인코딩 실패')
    return encoded.tobytes()


def observation_image(image, region):
    if region != 'head':
        return jpeg(image, 95), 'jpg'
    ok, encoded = cv2.imencode('.png', image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not ok:
        raise ValueError('이미지 인코딩 실패')
    return encoded.tobytes(), 'png'


def head_region(points, confidence, width, height):
    valid = (confidence >= 0.4) & np.isfinite(points).all(axis=1)
    valid &= (points[:, 0] > 0) & (points[:, 0] < width) & (points[:, 1] > 0) & (points[:, 1] < height)
    face_ids = [index for index in range(5) if valid[index]]
    shoulders = [index for index in (5, 6) if valid[index]]
    hips = [index for index in (11, 12) if valid[index]]
    if not face_ids:
        # A broad context crop is not evidence that the face itself is visible.
        bottom = max(height * 0.35, max((points[i, 1] for i in shoulders), default=0) + height * 0.12)
        desired = [0, 0, width, min(height, bottom)]
        method = 'upper_body_context'
    else:
        face = points[face_ids]
        center = face.mean(axis=0)
        span = float(np.ptp(face, axis=0).max())
        torso_length = (float(np.linalg.norm(points[hips].mean(axis=0)-points[shoulders].mean(axis=0)))
                        if shoulders and hips else height * 0.3)
        # COCO has no chin point: retain a generous jaw/filter margin around the face landmarks.
        scale = max(span * 1.8, min(torso_length * 0.65, height * 0.35), min(width * 0.6, height * 0.22), 32)
        desired = [min(face[:, 0].min()-scale*0.45, center[0]-scale*0.7),
                   face[:, 1].min()-scale*0.65,
                   max(face[:, 0].max()+scale*0.45, center[0]+scale*0.7),
                   face[:, 1].max()+scale*0.85]
        method = 'face_landmarks_with_jaw_margin'
    box = bounded_box(desired, width, height)
    return box, {'method': method, 'face_keypoints': face_ids,
                 'landmark_confidence': round(float(confidence[face_ids].mean()), 4) if face_ids else 0,
                 'clipped_edges': int(sum((desired[0] < 0, desired[1] < 0, desired[2] > width, desired[3] > height))),
                 'version': 'head-context-v2'}


class Identity:
    def __init__(self):
        self.model = None
        self.processor = None
        self.model_hash = None

    def load(self):
        with GPU_LOCK:
            if self.model is None:
                self.processor = AutoImageProcessor.from_pretrained(str(IDENTITY_MODEL), local_files_only=True)
                self.model = SiglipVisionModel.from_pretrained(str(IDENTITY_MODEL), local_files_only=True).to(DEVICE).eval()
                self.model_hash = fingerprint(IDENTITY_MODEL / 'model.safetensors')

    def embed(self, image):
        with GPU_LOCK, torch.inference_mode():
            self.load()
            if isinstance(image, np.ndarray):
                image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            image = ImageOps.pad(image.convert('RGB'), (384, 384), color='white')
            inputs = self.processor(images=image, return_tensors='pt').to(DEVICE)
            vector = self.model(**inputs).pooler_output[0].float()
            vector = vector / vector.norm().clamp(min=1e-8)
            return vector.cpu().numpy().tolist()

    def search(self, image, references, site_products=None):
        if not references:
            return {'state': 'UNAVAILABLE', 'candidates': [], 'reason': '등록 사진 없음'}
        vector = np.array(self.embed(image), dtype=np.float32)
        return rank_references(vector, references, self.model_hash, site_products)


identity = Identity()


class Vision:
    def __init__(self, size, release_enabled):
        with GPU_LOCK:
            path = PERSON_MODELS[size]
            self.person = YOLO(str(path)).to(DEVICE)
            if self.person.names.get(0) != 'person':
                raise ValueError('사람 검출 모델의 class 0이 person이 아닙니다.')
            self.pose = YOLO(str(POSE_MODEL)).to(DEVICE)
            self.release = YOLO(str(RELEASE_MODEL)).to(DEVICE) if release_enabled else None
            self.manifest = {
                'person': {'model': path.name, 'sha256': fingerprint(path)},
                'pose': {'model': POSE_MODEL.name, 'sha256': fingerprint(POSE_MODEL)},
                'release': {'model': RELEASE_MODEL.name, 'sha256': fingerprint(RELEASE_MODEL),
                            'native_classes': self.release.names} if self.release else None,
                'device': DEVICE, 'tracker': 'bytetrack.yaml',
            }

    def reset_tracking(self):
        with GPU_LOCK:
            for tracker in getattr(self.person.predictor, 'trackers', []):
                tracker.reset()

    def people(self, frame):
        with GPU_LOCK:
            result = self.person.track(frame, persist=True, tracker='bytetrack.yaml', classes=[0],
                                       imgsz=640, conf=0.15, device=DEVICE, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []
        return [{'track_id': int(track), 'bbox': bounded_box(box, frame.shape[1], frame.shape[0]),
                 'confidence': round(float(score), 4)}
                for box, track, score in zip(boxes.xyxy.cpu().tolist(), boxes.id.cpu().tolist(), boxes.conf.cpu().tolist())]

    def body(self, person):
        if person is None:
            return None
        height, width = person.shape[:2]
        if not observation_size_ok(height, width):
            return None
        body = {'images': {'person': person}, 'boxes': {'person': [0, 0, width, height]},
                'route': 'person_only', 'reason': '몸통 Pose 불충분 · 사람 영상으로 관찰',
                'keypoints': [], 'keypoint_confidence': []}
        if height < 100 or width < 35:
            body.update(route='partial_person_only', reason='작은 부분 영상 · 보이는 부위만 원본 픽셀로 관찰')
            return body
        with GPU_LOCK:
            result = self.pose.predict(person, imgsz=640, conf=0.25, device=DEVICE, verbose=False)[0]
        if result.keypoints is None or len(result.keypoints) == 0:
            return body
        # Associate Pose with the detector crop; an extra helper must not veto all observations.
        boxes = result.boxes.xyxy.cpu().numpy()
        scores = []
        for box in boxes:
            x1, y1, x2, y2 = bounded_box(box, width, height)
            intersection = max(0, x2-x1) * max(0, y2-y1)
            area = max(0, box[2]-box[0]) * max(0, box[3]-box[1])
            scores.append(float(intersection / max(1, width*height + area-intersection)))
        order = np.argsort(scores)[::-1]
        index = int(order[0])
        body['pose_match_scores'] = scores
        if scores[index] < 0.45 or len(order) > 1 and scores[index]-scores[int(order[1])] < 0.15:
            body['reason'] = '몸통 대상 연결 불확실 · 사람 영상으로 관찰'
            return body
        points = result.keypoints.xy[index].cpu().numpy()
        confidence = result.keypoints.conf[index].cpu().numpy()
        body.update(keypoints=points.tolist(), keypoint_confidence=confidence.tolist())
        head_box, head_info = head_region(points, confidence, width, height)
        body['boxes']['head'] = head_box
        body['images']['head'] = crop(person, head_box)
        body['head_region'] = head_info
        body.update(route='pose_head_context', reason='대상 연결 머리/안면 영역과 사람 영상으로 관찰')
        torso_ids = [5, 6, 11, 12]
        if not all(confidence[index] >= 0.4 for index in torso_ids):
            return body
        torso_points = points[torso_ids]
        left, top = torso_points.min(axis=0)
        right, bottom = torso_points.max(axis=0)
        if right - left < 12 or bottom - top < 20:
            return body
        pad_x, pad_y = (right - left) * 0.15, (bottom - top) * 0.1
        boxes = {**body['boxes'],
                 'torso': bounded_box([left-pad_x, top-pad_y, right+pad_x, bottom+pad_y], width, height),
                 'legs': bounded_box([0, max(0, top + (bottom-top)*0.75), width, height], width, height)}
        # Keep torso context for side views; do not change the Decisions detail crops.
        center_x = float((left + right) / 2)
        half_width = max(float((right-left)*0.65), float((bottom-top)*0.35))
        identity_box = bounded_box([center_x-half_width, top-pad_y, center_x+half_width, bottom+pad_y], width, height)
        if identity_box[2]-identity_box[0] >= 35 and identity_box[3]-identity_box[1] >= 60:
            boxes['identity_torso'] = identity_box
        images = {name: crop(person, box) for name, box in boxes.items()}
        body.update(images={key: value for key, value in images.items() if value is not None and value.size},
                    boxes=boxes, route='pose_regions', reason='대상 연결 Pose 영역과 사람 영상으로 관찰')
        return body

    def scene(self, frame, roi):
        height, width = frame.shape[:2]
        box = bounded_box([roi[0]*width, roi[1]*height, roi[2]*width, roi[3]*height], width, height)
        image = crop(frame, box)
        with GPU_LOCK:
            result = self.release.predict(image, imgsz=960, conf=0.25, device=DEVICE, verbose=False)[0]
        return [{'bbox': [float(b[0])+box[0], float(b[1])+box[1], float(b[2])+box[0], float(b[3])+box[1]],
                 'confidence': round(float(score), 4), 'native_class': result.names[int(cls)],
                 'label': '누출'}
                for b, score, cls in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist())]
