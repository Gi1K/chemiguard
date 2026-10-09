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
| 사후 제품 관리 | `catalog_store.py`, `catalog_sources.py`, `catalog_admin.py`, `web/catalog-sync.js`: 영속 제품 DB, 공식 출처 검증·중복 방지·변경 이력, 일일 관리 자동화와 홈페이지 갱신 |
| 사후 배포 | `build.mjs`, Vercel 설정, 서버 실행/HTTPS 프록시 예시. `dist/`는 생성물이며 커밋하지 않음 |

기존 화면과 기능을 새로 개발한 것으로 세지 않는다. 빌드는 기준선 해시가 하나라도 바뀌면 중단한다. 원본은 사전 폴더에 보존하고, 분리·정리·개선한 파일은 사후 폴더에 둔다. 원래 사진의 모델 일치/대표사진 상태와 실제 판매 색상 메타데이터는 보존한다.

## 제품 DB와 매일 자동 확인

홈페이지는 `.runtime/catalog.sqlite3`를 사용한다. 최초 실행 때 기존 44개 제품·150개 출처를 한 번 이관하며, 원본 JSON은 변경하지 않는다. 카탈로그 화면·비교·선택 목록과 상담은 같은 DB를 읽는다. 새 제품이 반영되면 활성 화면이 최대 60초 안에 갱신하며, 열린 상세 창이나 진행 중인 상담은 다음 확인 때 갱신한다. 서버에 연결하지 못하면 기본 44개 목록으로 돌아가고 화면에 상태를 표시한다.

현재 작업 PC에는 **한국 시간 매일 오전 9시**에 이 대화의 Codex 관리 자동화가 공식 제조사 자료를 확인하도록 등록했다. 홈페이지 상담은 기존 Luna Agents API를 사용하고, 관리 자동화는 Codex가 실행한다. **서버 PC와 Codex 앱이 켜져 있어야 정기 확인이 실행된다.** 저장소 복제만으로 다른 PC에 일정이 설치되지는 않는다. 홈페이지의 `제품 자동 업데이트`에는 등록 일정, 최근 확인 시각, 추가·갱신 건수와 실제 수집에 성공한 공식 페이지 수·제조사만 표시한다. 실패 출처와 HTTP 오류는 관리 DB/CLI/API 이력에 보존하고 화면에서 제외한다. 수집 성공이 없으면 새 수집 자료가 없다고 안내한다.

공식 본문에서 이름·정확 모델·품목을 확인한 제품만 기본 정보로 추가한다. 새로 발견한 제품은 `성능 검토 전`이며 자동 추천·조합에서는 제외한다. 수동 비교·초안 선택은 가능하다. 출시일·인증·시험 성능·국내 재고·이미지 권한을 추정하지 않는다. 신규 사진은 공식 출처 링크로 확인한다.

현재 첫 수집에서 DuPont QS127T GR을 추가해 운영 DB는 45개 제품·151개 출처다. 이는 최근 출시가 확인되었다는 뜻이 아니다. 일부 제조사의 HTTP 403은 실패로 기록했다. 정적 `catalog-data.json`은 기본 자료이며, 화면의 제품·출처 링크는 DB 연결 시 최신 API로 연결한다.

관리 절차, 검색 대상과 한계는 [CATALOG_MAINTENANCE.md](CATALOG_MAINTENANCE.md)에 있다. `.venv/bin/python catalog_admin.py status`로 현재 상태를 확인한다. 쓰기는 로컬 CLI로만 수행하며 외부 쓰기 API는 제공하지 않는다. DB·수집 결과는 Git 제외다. 장기 운영을 위한 별도 서버 스케줄러, 백업과 성능 검토·승인 기능은 후속 범위다.

### 수집 자료 별도 조회

`/kit-catalog/collection.html`에서 자동 수집 제품과 최근 실행에서 수집에 성공한 공식 출처를 조회한다. 홈페이지 상단의 **수집 현황** 또는 제품 자동 업데이트의 **수집된 제품·출처 조회**로 이동한다. 기존 44개 사전 제품은 원래 전체 제품 화면에서 조회한다.

제품명·모델·출처 검색, 제조사 필터, 수집 제품/확인한 출처 보기, 최초 발견·최근 확인 시각, 공식 원문 링크를 제공한다. 검색어·제조사·보기는 주소에 보존해 같은 조건으로 다시 열 수 있다. 목록은 20개 단위로 표시한다. `최신 목록 불러오기`와 활성 화면의 1분 갱신은 저장된 DB를 읽기만 하며 수집·모델 호출을 실행하지 않는다. 출처 탭은 최근 실행에서 성공한 자료이며 전체 과거 실행 이력은 아니다. API 연결 실패 때는 오류를 안내하고 이미 조회한 자료가 있으면 유지한다.

## 사진 표시

기존 사진 44개는 `allow_local_preview=true`, `allow_redistribution=false`인 자료다. 기존 원본이 있는 PC에서는 `.env`의 `PPE_LOCAL_PHOTOS_DIR`에 원본 `kit-catalog` 폴더의 절대 경로를 지정한다. 이 폴더 아래 `assets`의 등록된 파일만 읽는다. 사진을 저장소나 `dist`로 복사하지 않는다.

기본적으로 서버와 같은 PC에서 `http://127.0.0.1:34402` 또는 `http://localhost:34402`로 직접 접속할 때 사진을 표시한다. 비공개 원격 미리보기는 아래 Tailscale 설정으로 허용한다. 공개 터널의 제품 사진은 아래 명시적 설정으로 켠다. 사진은 원래 비율을 유지하고, 상세 화면에서 확대할 수 있다. 저해상도 원본을 확대해도 해상도가 높아지지는 않는다. 제품군 대표사진은 정확 모델 사진과 구분해 표시한다.

2026-10-09 사용자가 공개 홈페이지에서도 기존 제품 사진을 모두 표시하도록 지시했다. 현재 서버의 `.env`에 `PPE_PUBLIC_CATALOG_PHOTOS=true`를 설정하면 고정 Host `public-preview.invalid`로 들어오는 공개 터널에서 등록된 기존 사진을 표시한다. 기본값은 false다. 등록되지 않은 파일·상담 첨부·개인 실행 근거는 제공하지 않는다. 원본과 사전 권한 메타데이터를 바꾸거나 Git/정적 배포 파일에 사진을 넣지 않는다. 사용자 요청에 따른 표시 설정이며 새 라이선스를 확보했다는 의미는 아니다. 연결된 사진이 없는 신규 수집 제품은 도식과 공식 출처 링크를 표시한다.

## Tailscale 비공개 원격 접속

### SSH 터널로 접속 (sudo 불필요)

서버에서 SSH 로그인이 가능한 계정으로 연결한다. Tailscale IP를 사용하면 서버와 접속 기기 모두 Tailscale에 연결되어 있어야 한다. **아래 명령은 페이지를 볼 맥/PC의 터미널에서 실행한다.** 이미 서버에 SSH로 접속한 셸 안에서 실행하지 않는다. `your-user@your-server`는 실제 서버 계정과 Tailscale IP 또는 SSH 호스트로 바꾼다.

```bash
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:34402:127.0.0.1:34402 your-user@your-server
```

인증한 뒤 터미널이 아무 출력 없이 대기하면 연결이 유지되는 정상 상태다. 같은 맥/PC의 브라우저에서 `http://127.0.0.1:34402/kit-catalog/`를 연다. `Ctrl+C`로 터널을 종료할 수 있다. 사진·API 요청은 이 터널을 함께 통과하며 기존 로컬 Origin과 사진 접근 조건을 만족한다. 상담은 기존 시연 코드가 필요하다. SSH 터널 자체에는 Tailscale Serve 설정이나 sudo가 필요 없다.

`Address already in use`라면 접속 기기의 34402 포트가 사용 중이다. 자신이 띄운 기존 터널이면 해당 터미널에서 종료하고 다시 연결한다. 임의로 다른 프로세스를 종료하지 않는다. 다른 로컬 포트를 사용할 경우에는 서버 `PPE_ALLOWED_ORIGINS`에도 그 로컬 주소를 추가해야 상담이 동작한다. SSH 로그인 실패는 서버 계정/키/암호 문제이며 홈페이지 API 키와 별개다.

### Tailscale Serve HTTPS 접속

서버 PC와 접속 기기에서 Tailscale을 켠다. 서버의 `tailscale status --json`에서 확인한 DNS 이름을 사용해 `.env`에 다음 항목을 설정한다. 기존 API 키는 유지한다.

```dotenv
PPE_TAILSCALE_ORIGIN=https://your-device.your-tailnet.ts.net:9443
PPE_TAILSCALE_USER_LOGIN=your-tailscale-login
PPE_ALLOWED_ORIGINS=http://127.0.0.1:34402,http://localhost:34402,https://your-device.your-tailnet.ts.net:9443
```

`bash run.sh`로 재시작한 뒤, 다른 터미널에서 다음 명령을 실행한다. Tailscale 운영자 권한이 없는 경우 `sudo`를 붙여 PC 관리자가 실행한다. 기존 Serve/Funnel 설정을 초기화하지 않고 사용하지 않는 전용 포트에만 추가한다.

```bash
tailscale serve --bg --https=9443 http://127.0.0.1:34402
tailscale serve status
```

접속 주소는 `https://your-device.your-tailnet.ts.net:9443/kit-catalog/`다. 화면과 API가 같은 출처이므로 `PUBLIC_API_BASE`는 비워 둔다. 상담 시연 코드는 이 주소의 **상담 접근 설정**에도 입력한다. 브라우저의 초안·설정은 주소별로 저장되므로 기존 로컬 주소와 자동 공유되지 않는다.

사진은 정확한 Host와 허용한 `Tailscale-User-Login`이 모두 일치하고 실제 프록시 연결이 loopback일 때만 표시한다. `run.sh`는 Tailscale 사진 설정 시 `127.0.0.1` 바인딩을 강제하고, 전달 헤더로 접속 IP를 바꾸는 동작을 끈다. 수동으로 서버를 띄워도 `--host 127.0.0.1 --no-proxy-headers`를 유지해야 한다. [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)는 클라이언트가 보낸 신원 헤더를 제거하고 실제 사용자 신원을 붙인다. 태그된 기기는 사용자 신원이 없어 사진을 표시하지 않는다. 공개 Funnel로 전환하지 않는다.

이 연결만 끄려면 `tailscale serve --https=9443 off`를 사용한다. Serve는 백그라운드 설정을 유지하지만 앱 서버는 별도로 실행 중이어야 한다.

### 서버 지속 실행

Linux 서버에서는 `deploy/chemiguard-catalog.service.example`을 `~/.config/systemd/user/chemiguard-catalog.service`로 복사하고 `WorkingDirectory`를 이 앱의 절대 경로로 수정한다. 기존 수동 실행 서버가 있으면 해당 프로세스만 종료한 후 아래 명령으로 시작한다. 서비스도 동일한 `run.sh`와 로컬 `.env`를 사용한다.

```bash
systemctl --user daemon-reload
systemctl --user enable --now chemiguard-catalog.service
systemctl --user status chemiguard-catalog.service --no-pager
```

설정 변경 후에는 `systemctl --user restart chemiguard-catalog.service`, 중지하려면 `systemctl --user stop chemiguard-catalog.service`를 쓴다. SSH 접속 종료 후나 PC 부팅 때도 실행하려면 해당 서버 계정의 `loginctl show-user "$USER" -p Linger`가 `Linger=yes`여야 한다. 현재 작업 PC는 이미 활성화되어 있어 시스템 권한 설정을 변경하지 않았다. 원격 기기의 SSH 터널은 별개이므로 접속할 때 다시 실행한다.

## 요청과 제한

### 처음 사용하는 사람의 상담 흐름

`처음이라면 상담부터` → `처음이라 잘 모르겠어요` → 보내기로 시작한다. 한 번에 질문 하나를 받으며, 제품명·성분을 모르면 라벨 사진을 첨부할 수 있는지 묻는다. 사진이 없으면 라벨의 글자나 담당자에게 요청하는 문장으로 안내한다.

`사진 첨부`에서 JPG·PNG·WebP를 최대 2장 선택한다. 브라우저 선택 한도는 장당 10MB이며 긴 변 2048px, JPEG 700KB 이하로 줄인다. 글 없이 사진만 보낼 수 있고 전송 전 미리보기·제거가 가능하다. HEIC는 JPG로 변환해야 한다.

사진 요청은 Luna 이미지 입력으로 라벨 글자만 읽는 세션 1개를 사용한다. 읽은 내용과 불확실한 부분을 표시하고, 사용자가 수정 후 `이 내용으로 상담하기`를 눌렀을 때 확인한 텍스트로 기존 물질 조회·상담을 진행한다. 확인 전에는 후보나 조합을 생성하지 않고 대화 이력에 판독 내용을 넣지 않는다. 흐리거나 라벨이 아닌 사진은 재촬영을 안내한다. 사진만으로 성분·적합성·착용 가능 시간을 확정하지 않는다.

전송 시 사진은 OpenAI로 전달된다. 앱 서버는 허용한 data URL의 실제 이미지 형식·바이트·픽셀 수를 검사하고 메타데이터를 제거해 메모리에서만 처리한다. 원본·변환 사진을 파일이나 대화 저장소에 보관하지 않는다. 임시 판독 텍스트는 대화 메모리에 보관하며, 확인한 텍스트는 이후 대화 맥락에 포함된다. 브라우저 사진 미리보기도 새 대화·새로고침 시 사라진다. 외부 Agents 세션은 아래 정리 정책을 따른다.

### API와 운영 제한

- `GET /api/ppe/status`: 상담 준비 상태와 허용된 로컬 사진 목록. 키·시연 코드 값은 반환하지 않는다.
- `GET /api/ppe/catalog`: 로컬 경로·비공개 사진 정보를 제거한 최신 제품·출처 목록. `GET /api/ppe/catalog/status`: 최근 수집 결과와 등록 일정. 두 응답 모두 캐시하지 않는다.
- `GET /api/ppe/local-media/{product_id}`: 위 로컬 조건을 만족한 등록 사진만 반환.
- `POST /api/ppe/chat`: `Authorization: Bearer <시연 코드>`와 JSON. `message`, `session_id`, `auto_kit_options`, `existing_kits`, 선택적 `photos`(data URL 배열), `photo_confirmation`(`review_id`, 수정한 `text`)을 받는다. 사진과 확인 텍스트를 같은 요청에 보내지 않는다.
- 브라우저 Origin이 있으면 허용 목록과 대조하고, 모든 요청의 시연 코드를 확인한다. Origin은 인증 대용이 아니다. 글 요청 최대 32KB, 메시지 6000자. 사진 요청 본문은 2,000,000바이트, 장당 실제 파일 700,000바이트·1600만 픽셀, 최대 2장. 사진 확인 텍스트는 2000자까지다. 임의 원격 이미지 URL은 받지 않는다.
- 한 번에 상담 1건, 기본 분당 4건/UTC 일당 30건, 일일 예약 토큰 150만. 텍스트 입력 UTF-8 바이트 수와 출력 예상량, 이미지 장당 32,000토큰을 예약하며 실패해도 환급하지 않는다. 이미지 base64는 텍스트로 계산하지 않는다. 실제 청구 토큰/금액의 측정치나 엄격한 비용 상한은 아니다.
- `PPE_MAX_OUTPUT_TOKENS=5000`은 Responses 모드의 출력 상한이다. Agents API에는 동일 필드가 없으므로 Agents 모드에서는 예약량 산정에만 쓴다. 요청당 최대 2개 세션·145초 처리 제한·자동 재시도 없음·실패 시 취소/삭제를 적용한다. 원격 작업 정리에 최대 약 20초가 추가될 수 있다.
- Agents 세션은 sandbox·추가 도구·하위 에이전트를 사용하지 않는다. 현재 계정에서는 `spend_control` 요청에 `Session budget configuration is not enabled`가 반환되어 `PPE_AGENT_BUDGET_ENABLED=false`로 둔다. 이 상태에서 금액 상한이 적용된다고 주장하지 않는다. 계정에서 지원이 활성화된 뒤 true로 설정하면 세션당 50센트·일일 예약 500센트 기본값을 사용한다. 이 옵션을 거절해도 자동으로 제한을 제거해 재시도하지 않는다.
- `.runtime/usage.sqlite3`는 요청/토큰 **숫자만** 저장한다. 회사 DB나 초안 저장소가 아니며 재시작 후에도 제한을 유지한다. 서버 디스크에 이 경로를 보존한다.
- `touch .runtime/STOP`으로 새 유료 호출을 중지한다. 진행 중인 호출을 취소하거나 환불하지는 않는다. 다시 열 때 해당 STOP 파일을 제거한다. `PPE_CHAT_ENABLED=false`도 지원한다.
- 대화는 앱 프로세스 메모리에 최대 24개·각 6회 상담. 2시간 뒤 만료하고 다음 요청에서 정리한다. 서버 재시작 시 410과 함께 전체 작업 조건 재입력을 안내한다. Agents는 각 단계의 외부 세션을 종료 후 삭제하고, 미완료 작업은 취소 후 삭제한다. 정리 전 ID만 `.runtime/pending-agent-sessions.json`에 보관하고 다음 요청에서 재정리하며, 정리 실패 시 새 상담을 중단한다. API에서 삭제한 뒤 실제 저장소 정리는 비동기일 수 있다. Responses 모드는 `store:false`로 호출한다.
- API 오류에 원문 예외·키·입력을 포함하지 않는다. 자동 유료 재시도는 없다. 미등록 제품/출처, 미조회 원문, 제외 제품 포함 조합, 중복 기본 품목, 표시 형식 불일치는 반환하지 않는다.
- 시험 행의 CAS/농도/온도/원문 값/시험 주석/조회 시각/개정 및 matched/not_found/error를 보존한다. 모든 결과는 검토 후보이며 승인·감지 등록·합성 생성 플래그는 false다.

## 외부 공개 방법

### 도메인 없이 임시 공개하기

현재 PC의 홈페이지를 누구나 조회할 임시 주소로 열 때는 Cloudflare Quick Tunnel을 사용한다. 공식 `cloudflared` 실행 파일을 `~/.local/bin/cloudflared`에 설치하고, `deploy/chemiguard-catalog-public.service.example`의 WorkingDirectory를 앱 경로로 바꿔 `~/.config/systemd/user/chemiguard-catalog-public.service`에 저장한다. 기존 홈페이지 서비스가 필요하다.

```bash
systemctl --user daemon-reload
systemctl --user enable --now chemiguard-catalog-public.service
cat .runtime/public-preview/url.txt
```

출력한 HTTPS 주소는 방문자 계정이나 Tailscale 설치 없이 열 수 있다. 종료는 `systemctl --user disable --now chemiguard-catalog-public.service`다. 이 작업은 기존 Tailscale/SSH 설정을 변경하지 않는다. PC가 꺼지면 접속할 수 없고, 터널 재생성 시 주소가 바뀌므로 위 파일을 다시 확인한다. Quick Tunnel은 임시 시연용이며 운영 가용성을 보장하지 않는다.

터널은 동일한 `127.0.0.1:34402` 앱과 제품 DB를 연결한다. 키를 터널 프로세스에 전달하지 않고 HTTP Host를 `public-preview.invalid`로 고정한다. 등록 제품 사진은 `PPE_PUBLIC_CATALOG_PHOTOS=true`일 때 제공한다. 시연 코드와 기존 전역 상담 예산 제한은 그대로 적용된다. 홈페이지와 상담 API가 같은 공개 출처를 사용하므로 `PUBLIC_API_BASE`는 비워 둔다.

`deploy/public_preview.py`는 생성된 정확한 HTTPS Origin을 비공개 실행 폴더에 기록한다. 서버는 고정 Host·loopback 연결에서 이 Origin만 추가로 허용하고 기존 시연 코드도 확인한다. 임의의 `*.trycloudflare.com` 전체를 허용하지 않는다. 터널을 정상 종료하면 해당 Origin 허용도 제거된다. 매일 오전 9시 제품 수집은 기존 로컬 Codex 자동화를 계속 사용하므로 PC와 Codex 앱이 켜져 있어야 한다.

### 별도 서버와 Vercel 구성

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
.venv/bin/python check_photo_flow.py
```

`check_contract.py`는 외부 API와 제조사 조회를 메모리에서 모의 처리한다. 실제 Agents SDK의 이미지 입력·이벤트 파싱·미완료 스트림 거부·취소/삭제도 오프라인으로 검사한다. `check_photo_flow.py`는 사진 검증, 메타데이터 제거, 확인 전 추천 방지, 수정한 판독 텍스트 반영을 확인한다. 실제 모델 품질 검증을 대신하지 않는다. 실행 결과와 PRD 완료 상태는 [구현 기록](IMPLEMENTATION.md)에 구분했다.

기술 참조: [Agents API 시작](https://developers.openai.com/api/docs/guides/agents-api/quickstart), [세션 설정](https://developers.openai.com/api/reference/resources/beta/subresources/agents/subresources/sessions/methods/create), [세션 정리](https://developers.openai.com/api/docs/guides/agents-api/sessions/manage), [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [Sol](https://developers.openai.com/api/docs/models/gpt-6-sol), [Responses 구조화 출력](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [Vercel 원본 경로 설정](https://vercel.com/docs/monorepos/monorepo-faq).
