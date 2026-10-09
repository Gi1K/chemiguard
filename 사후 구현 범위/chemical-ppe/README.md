# ChemiGuard 화학보호구 홈페이지 — 사후 구현

2026-10-09 본선 구현. 기존 카탈로그·조합 기능을 근거로 홈페이지와 상담 연결을 작성했다. 기본 연결은 **OpenAI Agents API + gpt-6-luna**이며 Sol·Luna 모두 실제 구조화 응답과 세션 정리를 확인했다. 공개 HTTPS 배포는 아직 진행하지 않았다.

## 실행

Node.js 20 이상, Python 3.12 기준. 저장소 전체를 복제해야 사전 원본을 읽을 수 있다. 이 앱은 모델 가중치·영상 파일을 사용하지 않는다.

```bash
cd '사후 구현 범위/chemical-ppe'
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
cp .env.example .env  # 최초 한 번만; 기존 설정을 덮어쓰지 않는다
bash run.sh
```

화면: `http://127.0.0.1:34402/kit-catalog/`. API 키 없이 검색·필터·수동 조합·초안 저장/복원·JSON 내보내기를 사용할 수 있다. 상담은 설정 대기로 표시한다. `.env`는 `run.sh`가 읽는 셸 환경 파일이므로 공백이 포함된 값은 따옴표로 감싼다.

`.env`에 `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-6-luna`, 16자 이상의 임의 `PPE_DEMO_TOKEN`을 설정하고 서버를 재시작한다. `PPE_BACKEND=agents`가 기본이다. 모델은 `gpt-6-sol`로 바꿀 수 있다. 시연 참여자에게는 `PPE_DEMO_TOKEN`만 전달하고, 화면의 **상담 접근 설정**에서 입력한다. 모델 키는 화면에 입력하지 않는다. 개인 Codex 인증으로 우회하지 않는다.

키에는 `api.agents.read`, `api.agents.write`, `api.responses.write` 권한이 필요하다. 기존 직접 Responses 연결은 `PPE_BACKEND=responses`로 명시할 때만 사용하며, Agents 실패 후 자동 전환하거나 유료 재시도하지 않는다.

## 사전·사후 경계

| 구분 | 실제 사용 |
| --- | --- |
| 사전 원본 | [기존 페이지](../../사전%20구현%20범위/04_화학보호복_기존페이지/README.md)에 8개 원본 보존. PRD SHA256과 모두 일치 |
| 사전 화면 로직 | 기존 `app.js`의 공통 함수·조합·초안·초기화를 사후 `core.js`, `drafts.js`, `bootstrap.js`로 나눠 정리. 기존 `style.css`는 빌드에서 읽어 사용. 검색·조합·색상 비교·초안 기능은 사전 성과 |
| 사전 데이터 | 44개 제품·150개 출처 JSON. 공개 빌드에서 로컬 경로와 이미지 URL을 제거 |
| 사전 상담 지식 | 원본 `CatalogChat.instructions/output_schema`와 `chemical_live_lookup.lookup_chemicals` 재사용. 원본 서버 초기화·CodexClient 실행은 없음 |
| 사후 화면 | `web/index.html`은 기존 DOM 계약을 바탕으로 다시 구성. `catalog.js`는 사진 중심 카드·카테고리·상세·확대·최대 3개 비교, `counselor.js`는 API 접근·오류·시험 원문 표시. `public.css`, `catalog.css`는 새 화면과 모바일 스타일 |
| 사후 API | `server.py`, `agents_backend.py`: CAS 계획 → 기존 제조사 조회 → 조합. 요청당 최대 2개의 Agents 세션 또는 Responses 요청, 임시 대화, 응답 검증, 접근·호출 제한 |
| 사후 배포 | `build.mjs`, Vercel 설정, 서버 실행/HTTPS 프록시 예시. `dist/`는 생성물이며 커밋하지 않음 |

기존 화면과 기능을 새로 개발한 것으로 세지 않는다. 빌드는 기준선 해시가 하나라도 바뀌면 중단한다. 원본은 사전 폴더에 보존하고, 분리·정리·개선한 파일은 사후 폴더에 둔다. 원래 사진의 모델 일치/대표사진 상태와 실제 판매 색상 메타데이터는 보존한다.

## 사진 표시

기존 사진 44개는 `allow_local_preview=true`, `allow_redistribution=false`인 자료다. 기존 원본이 있는 PC에서는 `.env`의 `PPE_LOCAL_PHOTOS_DIR`에 원본 `kit-catalog` 폴더의 절대 경로를 지정한다. 이 폴더 아래 `assets`의 등록된 파일만 읽는다. 사진을 저장소나 `dist`로 복사하지 않는다.

서버와 같은 PC에서 `http://127.0.0.1:34402` 또는 `http://localhost:34402`로 직접 접속할 때만 사진을 표시한다. 외부 호스트·프록시 전달 요청은 사진에 접근할 수 없다. 사진은 원래 비율을 유지하고, 상세 화면에서 확대할 수 있다. 저해상도 원본을 확대해도 해상도가 높아지지는 않는다. 제품군 대표사진은 정확 모델 사진과 구분해 표시한다.

공개 배포에는 재배포 권한이 확인되지 않은 사진을 포함하지 않는다. 공개 화면은 품목 도식과 원본 출처 링크를 표시한다. 도식은 실제 제품 사진이 아니다. 공개 사진은 별도 권한 확인 후 추가하는 후속 범위다.

## 요청과 제한

- `GET /api/ppe/status`: 상담 준비 상태와 허용된 로컬 사진 목록. 키·시연 코드 값은 반환하지 않는다.
- `GET /api/ppe/local-media/{product_id}`: 위 로컬 조건을 만족한 등록 사진만 반환.
- `POST /api/ppe/chat`: `Authorization: Bearer <시연 코드>`와 JSON. `message`, `session_id`, `auto_kit_options`, `existing_kits`를 받는다.
- 브라우저 Origin이 있으면 허용 목록과 대조하고, 모든 요청의 시연 코드를 확인한다. Origin은 인증 대용이 아니다. 입력 최대 32KB, 메시지 6000자.
- 한 번에 상담 1건, 기본 분당 4건/UTC 일당 30건, 일일 예약 토큰 150만. 입력 UTF-8 바이트 수와 출력 예상량을 예약하며 실패해도 환급하지 않는다. 실제 청구 토큰/금액의 측정치나 엄격한 비용 상한은 아니다.
- `PPE_MAX_OUTPUT_TOKENS=5000`은 Responses 모드의 출력 상한이다. Agents API에는 동일 필드가 없으므로 Agents 모드에서는 예약량 산정에만 쓴다. 요청당 최대 2개 세션·145초 처리 제한·자동 재시도 없음·실패 시 취소/삭제를 적용한다. 원격 작업 정리에 최대 약 20초가 추가될 수 있다.
- Agents 세션은 sandbox·추가 도구·하위 에이전트를 사용하지 않는다. 현재 계정에서는 `spend_control` 요청에 `Session budget configuration is not enabled`가 반환되어 `PPE_AGENT_BUDGET_ENABLED=false`로 둔다. 이 상태에서 금액 상한이 적용된다고 주장하지 않는다. 계정에서 지원이 활성화된 뒤 true로 설정하면 세션당 50센트·일일 예약 500센트 기본값을 사용한다. 이 옵션을 거절해도 자동으로 제한을 제거해 재시도하지 않는다.
- `.runtime/usage.sqlite3`는 요청/토큰 **숫자만** 저장한다. 회사 DB나 초안 저장소가 아니며 재시작 후에도 제한을 유지한다. 서버 디스크에 이 경로를 보존한다.
- `touch .runtime/STOP`으로 새 유료 호출을 중지한다. 진행 중인 호출을 취소하거나 환불하지는 않는다. 다시 열 때 해당 STOP 파일을 제거한다. `PPE_CHAT_ENABLED=false`도 지원한다.
- 대화는 앱 프로세스 메모리에 최대 24개·각 6회 상담. 2시간 뒤 만료하고 다음 요청에서 정리한다. 서버 재시작 시 410과 함께 전체 작업 조건 재입력을 안내한다. Agents는 각 단계의 외부 세션을 종료 후 삭제하고, 미완료 작업은 취소 후 삭제한다. 정리 전 ID만 `.runtime/pending-agent-sessions.json`에 보관하고 다음 요청에서 재정리하며, 정리 실패 시 새 상담을 중단한다. API에서 삭제한 뒤 실제 저장소 정리는 비동기일 수 있다. Responses 모드는 `store:false`로 호출한다.
- API 오류에 원문 예외·키·입력을 포함하지 않는다. 자동 유료 재시도는 없다. 미등록 제품/출처, 미조회 원문, 제외 제품 포함 조합, 중복 기본 품목, 표시 형식 불일치는 반환하지 않는다.
- 시험 행의 CAS/농도/온도/원문 값/시험 주석/조회 시각/개정 및 matched/not_found/error를 보존한다. 모든 결과는 검토 후보이며 승인·감지 등록·합성 생성 플래그는 false다.

## Vercel + 별도 HTTPS API

1. API 서버에 전체 저장소를 배치하고 위 실행 방법으로 단일 프로세스를 실행한다. `deploy/Caddyfile.example`을 실제 도메인으로 수정해 TLS 프록시를 연결한다. Python API는 loopback에서 실행한다.
2. Vercel에서 이 저장소를 연결한다. Root Directory: `사후 구현 범위/chemical-ppe`, Framework: Other, Build: `npm run build`, Output: `dist`.
3. 사전 원본 읽기를 위해 **Include source files outside of the Root Directory in the Build Step**을 켠다. 사전 원본 변경도 빌드 대상에 포함되도록 변경 없는 배포 자동 생략 설정을 확인한다.
4. Vercel의 빌드 환경변수에는 `PUBLIC_API_BASE=https://실제-API-호스트`만 지정한다. 키·시연 코드는 Python 서버에만 둔다.
5. 서버 `PPE_ALLOWED_ORIGINS`에 실제 Vercel 공개 주소를 정확히 지정하고 재시작한다. 임의 `*.vercel.app` 허용은 하지 않는다. `PUBLIC_API_BASE`가 비면 동일 출처 API를 사용하므로 정적 Vercel만 배포할 때는 반드시 지정해야 한다.
6. 공개 기기에서 상담 1사례 → 후속 질문 → 근거 → 조합 → 초안/JSON을 확인한다. 현재 공개 호스트 배포와 공개 환경 검증은 대기다.

Vercel에 올라가는 것은 `dist/`의 공개 파일뿐이다. Python API·환경 파일·PRD·원본 아카이브·사진·연구 자료는 정적 배포 결과에 없다. 서버는 단일 worker 구성을 따른다. 수평 확장은 대화 저장/잠금 설계 변경 후 별도로 검토한다.

## 최소 검증

```bash
npm run build
for file in dist/kit-catalog/*.js; do node --check "$file"; done
.venv/bin/python check_contract.py
```

`check_contract.py`는 외부 API와 제조사 조회를 메모리에서 모의 처리한다. 실제 Agents SDK의 이벤트 파싱·미완료 스트림 거부·취소/삭제도 오프라인으로 검사한다. 실제 모델 품질 검증을 대신하지 않는다. 실행 결과와 PRD 완료 상태는 [구현 기록](IMPLEMENTATION.md)에 구분했다.

기술 참조: [Agents API 시작](https://developers.openai.com/api/docs/guides/agents-api/quickstart), [세션 설정](https://developers.openai.com/api/reference/resources/beta/subresources/agents/subresources/sessions/methods/create), [세션 정리](https://developers.openai.com/api/docs/guides/agents-api/sessions/manage), [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [Sol](https://developers.openai.com/api/docs/models/gpt-6-sol), [Responses 구조화 출력](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [Vercel 원본 경로 설정](https://vercel.com/docs/monorepos/monorepo-faq).
