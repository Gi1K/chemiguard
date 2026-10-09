import threading

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps
from transformers import AutoImageProcessor, SiglipVisionModel
from ultralytics import YOLO

from .config import DEVICE, IDENTITY_MODEL, PERSON_MODELS, POSE_MODEL, RELEASE_MODEL, fingerprint

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

    def search(self, image, references):
        if not references:
            return {'state': 'UNAVAILABLE', 'candidates': [], 'reason': '등록 사진 없음'}
        vector = np.array(self.embed(image), dtype=np.float32)
        products = {}
        for reference in references:
            if reference['model_sha256'] != self.model_hash or reference['region'] != 'torso':
                continue
            score = float(np.dot(vector, np.array(reference['embedding'], dtype=np.float32)))
            product = products.setdefault(reference['product_id'], {
                'product_id': reference['product_id'], 'name': reference['product_name'], 'scores': [],
                'reference_url': reference['crop_url'], 'reference_count': 0})
            product['scores'].append(score)
            product['reference_count'] += 1
        candidates = []
        for product in products.values():
            product['score'] = float(np.mean(sorted(product.pop('scores'), reverse=True)[:2]))
            candidates.append(product)
        candidates.sort(key=lambda row: row['score'], reverse=True)
        return {'state': 'CANDIDATE' if candidates else 'UNAVAILABLE', 'candidates': candidates[:3],
                'gap': candidates[0]['score'] - candidates[1]['score'] if len(candidates) > 1 else None,
                'reason': '외형 참고 후보 · 제품 미확정'}


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
        height, width = person.shape[:2]
        if height < 100 or width < 35:
            return None
        with GPU_LOCK:
            result = self.pose.predict(person, imgsz=640, conf=0.25, device=DEVICE, verbose=False)[0]
        if result.keypoints is None or len(result.keypoints) == 0:
            return None
        # Multiple people in a crop are ambiguous; do not attach a helper's limbs to the target.
        if len(result.keypoints) != 1:
            return None
        points = result.keypoints.xy[0].cpu().numpy()
        confidence = result.keypoints.conf[0].cpu().numpy()
        torso_ids = [5, 6, 11, 12]
        if not all(confidence[index] >= 0.4 for index in torso_ids):
            return None
        torso_points = points[torso_ids]
        left, top = torso_points.min(axis=0)
        right, bottom = torso_points.max(axis=0)
        if right - left < 12 or bottom - top < 20:
            return None
        pad_x, pad_y = (right - left) * 0.15, (bottom - top) * 0.1
        boxes = {'person': [0, 0, width, height],
                 'torso': bounded_box([left-pad_x, top-pad_y, right+pad_x, bottom+pad_y], width, height),
                 'legs': bounded_box([0, max(0, top + (bottom-top)*0.75), width, height], width, height),
                 'head': bounded_box([0, 0, width, min(height, top+pad_y)], width, height)}
        images = {name: crop(person, box) for name, box in boxes.items()}
        return {'images': {key: value for key, value in images.items() if value is not None and value.size},
                'boxes': boxes, 'keypoints': points.tolist(), 'keypoint_confidence': confidence.tolist()}

    def scene(self, frame, roi):
        height, width = frame.shape[:2]
        box = bounded_box([roi[0]*width, roi[1]*height, roi[2]*width, roi[3]*height], width, height)
        image = crop(frame, box)
        with GPU_LOCK:
            result = self.release.predict(image, imgsz=960, conf=0.25, device=DEVICE, verbose=False)[0]
        return [{'bbox': [float(b[0])+box[0], float(b[1])+box[1], float(b[2])+box[0], float(b[3])+box[1]],
                 'confidence': round(float(score), 4), 'native_class': result.names[int(cls)],
                 'label': '가시적 연무·분출 의심'}
                for b, score, cls in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist())]
