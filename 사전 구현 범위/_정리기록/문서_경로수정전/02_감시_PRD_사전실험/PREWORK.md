# ChemiGuard PREWORK — 사전 구현·시험·실패 기록

근거 범위: 2026-10-08까지 저장된 기록. 문서 작성·검토: 2026-10-08~09 KST. **이 문서의 ‘당일 계획’은 아직 수행하지 않았다.** 기존 실험 코드·결과를 수정하지 않고 읽기 전용으로 조사했다. 새 권장 설계는 [PRD.md](PRD.md)와 [ARCHITECTURE.md](ARCHITECTURE.md)다.

## 1. 읽는 방법과 증거 등급

| 표시 | 뜻 | 예 |
|---|---|---|
| **K: 기록 확인** | 코드·입력 manifest·저장 출력·검토 기록에서 확인 | 모델별 27개 박스 대응 수, API 응답 시간 |
| **U: 사용자 관찰/조건** | 사용자가 제공한 판단·운영 조건 | 흰 보호복이 사람에게도 비슷해 보임, 회사별 색상 표준화 계획 |
| **H: 원인 가설** | 관찰을 설명할 가능성이 있으나 인과 시험 없음 | 벤치 배경이 팔 판단에 영향을 줬을 가능성 |
| **A: 미검증 가정/계획** | 앞으로 확인할 환경·성능·설계 | 3090의 l + Pose + SigLIP + smoke 동시 처리, Mac 원격 안정성 |

K도 독립 현장 정답을 뜻하지 않는다. 사람이나 모델이 정한 개발 관찰, 카탈로그 연결, 시각 검토, 정확한 SKU 정답을 구분한다. 조회한 README에 오래된 기본값이 있으면 더 최근 코드와 실제 출력 기록을 우선한다. 과거 수치를 새 구현 결과로 옮겨 적지 않는다.

경로 약어:

- `R`: `/home/giwon/Downloads/ppe-reference-poc`
- `B`: `/home/giwon/Downloads/models/visible_leak`

R은 Git 저장소로 초기화돼 있지 않았다. 따라서 사전 변경을 커밋 이력으로 전수 추적했다고 주장하지 않는다. `HANDOFF.md`, 보고서, `code_before/code_run`, JSON hash와 현재 파일을 대조했다. 본 문서 묶음의 [documentation_audit.json](documentation_audit.json)은 이번 조사 전후 소스 해시와 링크 검사를 기록한다. 비밀 `.env`는 읽거나 복사하지 않았다.

## 2. 실제 사전 구현 상태

| 구성 | K: 구현·실행 확인 | 남은 범위 |
|---|---|---|
| 사진 등록 | CLI 사진 + bbox → crop·SigLIP 임베딩·SQLite, 출처/영역/전처리 관리 | 새 이미지 업로드 UI·URL 자동 등록 없음 |
| 제품 DB | 기본 DB 제품 0개/사진 0장. 연구 `registry_body_regions` 제품 5개/사진 9장, full 5장 + torso 4장 | 전 제품 threshold·margin NULL. 정확 SKU 확정·보정 없음 |
| 사람 검출 | 현재 기본 YOLO26n + ByteTrack. s/m/l/YOLOX 비교 완료 | l로 기본 교체하지 않음, 새 전체 GPU 조합 미측정 |
| 관절 | 별도 YOLO26n-Pose, 원본 사람 crop·body ROI | Pose가 사람 검출·가시성 정답을 보장하지 않음 |
| PPE 후보 | YOLOE-26s visual prompt, 필수 제품의 첫 full reference | 낮은 안정성·후보 누락·의복 밖 후보 사례. 등록 사진 전체를 동시에 쓰는 구현 아님 |
| 제품 검색 | SigLIP2, 같은 영역 reference의 상위 2개 평균·차순위 gap, PE 비교 | 높은 오검색·미등록 최근접값 존재. torso는 진단 모드 |
| 착용 | 기본 Luna Responses, 5부위 가시성 + 위반 관찰, 후드/여밈 선택 | 실제 회사의 전 PPE 판정, 독립 정확도 미검증 |
| 시간·실패 | 사람별 주기, 2회 합의, TTL, 추적 손실·늦은 응답 폐기 | 새 구조의 API 지연 중 smoke 지속 동작 미검증 |
| 카탈로그 | 44개 제품 사진·검색·물질 상담·형식/작업 색상 비교 | 44개 제품 모두 영상 registry 등록된 것이 아님 |
| 시연 기준·검토 | 수동 제품 연결, 정책·DB/사진 hash, 저장 근거와 append-only 검토 | 현재 정책으로 새 전체 영상 실행 미시험 |
| 가시적 분출 | 별도 gas/smoke/liquid/pipe 모델 학습·오프라인 영상 비교 | PPE와 실시간 동시 분석 및 사건 수준 경보 미검증 |
| 알림·대응 | 저장 결과 검토·확인/반려/보류 | 외부 알림/자동 설비 정지/대피 조치 미구현 |

현재 운영 화면 `operations`는 **저장 분석 재생**이다. 그 화면에서 현재 policy로 모델을 새로 돌렸다는 의미가 아니다. PPE 교육 영상과 구미 누출 영상은 서로 다른 촬영·사건이며, 같은 화면에 보인다고 같은 사건의 사람과 누출이 연결된 것은 아니다.

## 3. 핵심 실험 근거 대장

### E01 — ENEX 사람 탐지와 ROI

**K. 입력:** 사용자 제공 [44.1초 ENEX 영상](/home/giwon/Downloads/enex-fuel-accident/enex-accident-01m49s-02m33s.mp4), 1280 × 720. 수동 주석 6프레임·사람 박스 6개, 추론 225개 고정 프레임. [입력 계획](../ppe-reference-poc/research/enex_person_detection_20261008/comparison_plan.json), [주석](../ppe-reference-poc/research/enex_person_detection_20261008/annotations.json), [ROI 계획](../ppe-reference-poc/research/enex_person_detection_20261008/roi_plan.json).

설정: CPU 2 threads, imgsz 640, conf 0.1, person class 0, ByteTrack. tracked bbox의 IoU ≥ 0.5 일대일 대응으로 채점했다. raw detector AP가 아니다.

| 조건 | 사람 대응 | 호스 영역 오탐 후보 | CPU 평균 |
|---|---:|---:|---:|
| YOLO26n | 5/6 | 2 | 22.38 ms |
| YOLO26s | 5/6 | 1 | 41.67 ms |
| YOLO26n-Pose 주검출 | 3/6 | 0 | 24.21 ms |
| YOLO26n + 장면 ROI | 5/6 | 0 | 36.23 ms |

ROI는 `[280, 0, 1000, 720]`이며 입력 확대·주변 제거를 포함하는 다른 조건이다. 먼 사람은 여전히 놓쳤다. [출력](../ppe-reference-poc/research/enex_person_detection_20261008/comparison.json), [ROI 출력](../ppe-reference-poc/research/enex_person_detection_20261008/roi_comparison.json), [채점](../ppe-reference-poc/research/enex_person_detection_20261008/scored.json), [설명](../ppe-reference-poc/research/enex_person_detection_20261008/README.md).

**설계 반영:** 사람 detector와 Pose를 분리. ROI는 사전에 선언한 구역 설정으로만 허용. 이 영상 전용 정답 기반 crop을 새 제품 규칙으로 하드코딩하지 않는다.

### E02 — ENEX에서 모델 크기 확대

**K. 입력:** E01과 같은 225프레임/사람 박스 6개. 새 m/l 각 1회, n/s는 저장 결과 재사용. [계획](../ppe-reference-poc/research/yolo26_size_probe_20261008/plan.json), [출력](../ppe-reference-poc/research/yolo26_size_probe_20261008/comparison.json), [m 원시 출력](../ppe-reference-poc/research/yolo26_size_probe_20261008/detect_m.json), [l 원시 출력](../ppe-reference-poc/research/yolo26_size_probe_20261008/detect_l.json).

m/l 모두 사람 5/6 대응·호스 영역 오탐 1개, CPU 평균 83.37/104.91 ms였다. 먼 사람 frame 910 누락과 frame 1138 호스/바닥 오탐이 남았다. 실행 간 CPU 부하가 완전히 통제된 비교는 아니다. [설명](../ppe-reference-poc/research/yolo26_size_probe_20261008/README.md).

**해석:** 이 입력에서는 모델 확대만으로 개선하지 못했다. 이를 “l은 언제나 불필요”로 일반화하지 않는다.

### E03 — 다른 영상 3개에서 n/s/m/l

**K. 입력:** V08 제조사 교육 0.8–6.2초, V12 군 작업장 보행 1.4–5.6초, S36 EDS 편집본 중 실제 APG-Cam CCTV 82.4–90.8초. 9개 주석 프레임, 사람 박스 27개, ignore 영역 5개. 크기별 90프레임, 총 360회 track 호출 + 12회 warmup. [출처·주석](../ppe-reference-poc/research/yolo26_multivideo_probe_20261008/sources_annotations.json), [고정 계획/모델 hash](../ppe-reference-poc/research/yolo26_multivideo_probe_20261008/plan.json).

| 모델 | 27개 박스 중 대응 | ignore 밖 추가 박스 | CPU 평균/p95 (ms) |
|---|---:|---:|---:|
| n | 21/27 | 0 | 20.35 / 22.88 |
| s | 24/27 | 0 | 37.65 / 45.35 |
| m | 25/27 | 1 | 101.11 / 122.07 |
| l | 27/27 | 1 | 111.36 / 126.30 |

S36만 보면 n/s/m/l = 2/6, 3/6, 4/6, 6/6이다. V08은 모두 6/6, V12는 13/15, 15/15, 15/15, 15/15다. m/l 추가 박스는 같은 사람의 중복 후보였다. [통합 출력](../ppe-reference-poc/research/yolo26_multivideo_probe_20261008/comparison.json), [S36 l 원시 출력](../ppe-reference-poc/research/yolo26_multivideo_probe_20261008/S36_l.json), [설명](../ppe-reference-poc/research/yolo26_multivideo_probe_20261008/README.md).

**한계:** CPU 2 threads/imgsz 640/conf 0.1/ByteTrack 결과. 27개의 독립 사람이나 독립 영상이 아니고 IDF1/HOTA 평가도 아니다. **3090 GPU 처리량·새 서비스 FPS·현장 정확도 100%가 아니다.** l 선택은 이 작은 표본을 근거로 한 잠정 설계다.

### E04 — 사람 전용 YOLOX 대조

**K. 입력:** E01의 225프레임/주석 6프레임, ByteTrack 공식 YOLOX-S 사람 체크포인트, CPU 2 threads. COCO 초기화와 CrowdHuman/MOT17/Cityperson/ETHZ 학습을 원 배포자가 설명한다. [계획](../ppe-reference-poc/research/yolox_person_probe_20261008/plan.json), [출력](../ppe-reference-poc/research/yolox_person_probe_20261008/comparison.json), [설명](../ppe-reference-poc/research/yolox_person_probe_20261008/README.md).

384 × 640은 사람 4/6 대응·호스 영역 오탐 0개·평균 118.28 ms, 608 × 1088은 사람 5/6 대응·호스/바닥 영역 오탐 1개·평균 288.76 ms였다. 첫 저해상도 장면에서는 raw 사람 conf 0.204가 있었으나 새 track 기준 0.25보다 낮아 보류됐다. 먼 사람은 raw에서도 없었다. **사람 전용 데이터로 학습했으니 현장 성능이 더 좋다는 결론은 나오지 않았다.** 코드와 데이터/가중치 라이선스가 별도이므로 기본 반입에서 제외했다.

### E05 — 제품 검색·YOLOE 후보의 한계

**K. SigLIP 대 PE:** 등록 full reference 5장, 제조사 제품군 연결 query 8장 + 미등록 의복 3장. SigLIP 384와 PE 224, 입력 해상도와 processor가 다르다. [입력](../ppe-reference-poc/research/encoder_comparison_20261004/input_manifest.json), [출력](../ppe-reference-poc/research/encoder_comparison_20261004/comparison.json), [PE snapshot](../ppe-reference-poc/research/encoder_comparison_20261004/pe_snapshot.json), [설명](../ppe-reference-poc/research/encoder_comparison_20261004/README.md).

제품군 top 1은 둘 다 7/8이다. I052/P12를 SigLIP은 P11, PE는 P02로 오검색했다. 미등록 ST40도 높은 최근접 점수가 나왔다. RTX 3090에서 단독 인코딩 query 11개를 1회씩 측정한 중앙값은 SigLIP 13.18 ms/PE 9.64 ms이며 전체 영상 처리 속도가 아니다. query에는 같은 촬영 그룹과 마네킹 자료가 포함되어 독립 착용 정확도로 볼 수 없다.

P02 = Tychem 6000F FaceSeal, P11 = Tychem 4000S, P12 = Tyvek 500 Xpert다. 카탈로그 연결 제품명이 실제 화소의 정확 SKU를 독립 입증하지는 않는다.

**K. YOLOE prompt 실험:** 두 개발 인물 crop에서 full mask는 후보가 각 1개였으나 garment mask는 conf 0.15에서 둘 다 0개, conf 0.005에서는 잡후보가 10/9개였다. text coverall은 부분착용에 상체와 겹치지 않는 후보 1개·정상 0개였다. [수정 요약](../ppe-reference-poc/demo/adaptive-ppe/results/yoloe_prompt_regions/change_summary.json), [reference mask](../ppe-reference-poc/demo/adaptive-ppe/results/yoloe_prompt_regions/reference_mask_annotation.json). 안정적인 PPE 영역이나 착용을 prompt만으로 확보한 결과가 아니다.

**설계 반영:** 새 P0에서 YOLOE 의무 경로를 제외하고 제품 검색은 보조 후보로 제한. PE를 합쳐 해결됐다고 주장하지 않는다.

### E06 — Pose 몸통 직접 검색

**K. 입력:** 등록 torso는 4개 제품에 각 1장이다. 제조사 query 4장/제품군 3개, ENEX 제품 미상 2건, 작은 사람·호스 2건을 사용했다. 기존 사람 bbox를 재사용했고 person detector 재평가가 아니다. CPU로 Pose 8개·SigLIP 6개를 실행했고, YOLOE/API 실행은 0회였다. [입력](../ppe-reference-poc/research/pose_direct_similarity_20261008/real_probe/manifest.json), [출력](../ppe-reference-poc/research/pose_direct_similarity_20261008/real_probe/results.json), [설명](../ppe-reference-poc/research/pose_direct_similarity_20261008/README.md).

제조사 top 1은 3/4였다. I007/P02가 P11로 검색됐고 cosine 0.9172/gap 0.0264였다. ENEX 두 사례의 P12 최근접 점수 0.5415/0.5581은 제품 정답으로 채점하지 않았다. 작은 사람·호스는 몸통 ROI가 없어 검색하지 않았다. 기준 미보정/ROI 부재로 8건 모두 uncertain이었다. 최초 실행을 제외한 유효 5건의 CPU 중앙값은 Pose 31 ms + SigLIP 200 ms, 합계 약 233 ms였다. 첫 로드는 2.37초였다.

**K:** 선택 helper는 작동했다. **A:** YOLOE를 완전히 제거한 새 서비스의 품질·속도는 아직 검증하지 않았다. 높은 유사도와 관절 위치만으로 제품·착용을 확정할 수 없다는 실패 근거다.

### E07 — Luna 호출 경로와 지연

**K. 입력:** 제조사 교육 영상의 개발 사진 6개 반복. 100개의 독립 이미지가 아니다. [입력 준비](../ppe-reference-poc/research/luna_responses_comparison_20261006/prepared_manifest/prepared.json), [원시 결과](../ppe-reference-poc/research/luna_responses_comparison_20261006/latency100_live_20261006/results.json), [결과표](../ppe-reference-poc/research/luna_responses_comparison_20261006/RESULTS.md).

| 조건 | 측정 호출 | p50/p95 (s) |
|---|---:|---:|
| App Server Luna none 요청 | 100 | 4.053 / 7.227 |
| Responses Luna medium | 100 | 2.229 / 3.392 |
| Responses Luna none | 100 | 1.817 / 2.512 |

조건별 개발 라벨 일치는 100/100·오류는 0건이었지만 사진 6개를 반복한 결과다. 클라이언트 전체 응답 지연이며 순수 모델 계산 시간이 아니다. App Server/Responses가 같은 모델 별칭이어도 전송·도구 환경·계층이 다르므로 차이 전부를 특정 내부 단계 탓으로 확정하지 않는다. Responses none 선택의 근거로 사용한다.

### E08 — Fast·출력 축약과 팔 오탐

**K. 입력:** 같은 개발 사진 6개 × 조건별 2회 반복, 같은 JPEG 85/high 4~5장. [준비 입력](../ppe-reference-poc/research/luna_fast_compact_20261006/prepared/prepared.json), [원시 결과](../ppe-reference-poc/research/luna_fast_compact_20261006/live/results.json), [요약](../ppe-reference-poc/research/luna_fast_compact_20261006/summary.json), [설명](../ppe-reference-poc/research/luna_fast_compact_20261006/README.md).

Standard/기존 답의 p50/p95 = 1.663/2.275초, Fast/기존 답은 1.289/1.934초, Fast/축약 답은 1.128/1.357초였다. 출력 평균은 57.33 → 28.67 tokens였다. 각 조건의 개발 라벨 일치는 12/12·오류는 0건이었다. 이후 영상에서는 팔을 미착용으로 본 오탐 의심이 나왔고, 같은 문제 crop에서 짧은 답과 긴 답이 다른 경우도 있었다. [오탐 입력](../ppe-reference-poc/research/luna_fast_compact_20261006/video_spot_manifest.json), [추가 답](../ppe-reference-poc/research/luna_fast_compact_20261006/video_spot_verbose/results.json).

**H:** 벤치 배경, 잘린 crop, 자세·가림 해석, 응답 변동이 원인 후보였다. 벤치 없는 팔 올림 사진에도 오탐 의심이 있어 벤치 원인으로 확정하지 않았다. [배경 검토 입력·결과 설명](../ppe-reference-poc/research/luna_arm_background_review_20261006/README.md). 이때의 단순 축약 프롬프트와 다음 E09의 5부위 프롬프트는 다르다.

과거 보고서의 달러 환산은 당시 token 사용량·공식 단가를 적용한 추정이며 청구서 실측이 아니다. 새 앱의 비용은 미측정이므로 현재 비용표로 재사용하지 않는다.

### E09 — 현재 착용 관찰과 메모리 최적화

**K. 입력:** 재사용 개발 사진 7장. `photos.json`에 입력과 이전 답을 연결했다. 현재 질문은 5부위 가시성 + 보이는 위반 + wearing. gpt-6-luna/none/Fast/JPEG 85/high, person + torso + legs 3장. [사진 출력](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/photos.json), [요약](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/summary.json), [설명](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/README.md).

개발 관찰 일치는 최초 6/7에서 질문 수정 후 7/7이었다(yes 2/no 2/uncertain 3). 최종 평균 1.429초/p50 1.419초/p95 1.883초, 평균 출력 46 tokens였다. payload 합계는 1,575,732 → 971,322 B(-38.4%)였다. 같은 사진에서 수정한 결과이므로 독립 검증이 아니다.

SigLIP vision-only는 고정 3장의 벡터·순위가 동일했고 CUDA 할당은 766,694,400 → 194,614,272 B(-74.6%)였다. 3장 batch는 0.045 → 0.050초여서 속도 향상은 확인되지 않았다. [이전 측정](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/encoder_before.json), [이후 측정](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/encoder_after.json).

| 영상 | 입력·출력 | 실제 관찰 |
|---|---|---|
| V08 두 사람 17.52초 교육 영상 | [영상](../ppe-reference-poc/demo/adaptive-ppe/video/V08_wide_205_222_5s.mp4), [JSONL](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/video_two_people/observations.jsonl) | 146프레임/처리 7.95 FPS, API 13회·평균 1.312초. API 가시성 결과 13개 uncertain, 최종 관측 58개 UNKNOWN |
| V08 부분 착용 14초 교육 영상 | [영상](../ppe-reference-poc/demo/adaptive-ppe/video/V08_donning_76_90s.mp4), [JSONL](../ppe-reference-poc/research/contest_pipeline_optimization_20261006/video_partial/observations.jsonl) | 116프레임/8.18 FPS, API 10회·평균 1.225초, 8회 적용/2회 추적 손실로 폐기. 최종 관측 45개 중 UNKNOWN 43개/위반 의심 2개 |

두 사람 영상의 “모두 UNKNOWN”은 정상 검증 성공이 아니다. 부분 착용에서 track 4의 1.88/4.28초 NO가 두 표로 연결됐지만 6.08초 NO는 추적 손실로 폐기됐다. 관측 45개를 45명·45개 독립 사례로 세지 않는다. 전체 호출 장애 0건이 인위적 timeout 처리 시험을 대신하지 않는다.

### E10 — ENEX 전체 PPE 파이프라인

**K. 입력:** E01 영상. P11은 실험용 reference이며 이 사업장의 필수 제품이 아니다. 당시 YOLO26n/Pose/YOLOE/SigLIP/Luna 기본 구성을 1회 실행했다. [보고서](../ppe-reference-poc/research/enex_ppe_check_20261008/report.json), [원시 JSONL](../ppe-reference-poc/research/enex_ppe_check_20261008/run/observations.jsonl), [설명](../ppe-reference-poc/research/enex_ppe_check_20261008/README.md).

처리 376프레임/8.53 FPS, API 14회·평균 1.342초/p50 1.263초/p95 1.946초였다. raw 결과는 YES 8개/NO 6개였으나 가시성 적용 후 전부 uncertain이었다. 6회 적용/8회 추적 손실로 폐기됐고, 최종 관측 39개는 모두 UNKNOWN이었다. YOLOE 후보와 SigLIP 제품 순위는 없었다. 영상 속 옷을 등록 화학복으로 확정한 결과가 아니다.

시각 검토에서 30.33/32.07/34.37/36.13/41.83초에 호스를 사람으로 잡아 API에 보낸 5개 사례를 확인했다. 일부 답은 상태에 반영됐지만 모두 UNKNOWN이었다. Track ID 7개가 사람 7명이라는 뜻은 아니다. 이후 몸통 증거가 없는 사람 후보는 유지하되 착용 API를 보류하는 guard를 추가했고, 그 변경 뒤 전체 PPE 영상 재실행은 하지 않았다.

### E11 — Decisions 시험과 부위 crop

**K. 입력:** 같은 개발 사진 7장, Responses 자동 재확인 없음. 부위 질문은 covered/uncovered/unobservable이며, 선택 차이 margin 0.20은 보정된 확률 기준이 아닌 실험 휴리스틱이다. [질문 개선 계획](../ppe-reference-poc/research/decisions_parts_20261007/protocol.json), [결과](../ppe-reference-poc/research/decisions_parts_20261007/summary.json), [설명](../ppe-reference-poc/research/decisions_parts_20261007/README.md).

질문 개선으로 개발 기준 일치가 4/7 → 5/7로 바뀌었다. 가린 팔을 YES로 답한 문제가 남았고 중앙값은 0.774초였다. 다른 실험의 0.346초와 같은 시간 조건에서 비교한 결과는 아니다.

후속 시험은 같은 7장의 paired 비교였다. 문맥 3장 vs 부위 최대 6장, 순서 교대, 측정 14회 + warmup 2회였다. 둘 다 5/7로 일치했다. 가린 팔의 YES → UNKNOWN은 개선됐지만, 탈의의 NO → UNKNOWN은 퇴행했다. p50은 문맥 0.442초/부위 0.541초였다. [입력](../ppe-reference-poc/research/decisions_region_crops_20261007/prepared.json), [계획](../ppe-reference-poc/research/decisions_region_crops_20261007/protocol.json), [응답 JSONL](../ppe-reference-poc/research/decisions_region_crops_20261007/calls.jsonl), [요약](../ppe-reference-poc/research/decisions_region_crops_20261007/summary.json).

Pose crop에 숨은 팔 대신 호흡 장비·도우미 팔이 포함될 수 있었다. 따라서 부위 사진을 더 보내면 무조건 좋아진다는 근거가 없다. Decisions는 runtime 기본에 통합하지 않았다.

### E12 — 카탈로그·물질·색상

**K:** 현재 제품 44개(화학복 16/장갑 10/장화 4/호흡 10/눈 2/안면 2), 사진 44개다. 기존 기록상 15개는 정확한 스타일이 미확인 상태다. [카탈로그 데이터](../ppe-reference-poc/demo/video-gallery/kit-catalog/catalog-data.json), [제조사 조회 기록](../ppe-reference-poc/research/live_material_lookup_20261006/README.md), [검증](../ppe-reference-poc/research/live_material_lookup_20261006/verification.json).

DuPont 보호복 3종의 공식 시험표 CAS 행 조회를 구현했다. 다른 품목 전체의 실시간 조회는 아니다. 저장 상담 예시는 아세톤 52.18초, 혼합 입력 72초였으며 독립 안전 정답 시험이 아니다. 시험 시간을 안전 사용 시간으로 변환하지 않는다.

작업 색상 상담 1회는 84.53초였다. 산 이송/알칼리 이송 각 4품목, 남은 확인 5/7개, 장화·호흡은 미선정이었다. [작업 색상 기록](../ppe-reference-poc/research/work_group_colours_20261007/README.md), [검증](../ppe-reference-poc/research/work_group_colours_20261007/verification.json).

**U:** 회사는 형식/작업별 색상을 표준화할 계획이다. **A:** 실제 매핑·영상 색상 규칙·승인 정확도는 미검증이다. 카탈로그의 색상 비교 기능을 영상의 자동 색상 판정으로 설명하지 않는다.

### E13 — 기준·근거·사람 검토 연결

**K:** catalog 초안 → 화학복 수동 mapping → 시연 policy → 저장 분석 → 확인/반려/보류를 구현했다. 로컬 검사 6묶음을 1회 실행했고, 검사용 policy 1개·보류 review 1행을 남겼다. [통합 기록](../ppe-reference-poc/research/chemiguard_integration_20261007/README.md), [확인 결과](../ppe-reference-poc/research/chemiguard_integration_20261007/verification.json), [정책 구현](../ppe-reference-poc/chemiguard_workflow.py), [저장 결과 어댑터](../ppe-reference-poc/chemiguard_evidence.py).

PPE 영상 2개에서 UI에 관측 12/10개를 표시했고, 맥락 프레임은 4장이었다. 누출은 Gumi 저장 결과의 164/169번 프레임 2장이었다. 실제 같은 시각의 프레임을 확인했으나 API 전송 crop과는 구별했다. GPU 사용 0회/새 모델 추론 0회/외부 모델 API 0회이며, policy로 새 영상을 처리한 통합 시험이 아니다.

이전 [10/7 통합 검토서](../ppe-reference-poc/docs/contest_m3_pro_20261006/INTEGRATION_REVIEW_20261007.md)의 ‘사람 검토 UI 없음’은 이 후속 구현보다 오래된 상태다. 현재도 회사 사용 승인·정확 SKU 확인은 false다.

### E14 — 가시적 분출·연기·액체 모델

**K. 최신 완료 상태:** 저장 기록상 smoke 50 epoch, liquid 기본 50 + 추가 13 epoch, pipe 45 epoch를 완료했다. full-gas는 사용자 요청으로 47 epoch에서 중지했다. 이 조사는 현재 GPU 프로세스를 확인하지 않았으며, 다른 학습이 없다는 뜻이 아니다.

| 시험 | 입력·모델·설정 | 기록된 결과 | 해석 |
|---|---|---|---|
| smoke 정지 사진 | FASDD 선별 train 37,251/val 4,657/test 4,657, COCO YOLO26s 초기화, smoke 1 class | test P 0.834/R 0.704/mAP50 0.799/mAP50–95 0.585 | 원 영상/scene ID 부재, 완전한 촬영 분리 증명 없음. 화학 누출 정확도 아님 |
| smoke 실내 영상 2개 | receiver 653프레임, ElkGrove 8,262프레임; imgsz 960/conf 0.25/batch 16/전체 프레임 | 검출이 있는 프레임 292/3,902개, 첫 검출 12.052/127.708초 | GT 없는 출력 횟수. 사건 시작 대비 지연이나 성공률 아님 |
| KTV 구미 편집 | native smoke/gas/pipe 비교, conf 0.25 | smoke: 16.683초 흰 분출 박스, 59.03초 흰 작업복 2명 오탐. gas: 0.03초 앵커 얼굴 오탐 | CCTV가 삽입된 뉴스 편집본. 가스종 식별 아님 |
| full-gas | 전체 참고 영상 26개·샘플 프레임 1,329개 중 가스/증기 영상 21개 부분집합. 유효 양성/음성 anchor는 영상 20개에 존재하며, 원 gas와 비교 | 양성 반응 35/52 → 11/52, 음성 반응 7/22 → 1/22 | 오경보 감소와 검출 감소가 동시에 발생. 자동 교체 근거 부족 |
| liquid-jet | ENEX 1,323프레임/HCL 영상, conf 0.25 | ENEX 18/24초 분출 누락, 분출 전 탱크 반사 오인 | 학습 완료가 실제 액체 분출 검출 성공을 뜻하지 않음 |
| pipe-leak | heldout 사진 73장 + 외부 영상 | val mAP50 0.813 → test 0.325; ENEX 18/24초 미검출 | 다른 장면 일반화 부족, 기본 모델에서 제외 |

직접 확인한 근거:

- smoke [학습 입력·모델 hash·완료](/home/giwon/Downloads/models/visible_leak/fasdd-smoke-yolo26s-20261007/training_result.json), [heldout 출력](/home/giwon/Downloads/models/visible_leak/fasdd-smoke-yolo26s-20261007/heldout_test.json).
- 실내 [러너·입출력 계약](/home/giwon/Downloads/models/visible_leak/fasdd-smoke-yolo26s-20261007/infer_indoor_pair.py), [요약](/home/giwon/Downloads/models/visible_leak/fasdd-smoke-yolo26s-20261007/video-check-20261008/indoor-pair-leak-20261008/summary.json), [receiver 예측](/home/giwon/Downloads/models/visible_leak/fasdd-smoke-yolo26s-20261007/video-check-20261008/indoor-pair-leak-20261008/receiver_valve_predictions.json). 입력 원본은 `B/cctv-20-20261004/clips/04_nh3_receiver_valve.mp4`다.
- KTV [원본](/home/giwon/Downloads/models/visible_leak/ktv-gumi-442065-20261008/ktv_442065_source.mp4), [예측](/home/giwon/Downloads/models/visible_leak/ktv-gumi-442065-20261008/inference/fasdd_smoke_predictions.json), [시각 검토](/home/giwon/Downloads/models/visible_leak/ktv-gumi-442065-20261008/inference/visual_review.json).
- full-gas [종료·외부 평가](/home/giwon/Downloads/models/visible_leak/full-gas-yolo26s-20261007/completion_audit.json), [Gumi 예측](/home/giwon/Downloads/models/visible_leak/full-gas-yolo26s-20261007/gumi-review/dense_predictions.json). 입력은 `B/cctv-20-20261004/clips/01_gumi_hf.mp4`다.
- liquid [영상 검토](/home/giwon/Downloads/models/visible_leak/liquid-jet-yolo26s-20261008/evaluation_review.json), [ENEX 예측](/home/giwon/Downloads/models/visible_leak/liquid-jet-yolo26s-20261008/cctv-eval-stable/enex_liquid_discharge_predictions.json).
- pipe [영상 검토](/home/giwon/Downloads/models/visible_leak/pipe-leak-yolo26s-20261008/evaluation_review.json).

기존 Gumi JSON의 xyxy는 0–1 정규화 좌표이고 실내 JSON은 pixel 좌표다. 새 계약은 coordinate_system을 명시해야 한다. `best_leak.pt`는 smoke tensor에 표시명만 바꾼 파생본으로, 새로운 누출 학습 성과가 아니다. [표시명 기록](/home/giwon/Downloads/models/visible_leak/fasdd-smoke-yolo26s-20261007/video-check-20261008/leak-display/label_alias.json).

**라이선스 근거:** FASDD [2026-09-11 원출처 관찰](/home/giwon/Downloads/FASDD_detection/source_manifest.json)은 공식 v9/CC BY-SA 4.0을 기록했다. [공식 페이지](https://www.scidb.cn/en/detail?dataSetId=ce9c9400b44148e1b0a749f5c3eb0bda), DOI 10.57760/sciencedb.j00104.00103과 일치한다. 이번 현재 페이지 조회에서는 본문 배지를 확보하지 못했으므로 최신 라이선스를 직접 재확인했다고 표현하지 않는다. smoke는 COCO 초기화이며 AIHub 가중치를 쓰지 않았다. 출처·변경 고지·AGPL 조건을 확인한 뒤 공개 배포한다.

AIHub leak.pt는 원문 README의 AGPL 표시 외에 [AIHub 공식 이용 정책](https://www.aihub.or.kr/intrcn/guid/usagepolicy.do?currMenu=151&topMenu=105)의 응용 모델 제공·반출 조건이 있다. 이번에 개별 승인 기록을 확인하지 못했으므로 **오픈 라이선스만으로 반입 가능한 필수 백업에서 제외**한다. 이 조건을 데이터에서 학습 가중치 전체로 기계적으로 일반화하지 않는다.

### E15 — 영상 수집과 자료 성격

**K:** [자료 대장](../ppe-reference-poc/research/chemical_ppe_video_search_20261004/candidates.json), [검색 기록](../ppe-reference-poc/research/chemical_ppe_video_search_20261004/README.md), [10/8 결과](../ppe-reference-poc/research/chemical_ppe_video_search_20261004/heartbeat_20261008/README.md). 최신 갤러리는 22편/촬영 그룹 11개이며, 실제 CCTV는 출처 그룹 1개(S36/S37 관련 편집본)다. 신규 유용 영상이 0개인 날도 있었다.

제조사 착탈의 교육·홍보·군 훈련·실제 고정 CCTV·스톡을 구분한다. 영상 설명만으로 상용 화학복 SKU·정상 착용 정답을 부여하지 않는다. 갤러리의 시각 검수와 모델 성능 시험은 별개다.

공식 시연 자료 찾기의 시작점: [DuPont Tychem 4000S 포털](https://www.smartservices.tyvek.es/products/tychem-4000-s-slchz5twh00.html), [DVIDS 작업 영상 V12](https://www.dvidshub.net/video/1008159/mals-12-marines-work-mopp-gear), [EDS S36 공식 편집본](https://www.dvidshub.net/video/992238/us-army-chemical-materials-activity-recovered-chemical-materiel-directorate-explosives-destruction-system-eds-b-roll). 이 링크가 행사 당일 다운로드/재배포 가능성을 보장하지 않는다. 사용 범위를 확인하고 당일 직접 허용 자료를 등록한다.

## 4. 사용자 관찰·가설·미검증 항목

| 구분 | 내용 | 문서에서의 취급 |
|---|---|---|
| U | P11/P12가 사람에게도 혼동될 수 있다는 관찰 | 정확 SKU를 핵심 자동 승인 기능으로 두지 않는 제품 판단에 참고. 정답 라벨 변경 근거 아님 |
| U | 회사의 형식별 색상 표준화 계획 | 향후 policy 입력 후보, 현재 영상 색상 판정 구현 아님 |
| H | 벤치가 팔 오탐의 원인 | 배경 제거 통제 시험 없음. 다른 사진에도 오류가 있으므로 확정 금지 |
| H | Pose/torso 검색이면 YOLOE 후보 누락을 완전히 해결 | 후보 없이 점수는 생성됐지만 오검색과 ROI 미추출이 남음 |
| A | GPU 환경에서 l + smoke도 충분히 빠를 것 | CPU 결과/단독 GPU 결과만 있음. 새 통합 실측 필요 |
| A | Mac 원격이 현장에서 안정적일 것 | 새 네트워크·원격 제어·화면 지연 미시험 |
| A | 3장 등록으로 회사 PPE를 확정할 수 있을 것 | 실제 1/3/5장 공정 비교 미실행. 사진 추가가 항상 개선하지 않음 |
| A | 시간 투표로 지속되는 흰 작업복 오탐이 해결될 것 | 장면 지속성 규칙 미시험, 지속 오탐은 통과할 수 있음 |

논의만 한 것: SAM 정밀 마스크, DINOv3, imajev 교체, 합성 착용 영상, 넘어짐 시계열 모델, 클라우드 GPU 배포. PE·Decisions는 실행한 실험이지만 기본 파이프라인으로 채택한 것은 아니다. Qwen은 과거 실행 기록이 있으나 현재 설정 경로가 없어 준비된 fallback이 아니다.

## 5. 변경 기록과 기존 자료의 정정

| 시기 | 사전 변경 | 보존 근거 |
|---|---|---|
| 10/3~4 | 사진 등록·SQLite·원본 crop·Pose·YOLOE·SigLIP·Qwen·후보 귀속/시간 조건 | 루트 README, DESIGN, research 실험 기록 |
| 10/4 | 입력 전처리/증강/PE 비교, 제품 오검색 보존 | E05, image_augmentation 기록 |
| 10/5~6 | App Server → Responses 비교, Fast/축약, 팔 문제 관찰, YES/NO와 가시성 gate | E07~E09, 각 code_before/code_run |
| 10/6 | SigLIP vision-only, 영상 generic 착용 관찰·정책/제품 결과 분리 | E09 |
| 10/7 | Decisions 부위 시험·시연 기준/사람 검토 연결 | E11/E13 |
| 10/8 | ENEX 관찰·ROI·몸통 API gate·직접 torso 검색·사람 크기 비교 | E01~E06/E10 |
| 10/7~8 | 별도 smoke/liquid/pipe 학습·영상 확인, 실패 보존 | E14 |

현재 README 일부 표의 기본 Qwen/PPE 후보를 Luna에 전송한다는 설명은 구표기다. 현재 화학복 Responses 입력은 전체 사람·몸통·다리(+필요 시 머리)이며, 등록 사진·제품명·유사도·PPE 후보 사진을 전송하지 않는다. `monitor_video.py`의 현재 기본은 n + ByteTrack/luna-api이고, l/YOLOE 생략은 **새 권장안**이다.

구 10/6 반입 manifest의 `models_count=11`은 실제로 n + pose + YOLOE + SigLIP 구성 파일 8개를 센 파일 수다. **신경망 11종이 아니다.** 그 묶음에는 l/s·누출 가중치가 없다. 새 반입 목록은 ARCHITECTURE/WEIGHTS.manifest를 따른다.

연결 작업 「Clip2Safety 기반 PPE 시스템 설계 (3)」(`codex://threads/01a104c4-f8ff-7052-8a1e-5b2fa069ea26`)도 읽었다. 해당 작업의 최신 범위는 화학 보호복 페이지의 카탈로그·상담·조합·구매 링크다. 그 작업의 Vercel/공개 페이지 계획을 본 감시 MVP의 완료 조건으로 자동 추가하지 않았다. 별도 DOCX 작성 폴더 `docs/hackathon_prd_20261009`는 수정하지 않는다.

## 6. 해커톤 공개와 아직 하지 않은 작업

[공식 Luma 안내](https://luma.com/f7h7onav)에서 빈 저장소 등록(README 없는 상태), 사전 작업 사용 시 출처·사전/당일 범위 공개, AI 코딩 도구 Codex, 10/9 17:00 마감, 1차 4분 데모·발표, 저장소/심사 SHA·Codex 기록·PDF·데모 링크 제출을 확인했다. 공식 상세 홈페이지의 본문은 이번 조회에서 확보하지 못해 외부 API의 모든 세부 조건을 확정하지 않는다. API 허용은 사용자 확인 조건이다.

**가중치와 설계만 반입하고 새 코드를 작성하는 것은 사용자 선택이다.** 사전 코드 전면 금지라는 공식 규정으로 설명하지 않는다. 소스 복사를 하지 않아도 기존 학습 가중치·실험·알려진 실패·선정한 사례·설계 지식은 사전 준비다.

[발표 실행서](/home/giwon/Downloads/케미가드_심사위원별_대응전략_발표실행서.pdf)의 장갑/액체 시연·20장면·세부 시간표는 작성자의 제안이며, 모두 공식 의무 또는 실제 시험 완료가 아니다. 본 PRD는 검증한 범위를 화학복과 가시적 연무/분출로 좁혔다.

| 당일 계획 | 현재 상태 |
|---|---|
| 새 repo·웹 앱·policy/registry/evidence 스키마 | 미구현 |
| l + Pose + SigLIP + smoke + Responses 통합·GPU 스케줄 | 미실행 |
| Mac에서 PC 원격 시작/중지·화면 확인 | 미검증 |
| 준비물 폴더로 가중치 배치·도착지 hash 확인 | 2026-10-09 완료: 실제 파일 12개 이동, SHA256 전부 일치 |
| 모델 클래스·오프라인 로딩 실행 확인 | 미수행 |
| 새로운 허용 사진·시연 영상 확보 및 등록 | 미수행 |
| 새로운 촬영 그룹 별도 평가·실패 fixture·당일 비교표 | 미수행 |
| 실제 신규 이벤트 알림·사람 검토·리허설 녹화 | 미수행 |
| 당일 최종 SHA·PDF·Codex 기록·데모 링크 제출 | 미수행 |

최초 문서 작성 작업은 세 문서와 모델 manifest·문서 검수 기록 작성이었다. 모델 학습·추론·외부 모델 API 호출·성능 시험·서비스 재시작·기존 코드/DB/가중치 변경을 하지 않았다. 기존 기록의 완료와 이번에 새로 완료한 일을 구분한다.

## 7. 준비물 폴더 정리 — 2026-10-09 추가 완료

사용자 요청으로 권장 가중치 4종과 예비 사람 모델 1종을 [해커톤 준비물 1의 models](<../해커톤 준비물 1/models/>)에 배치했다. SigLIP 설정 파일까지 총 12개·1,642,465,396 bytes이며, 이동 후 SHA256이 사전 기록과 모두 일치했다. 준비물의 파일은 실제 파일이고 원래 경로에는 기존 프로젝트용 연결을 남겼다. 기존 준비물 폴더의 영상·다른 모델은 덮어쓰거나 삭제하지 않았다.

이 문서 묶음은 `/home/giwon/Downloads/해커톤 준비물 prd`로 이동했다. 파일 배치·무결성 확인은 사전 준비의 추가 완료이며, 새 앱 구현·모델 로딩·당일 성능 시험 완료를 뜻하지 않는다. [이동 검수 기록](relocation_audit.json), [모델 목록](WEIGHTS.manifest.json). 과거 실험의 입력·출력 근거는 원래 프로젝트에 남아 있으므로 근거 링크는 이 PC에서 참조하는 경로다.
