# ChemiGuard 전화 알림 — OpenAI만 사용

ClawOps는 한국 전화망과 음성 전송만 담당하고, 우리 서버가 우리 OpenAI 키로 Realtime에 직접 연결한다. 음성 인식·대화·음성 생성은 OpenAI다. 기존 Discord 연결과 별개이며 관제/PPE 판정은 변경하지 않는다.

## 연결 구조

신규 사건 저장 → 별도 OpenAI Luna Decisions 연락 추천 → 고정 정책 검증/담당자 역할 선택 → 개소·신선도·중복 검사 → 전화 대기열 → ClawOps Agent SDK로 발신 → OpenAI Realtime 역할별 음성 대화 → 통화 상태 및 수신 확인 기록.

미착용·보호복 불일치는 현장 안전관리자, 누출 의심은 안전 관제실이다. 담당자는 현장 안전관리자·사내 119·안전 관제실 중 선택할 수 있다. **세 역할 모두 현재 등록 수신번호 하나로만 시연 연결**한다. 사내 119의 자동 선택 조건은 없으며 실제 119 신고도 하지 않는다. [연락 선택 구현/기록 계약](../../docs/PHONE_ROUTING_DESIGN.md).

- SDK `OpenAIRealtime` 경로를 사용한다. `AgentId`, 매니지드 에이전트, 외부 TTS/STT, pipeline, AMD, 다른 제공자 fallback을 사용하지 않는다.
- `gpt-realtime-2`와 OpenAI 공식 HTTPS/WSS 주소를 코드에서 고정한다. 기존 Discord에서 검증한 모델을 유지하며 임의 환경변수로 제3자 호환 엔드포인트를 설정하지 못한다.
- ClawOps SDK 0.38.0의 연결/종료 경계를 보강한 어댑터다. 이 버전을 바꿀 때는 테스트 및 실제 전화 확인이 필요하다.
- 공개 webhook이나 관제 서버의 인터넷 공개가 필요하지 않다. 서버가 ClawOps에 Control/Media WebSocket으로 연결한다. ClawOps 키는 ClawOps에, OpenAI 키는 OpenAI에만 전달한다.
- SDK 로컬 녹음·로컬 음성/전사 저장은 끈다. OpenAI에 전달하는 사건 정보는 개소·종류·짧은 사유·생성 시각이며 원본 영상·사진·로컬 경로는 제외한다. 통신 및 AI 제공자의 자체 데이터 처리는 각 서비스 정책에 따른다.
- ClawOps 계정의 서버 녹음·자동 받아쓰기/요약은 SDK의 `recording=False`와 별개다. 콘솔 **부가서비스 → 통화 녹음 / 통화 받아쓰기**에서 확인해야 한다. 실제 첫 시연 통화 조회에는 `recordingUrl`이 존재했으므로 서버 전체의 녹음이 꺼져 있다고 주장하지 않는다. 녹음·전사를 내려받거나 삭제하지 않았다. [ClawOps 공식 녹음 안내](https://platform.claw-ops.com/docs/call-recording).

## 사용자 설정

저장소 루트의 **`.env.clawops`**가 비공개 설정 파일이다. 처음에는 발신이 꺼져 있다. 예제는 이 폴더의 `.env.example`이다. 실제 키·번호를 채팅/소스/GitHub에 넣지 않는다.

```dotenv
CLAWOPS_ENABLED=false
CLAWOPS_AUTO_CALL=false
CLAWOPS_API_KEY=발급받은_키
CLAWOPS_ACCOUNT_ID=본인_계정_ID
CLAWOPS_FROM_NUMBER=등록된_발신번호
CLAWOPS_TO_NUMBER=안전관리자_수신번호
CLAWOPS_ZONE_ID=시연 구역
CHEMIGUARD_ENV_FILE=기존_OpenAI_키가_있는_파일의_절대경로
```

`CHEMIGUARD_ENV_FILE`은 이미 설정돼 있으면 그대로 둔다. OpenAI 키를 다른 곳으로 복사하지 않고 참조한다. 수신번호/발신번호는 서로 다른 국내 번호여야 하며 발신번호의 통신사 발신 등록도 완료돼 있어야 한다. `CLAWOPS_ZONE_ID`는 작업 기준의 `zone_id`와 정확히 일치해야 한다. 현재는 개소 1개·관리자 1명이다.

맥 터미널에서는 `ssh 사용자명@서버주소`로 접속한 뒤 서버의 저장소 루트에서 아래 명령을 실행하면 네 항목을 차례로 입력할 수 있다. 원격 파일 미리보기의 편집 기능은 필요 없다.

```sh
.venv/bin/python integrations/clawops_voice/setup.py
```

API 키 → Account ID → 등록 발신번호 → 관리자 수신번호 순서다. API 키는 숨김 입력이며 붙여넣고 Enter를 누른다. 값이 이미 설정돼 있으면 Enter로 유지할 수 있고 Ctrl+C로 저장 전에 취소할 수 있다. 번호는 `010...` 또는 `+82...` 형식을 받는다. 네 항목 완료 후 기존 OpenAI 키 참조·개소·기타 설정을 보존하면서 0600 권한으로 저장하고, 수동 발신을 활성화하며 자동 발신은 끈다. API 인증·서비스 재시작·실제 발신은 이 도구가 수행하지 않는다.

저장소 루트에서 선택 의존성을 설치한다(이번 작업 환경에는 설치 완료).

```sh
uv pip install --python .venv/bin/python -r integrations/clawops_voice/requirements.txt
chmod 600 .env.clawops
```

1. 위 설정을 채우고 `CLAWOPS_ENABLED=true`, `CLAWOPS_AUTO_CALL=false`로 저장한다.
2. 실행 중인 영상 분석을 종료한 뒤 관제 서비스를 재시작한다.
3. 사건 전화는 **전화 알림 → 사건 선택 → 연락 대상/역할 확인 → 선택 저장 → 시연 전화**에서 요청한다. 120초가 지난 사건은 ‘이전 사건으로 시연 전화’를 선택해야 한다. 순수 음성 연결 확인은 **연결 시험 역할 → 연결 시험**이다. 최종 ‘지금 시연 전화 걸기’에서 등록번호로 실제 발신하며 전화/AI 비용이 발생한다.
4. 수신 후 OpenAI 음성 대화를 확인하고 “내용 확인했습니다”라고 말하거나 키패드 1번을 누른다. 화면에서 통화 결과와 별도 수신 확인 시각을 확인한다.
5. 자동 사건 발신도 사용하려면 `CLAWOPS_AUTO_CALL=true`로 바꾸고 다시 시작한다. 이후 생성된 해당 개소 미착용/등록 보호복 불일치 HIGH와 누출 의심 REVIEW만 대상이다. 그 외 확인 필요 사건은 제외한다. 자동 발신이 꺼져 있어도 준비된 서버는 새 사건의 추천 계획을 만들며 실제 전화는 담당자의 발신 확인 후에만 실행한다.

현재 환경의 재시작 명령(분석 중 실행하지 않는다):

```sh
systemctl --user restart chemiguard-monitor.service
```

클라우드 콘솔에서 매니지드 Agent를 만들거나 Agent ID를 입력할 필요가 없다. SDK 발신 전용 번호를 사용한다. 이 연결은 들어오는 전화를 대화 세션에 받아들이지 않는다.

## 발신·기록 경계

### 마지막 시연의 통합 전화

세 번째 receiver 영상은 일반 `CLAWOPS_AUTO_CALL=false`와 별개로 로컬 시연 화면의 **매 시연 전화 켜기** 설정을 지원한다. 켜면 공개 페이지를 포함해 새 시연을 시작할 때마다 미착용·누출 두 사건의 실제 연락 Decisions 확인 후 등록번호에 한 통을 안내한다. 번호 공통 50초 간격과 120초 사건 신선도를 유지한다. 공개 방문자가 시연 시작으로 실제 통화 비용을 발생시킬 수 있으므로 시연 종료 후 로컬 화면에서 끈다. 페이지 열기·새로고침·과거 기록 조회는 발신하지 않는다. 통합 상세 계약은 PHONE_ROUTING_DESIGN을 따른다.

### 공통 경계

- 현재 영상 기반 시연이므로 모든 통화에서 **AI 시연 전화**라고 먼저 안내한다. 실제 현장의 현재 사고라고 말하지 않는다. 운영용 실시간 발신 모드는 이번 구현 범위에 없다.
- 같은 사건/역할/수신자는 한 번만 대기열에 넣는다. 같은 등록번호의 50초 이내 다른 알림은 역할/개소와 관계없이 `suppressed`로 기록한다. 이전 5분/10분당 3회 제한을 50초 기준으로 대체했고 발신 직전에도 간격을 재검사한다. 발신 대기열 최대 4건, 연락 추천 대기열 최대 8건, 사건 최대 나이 120초다. 이전 사건 시연은 수동으로 명시해야 하며 원래 사건 시각을 보존한다. 새 사건이 억제됐다고 사건 자체가 해제되지는 않는다.
- 재시작 때 과거 사건을 읽어 자동 발신하지 않는다. 전송 결과가 모호하거나 프로세스가 중단된 요청은 자동 재시도하지 않는다. 부재중의 자동 재시도·예비 담당자 전환·문자 발송은 이번 범위 밖이다.
- 벨 대기 30초, 전체 연결 대기/통화 상한 210초, 대화 무활동 60초 후 종료한다. 종료 API 결과를 확인하지 못하면 `termination_unconfirmed`로 표시한다.
- 단일 worker 및 프로세스 잠금을 사용한다. API 발신 접수·벨·통화·종료·부재중·실패·결과 불명과 수신 확인을 분리한다. 수신 확인은 `phone_call`에만 기록하며 기존 `review`나 PPE 경보 상태를 변경하지 않는다.
- 모델의 음성 확인 도구 호출은 오인식 가능성이 있다. DTMF 1번 확인도 제공하며 두 방식의 기록 경로를 구분한다. 어느 방식도 안전관리자의 실제 현장 조치 완료를 보장하지 않는다.
- `/api/phone` 및 사건 상세/JSON에 마스킹된 전화 이력을 표시한다. 실제 키·전체 수신번호·SDK 원시 오류는 응답이나 기록에 넣지 않는다.

## 확인

우리 서버에 설정된 OpenAI 키로 실제 Realtime 음성 왕복만 먼저 확인할 수 있다. 아래 명령은 짧은 실제 OpenAI API 사용량이 발생하며 전화는 걸지 않는다.

```sh
.venv/bin/python integrations/clawops_voice/check_realtime.py
```

운영 전화와 같은 `OpenAIOnlySession`으로 세션 승인·반환 모델을 확인하고, 메모리에서 생성한 시험 음성을 다시 입력해 발화 감지와 응답 완료를 검증한다. 결과 수치만 Git 제외 `.data/realtime-check-*.json`에 저장한다. 사람의 마이크·ClawOps 전화망·휴대폰 재생 확인을 대신하지 않는다.

실제 전화 이력에는 OpenAI의 `session.updated` 수신 시각, 반환 모델, 상대 음성 전송량, AI 음성 생성량, 발화 감지 및 응답 완료 횟수를 표시한다. 음성 길이는 전화용 G.711 μ-law 8 kHz 바이트 수 환산값이며 입력에는 무음도 포함된다. 설정 준비·전화 연결·Realtime 동작·실제 청취는 별개다. 응답 생성량은 휴대폰에서 들었다는 확인이 아니며 원시 음성·전사·키는 기록하지 않는다. 공식 기준: [OpenAI Realtime 대화 이벤트](https://developers.openai.com/api/docs/guides/realtime-conversations).

```sh
.venv/bin/python -m unittest discover -s tests -p test_phone_alerts.py -v
npm run build
```

키 미설정 차단, 기존 사건 제외, 영속 중복 억제, 개소/검토/신선도, 단일 worker, 부재중, OpenAI 고정 주소·오류, 순수 SDK 발신 본문, μ-law 오디오 전달을 오프라인 검사한다. 실제 통신사 발신·수신·양방향 음질은 ClawOps 키와 번호 설정 후 별도로 확인해야 한다.

공식 근거: [ClawOps Python SDK](https://docs.claw-ops.com/sdk/python), [Agent 구조](https://platform.claw-ops.com/docs/sdk/python/agent), [발신 API](https://docs.claw-ops.com/api-reference/claw-ops-api/calls/create-call), [OpenAI Realtime 계약](https://developers.openai.com/api/reference/resources/realtime/client-events).
