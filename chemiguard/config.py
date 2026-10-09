import hashlib
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
if os.getenv('CHEMIGUARD_ENV_FILE'):
    load_dotenv(os.environ['CHEMIGUARD_ENV_FILE'])

ASSETS = Path(os.getenv('CHEMIGUARD_ASSETS_DIR') or ROOT.parents[1] / '사전 구현 범위/01_가중치_영상').resolve()
PPE_MEDIA = Path(os.getenv('CHEMIGUARD_PPE_MEDIA_DIR') or ROOT.parents[2] / 'ppe-reference-poc/demo/adaptive-ppe/video').resolve()
DATA = Path(os.getenv('CHEMIGUARD_DATA_DIR') or ROOT / '.data').resolve()
for directory in ('references', 'uploads', 'runs', 'models', 'previews'):
    (DATA / directory).mkdir(parents=True, exist_ok=True)

DEVICE = os.getenv('CHEMIGUARD_DEVICE', 'cuda:0')
API_MODEL = 'gpt-6-luna'
API_ENDPOINT = 'https://api.openai.com/v1/decisions'
PERSON_MODELS = {
    'large': ASSETS / 'models/person/yolo26l.pt',
    'medium': DATA / 'models/yolo26m.pt',
}
POSE_MODEL = ASSETS / 'models/pose/yolo26n-pose.pt'
RELEASE_MODEL = ASSETS / 'models/release/fasdd_smoke_yolo26s.pt'
IDENTITY_MODEL = ASSETS / 'models/identity/siglip2-base-patch16-384'


@lru_cache(maxsize=64)
def file_hash(path: str, size: int, mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(path: Path) -> str:
    stat = path.stat()
    return file_hash(str(path), stat.st_size, stat.st_mtime_ns)
