# 사전 준비 공개

기준일: 2026-10-09. 본선 앱 개발 전에 준비된 다음 자료와 설계 지식을 사용한다.

- `사전 구현 범위/02_감시_PRD_사전실험`의 PRD, 아키텍처, 실패 사례와 사전 실험 기록.
- COCO YOLO26 Large, YOLO26n-Pose, SigLIP2 base384, FASDD smoke YOLO26s 가중치.
- 선정한 누출 CCTV 및 화학보호복 교육 영상. 파일은 로컬에서만 참조하고 Git에 재배포하지 않는다.
- 사람 추적, 원본 crop, Pose 몸통, vision-only 임베딩, 관측 TTL/세대, 연속 관측 합의, 담당자 검토 설계.
- `ppe-reference-poc/luna_decisions.py`의 API 계약과 부위 관찰 규칙을 참고했다. 기존 앱·DB·저장 예측을 복제하지 않고 새 모듈을 작성한다. 기존 코드를 참고했다는 사실도 사전 기여로 공개한다.

본선 변경: 사용자 요청에 따라 Responses 대신 `gpt-6-luna` Decisions를 기본 API로 채택하고, 사람 모델은 Medium/Large를 지원한다. Medium 가중치는 본선 준비 과정에서 추가한다.

기존 소수 사진·영상 실험의 정확도나 지연은 새 앱의 측정치가 아니다. 현재 앱에서 새로 실행한 결과는 실행 ID별로 기록한다.

자산 출처: Ultralytics YOLO26(AGPL-3.0/Enterprise), Google SigLIP2(Apache-2.0), FASDD(DOI: 10.57760/sciencedb.j00104.00103, 기존 자료의 CC BY-SA 4.0 기록). 영상별 출처는 로컬 준비물의 `metadata/sources.json`, `package_manifest.json`에 보존되어 있다. 공개 게시된 영상이라는 사실을 재배포 허가로 간주하지 않는다.
