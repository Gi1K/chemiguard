# ChemiGuard

화학보호복 착용 관찰과 가시적 연무·분출 의심 장면을 근거와 함께 담당자에게 전달하는 영상 감시 앱.

## 해커톤 본선 구현

2026-10-09, 빈 저장소 확인 이후 사용자의 구현·커밋 요청으로 본선 개발을 시작했습니다. 이 저장소의 커밋 이력을 보존하며 최종 제출까지 사용합니다.

이번 구현: 작업 정책, 제품 참고 사진 등록, 영상 입력, YOLO26 Medium/Large 사람 검출·추적, Pose 부위 crop, Luna Decisions API 착용 관찰, SigLIP2 외형 후보, smoke 장면 분석, 사건 근거, 담당자 확인·반려·보류, 실행 기록.

화학보호복 카탈로그·검색·상담 페이지는 이번 구현 범위에서 제외합니다. 영상만으로 화학물질 종류, 제품 적합성, 안전을 확정하지 않습니다.

## 사전 준비 공개

사전 준비: 감시 PRD·아키텍처·실험 기록, 기존 학습/다운로드 가중치, 선정한 사진·영상, 추적·crop·착용 관찰·외형 검색·시간 합의 설계 지식.

사전 앱은 별도 `ppe-reference-poc` 프로젝트에 있습니다. 본선 앱 소스와 DB는 새로 작성하며, 사전 실험의 성능 수치를 새 앱의 성능으로 표시하지 않습니다. 기존 소스를 참고하거나 일부 재사용한 경우 추가 문서에 기록합니다.

원본 영상·API 키·개인 실행 데이터는 Git 저장소에 포함하지 않습니다. 사전 공개 가중치와 준비 문서는 별도의 `사전 구현 범위/` 아카이브 및 Git LFS 이력으로 관리합니다. 로컬 자산의 경로와 출처, 필요한 의존성 및 실행 방법은 구현과 함께 기록합니다.

FASDD 데이터와 YOLO 가중치별 라이선스·출처·변경 사항은 [데이터 및 가중치 라이선스](docs/DATA_MODEL_LICENSES.md)에 정리했습니다.

상세 범위와 실제 동작 확인 결과는 `docs/`에서 관리합니다. 기존 이력을 삭제하거나 재작성하지 않습니다.

## 로컬 실행

Python 3.11+, Node.js 20+, NVIDIA CUDA 환경을 권장합니다. 현재 개발 장비는 RTX 3090입니다. 인증 없는 로컬 시연용이며 외부 네트워크로 직접 노출하지 않습니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
npm run build
```

`.env.example`에 설정 항목이 있습니다. `OPENAI_API_KEY`는 로컬 환경 또는 Git에서 제외한 `.env`로 제공합니다. 기존 키 파일은 `CHEMIGUARD_ENV_FILE`로 참조할 수 있습니다. 키 값과 경로를 공개 실행 기록에 포함하지 않습니다.

로컬 자산 구성:

```text
CHEMIGUARD_ASSETS_DIR/
  models/person/yolo26l.pt
  models/pose/yolo26n-pose.pt
  models/release/fasdd_smoke_yolo26s.pt
  models/identity/siglip2-base-patch16-384/
CHEMIGUARD_PPE_MEDIA_DIR/  # 착의/다인/작업 원본 영상
CHEMIGUARD_DATA_DIR/models/yolo26m.pt
```

기본 경로는 해커톤 로컬 폴더 배치에 맞춰져 있습니다. 다른 장비에서는 두 자산 경로를 지정하고, 실행 데이터 경로를 생략하면 저장소의 `.data`를 사용합니다. 준비된 보호복 영상이 없어도 화면의 '영상 등록'으로 추가할 수 있습니다. 기존 학습 가중치와 권리 미확인 영상은 자동 다운로드하지 않습니다.

Medium 가중치는 Ultralytics 공식 자산 `https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26m.pt`를 `.data/models/yolo26m.pt`에 준비합니다. 이는 사전학습 모델이며 이 프로젝트에서 새로 학습한 모델이 아닙니다.

```bash
.venv/bin/python -m chemiguard
```

기본 주소: `http://127.0.0.1:8765`. 포트 충돌 시 `CHEMIGUARD_PORT`를 변경합니다. UI 변경 뒤에는 빌드를 다시 실행하고 백엔드 변경 뒤에는 서버를 재시작합니다.

## 관찰과 한계

- 기본 작업 기준은 몸통·양팔·양다리, 후드, 앞 중앙 지퍼/덮개 필수입니다. 가림·불확실·오류는 확인 불가이며 안전 승인과 다릅니다.
- 한 번에 파일 영상 하나를 1배속으로 읽으며 로컬 분석은 최대 약 5Hz입니다. 현재 RTSP/다중 카메라 입력은 없습니다.
- `gpt-6-luna` Decisions 호출은 실제 API 사용량을 발생시킵니다. 키가 없어도 로컬 검출은 작동하지만 착용 관찰은 오류/확인 필요로 남습니다. 입력 crop은 해당 API로 전송됩니다.
- 제품 외형 검색은 등록 사진과의 유사 후보입니다. 제품 정답·인증·화학적 적합성을 확정하지 않습니다.
- smoke 모델은 가시적 연무·분출 후보를 찾는 것이며 보이지 않는 가스나 물질 종류를 판별하지 않습니다.
- `.data`에는 개인 실행 기록, 원본 시점 근거, API 원응답과 검토 기록이 남습니다. 실행 JSON 다운로드는 관측과 검토 메타데이터를 포함하며 이미지 파일은 로컬 경로로 참조합니다. 공개 배포 전 접근 제어와 보관/삭제 정책이 필요합니다.

## 개발 기록

- [작업 지침](AGENTS.md)
- [사전 준비 공개](docs/PREWORK.md)
- [본선 범위와 후속 학습 데이터 아이디어](docs/HACKATHON_SCOPE.md)
- [누적 개선 기록](docs/DEVELOPMENT_LOG.md)
