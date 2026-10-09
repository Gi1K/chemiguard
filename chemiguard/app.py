import io
import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import API_MODEL, ASSETS, DATA, DEVICE, IDENTITY_MODEL, PERSON_MODELS, ROOT, fingerprint
from .monitor import monitor
from .sources import VIDEO_EXTENSIONS, sources
from .store import now, store, uid
from .vision import identity


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    zone_id: str = Field(min_length=1, max_length=100)
    coverall_required: bool = True
    hood_required: bool = False
    closure_required: bool = False
    closure_location: str = Field(default='unknown', max_length=200)
    identity_required: bool = False
    required_product_id: str | None = None
    release_monitoring: bool = True
    scene_roi: list[float] = Field(default=[0, 0, 1, 1], min_length=4, max_length=4)

    @model_validator(mode='after')
    def validate_policy(self):
        if not self.coverall_required and (self.hood_required or self.closure_required or self.identity_required):
            raise ValueError('후드·여밈·제품 확인은 화학복 필수 정책에서 설정해 주세요.')
        x1, y1, x2, y2 = self.scene_roi
        if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
            raise ValueError('감시 영역은 0~1 범위의 유효한 사각형이어야 합니다.')
        if self.closure_required and self.closure_location in ('', 'unknown'):
            raise ValueError('필수 여밈의 위치를 입력해 주세요.')
        if self.identity_required and not self.required_product_id:
            raise ValueError('확인할 등록 제품을 선택해 주세요.')
        return self


class RunInput(BaseModel):
    source_id: str
    policy_id: str
    person_size: Literal['medium', 'large'] = 'large'


class ControlInput(BaseModel):
    action: Literal['pause', 'resume', 'stop', 'seek']
    position: float | None = None


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=80)
    action: Literal['ACKNOWLEDGED', 'DISMISSED', 'DEFERRED']
    note: str = Field(min_length=1, max_length=2000)


class ReferenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    product_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    product_name: str = Field(min_length=1, max_length=150)
    source: str = Field(min_length=1, max_length=1000)
    usage_scope: str = Field(min_length=1, max_length=500)
    view: Literal['front', 'back', 'side', 'other'] = 'front'
    region: Literal['torso'] = 'torso'
    bbox: list[int] = Field(min_length=4, max_length=4)


@asynccontextmanager
async def lifespan(app):
    if not store.list('policy'):
        store.put('policy', PolicyInput(name='화학보호복 기본 관찰', zone_id='시연 구역').model_dump() |
                  {'revision': 1, 'reference_revision': store.revision()})
    yield
    if monitor.busy():
        monitor.active.control('stop')
        monitor.active.thread.join(timeout=10)


app = FastAPI(title='ChemiGuard', lifespan=lifespan)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse(status_code=400, content={'detail': str(exc)})


def public_reference(row):
    return {key: value for key, value in row.items() if key != 'embedding'}


def system_status():
    return {'api_configured': bool(os.getenv('OPENAI_API_KEY', '').strip()), 'api_model': API_MODEL,
            'api_backend': 'Decisions', 'device': DEVICE,
            'gpu_available': torch.cuda.is_available(),
            'gpu_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            'models': {size: path.exists() for size, path in PERSON_MODELS.items()},
            'identity_ready': (IDENTITY_MODEL / 'model.safetensors').is_file(),
            'assets_ready': ASSETS.is_dir(), 'reference_revision': store.revision()}


@app.get('/api/health')
def health():
    return {'status': 'ok', **system_status()}


@app.get('/api/bootstrap')
def bootstrap():
    return {'system': system_status(), 'sources': sources.list(), 'policies': store.list('policy'),
            'references': [public_reference(row) for row in store.list('reference')],
            'active': monitor.active.snapshot() if monitor.active else None}


@app.get('/api/sources')
def list_sources():
    return sources.list()


@app.get('/api/sources/{source_id}/preview')
def source_preview(source_id: str):
    return FileResponse(sources.preview(source_id), media_type='image/jpeg')


@app.get('/api/sources/{source_id}/video')
def source_video(source_id: str):
    return FileResponse(sources.path(source_id))


@app.post('/api/sources')
def upload_source(video: UploadFile = File(...), source: str = Form(...)):
    suffix = Path(video.filename or '').suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(400, 'MP4, MOV, MKV, WEBM, AVI 영상을 선택해 주세요.')
    if not source.strip():
        raise HTTPException(400, '영상 출처를 입력해 주세요.')
    relative = Path('uploads') / (uid('video') + suffix)
    destination = DATA / relative
    size = 0
    try:
        with destination.open('wb') as output:
            for block in iter(lambda: video.file.read(1024*1024), b''):
                size += len(block)
                if size > 512*1024*1024:
                    raise HTTPException(413, '영상은 512MB 이하여야 합니다.')
                output.write(block)
        import cv2
        capture = cv2.VideoCapture(str(destination))
        ok, _ = capture.read()
        capture.release()
        if not ok:
            raise HTTPException(400, '읽을 수 없는 영상입니다.')
        store.put('source', {'name': Path(video.filename).stem[:150], 'source': source.strip()[:1000],
                             'file': str(relative), 'sha256': fingerprint(destination)})
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    sources.refresh()
    return next(row for row in sources.list() if sources.path(row['id']) == destination)


@app.get('/api/policies')
def list_policies():
    return store.list('policy')


@app.post('/api/policies')
def add_policy(payload: PolicyInput):
    if payload.identity_required and not any(row['product_id'] == payload.required_product_id for row in store.list('reference')):
        raise HTTPException(400, '해당 제품의 참고 사진을 먼저 등록해 주세요.')
    existing = [row for row in store.list('policy') if row['name'] == payload.name]
    revision = max([row['revision'] for row in existing], default=0) + 1
    return store.put('policy', payload.model_dump() | {'revision': revision, 'reference_revision': store.revision()})


@app.get('/api/references')
def list_references():
    return [public_reference(row) for row in store.list('reference')]


@app.post('/api/references')
def add_reference(image: UploadFile = File(...), metadata: str = Form(...)):
    if monitor.busy():
        raise HTTPException(409, '사진 등록은 영상 실행을 중지한 뒤 진행해 주세요.')
    try:
        meta = ReferenceInput.model_validate_json(metadata)
    except ValueError as exc:
        raise HTTPException(400, '사진 등록 정보가 올바르지 않습니다: ' + str(exc)[:250])
    content = image.file.read(10*1024*1024+1)
    if len(content) > 10*1024*1024:
        raise HTTPException(413, '사진은 10MB 이하여야 합니다.')
    try:
        original = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(400, '읽을 수 없는 사진입니다.')
    x1, y1, x2, y2 = meta.bbox
    if not 0 <= x1 < x2 <= original.width or not 0 <= y1 < y2 <= original.height or min(x2-x1, y2-y1) < 20:
        raise HTTPException(400, '사진 안에서 20px 이상의 몸통 영역을 지정해 주세요.')
    crop = original.crop(meta.bbox)
    vector = identity.embed(crop)
    reference_id = uid('reference')
    folder = DATA / 'references' / reference_id
    folder.mkdir()
    original.save(folder / 'original.jpg', quality=92)
    crop.save(folder / 'torso.jpg', quality=92)
    return public_reference(store.put('reference', meta.model_dump() | {
        'id': reference_id, 'revision': store.revision()+1, 'embedding': vector,
        'model_sha256': identity.model_hash, 'model': 'siglip2-base-patch16-384',
        'preprocessing': 'RGB white-pad 384 L2-normalized',
        'original_url': f'/media/references/{reference_id}/original.jpg',
        'crop_url': f'/media/references/{reference_id}/torso.jpg',
        'image_sha256': fingerprint(folder / 'original.jpg')}))


@app.post('/api/runs')
def start_run(payload: RunInput):
    sources.path(payload.source_id)
    policy = store.get('policy', payload.policy_id)
    if not policy:
        raise HTTPException(404, '정책을 찾을 수 없습니다.')
    if policy['reference_revision'] != store.revision():
        raise HTTPException(409, '등록 사진이 변경되었습니다. 정책을 새 버전으로 저장해 주세요.')
    return monitor.start(payload.source_id, policy, payload.person_size)


@app.get('/api/runs/active')
def active_run():
    return monitor.active.snapshot() if monitor.active else None


@app.get('/api/runs')
def list_runs():
    return store.list('run', 100)


@app.get('/api/runs/{run_id}')
def get_run(run_id: str):
    if monitor.active and monitor.active.id == run_id:
        return monitor.active.snapshot()
    record = store.get('run', run_id)
    if not record:
        raise HTTPException(404, '실행을 찾을 수 없습니다.')
    return record


@app.post('/api/runs/{run_id}/control')
def control_run(run_id: str, payload: ControlInput):
    if not monitor.active or monitor.active.id != run_id:
        raise HTTPException(404, '현재 실행을 찾을 수 없습니다.')
    return monitor.active.control(payload.action, payload.position)


@app.get('/api/runs/{run_id}/frame')
def run_frame(run_id: str, generation: int, seq: int):
    if not monitor.active or monitor.active.id != run_id:
        raise HTTPException(404, '현재 실행을 찾을 수 없습니다.')
    data = monitor.active.frame(generation, seq)
    if data is None:
        raise HTTPException(404, '프레임이 갱신되었습니다.')
    return Response(data, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=60'})


@app.get('/api/runs/{run_id}/export')
def export_run(run_id: str):
    if monitor.active and monitor.active.id == run_id:
        monitor.active._save()
    record = store.get('run', run_id)
    if not record:
        raise HTTPException(404, '실행을 찾을 수 없습니다.')
    events = [row for row in list_events() if row['run_id'] == run_id]
    return JSONResponse({'run': record, 'events': events}, headers={
        'Content-Disposition': f'attachment; filename="{run_id}.json"'})


@app.get('/api/events')
def list_events(run_id: str | None = None):
    reviews = store.list('review', 5000)
    rows = store.list('event', 500)
    if run_id:
        rows = [row for row in rows if row['run_id'] == run_id]
    for row in rows:
        related = [review for review in reviews if review['event_id'] == row['id']]
        row['review_status'] = related[0]['action'] if related else 'OPEN'
        row['review_count'] = len(related)
    return rows


@app.get('/api/events/{event_id}')
def event_detail(event_id: str):
    event = store.get('event', event_id)
    if not event:
        raise HTTPException(404, '사건을 찾을 수 없습니다.')
    return {'event': event, 'observation': store.get('observation', event['observation_id']),
            'reviews': [row for row in store.list('review', 5000) if row['event_id'] == event_id],
            'run': store.get('run', event['run_id'])}


@app.post('/api/events/{event_id}/reviews')
def add_review(event_id: str, payload: ReviewInput):
    if not store.get('event', event_id):
        raise HTTPException(404, '사건을 찾을 수 없습니다.')
    return store.put('review', payload.model_dump() | {'event_id': event_id})


@app.get('/api/events/{event_id}/export')
def export_event(event_id: str):
    return JSONResponse(event_detail(event_id), headers={
        'Content-Disposition': f'attachment; filename="{event_id}.json"'})


app.mount('/media/references', StaticFiles(directory=DATA / 'references'), name='reference-media')
app.mount('/media/runs', StaticFiles(directory=DATA / 'runs'), name='run-media')

if (ROOT / 'dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='dashboard')
else:
    @app.get('/')
    def build_needed():
        return JSONResponse({'message': 'Run npm install && npm run build, then restart the server.'}, status_code=503)
