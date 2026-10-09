본선 정리 위치 — 2026-10-09
  /home/giwon/Downloads/해커톤 본선/사전 구현 범위/01_가중치_영상
현재 영상 총 152개: 기존 묶음 115개 + 10월 9일 시작 전 추가 37개.
현재 models: PRD 권장 모델 4종·예비 1종의 12파일 + 기존 leak 표시명 가중치 1개.
전체 사전 구현 범위와 문서 위치: ../00_사전구현_범위.txt
아래는 기존 준비물 설명과 출처 기록이다.

해커톤 준비물 1 — 암모니아 영상 / FASDD 가중치

로컬에 있던 암모니아 관련 영상 출처 25개와 기존 영상 115개를 모았습니다.
출처 URL 수는 서로 다른 사고 수가 아닙니다. 동일 사건의 재게시 영상이 포함될 수 있습니다.
원래 124개 파일 경로 중 내용이 완전히 같은 9개 중복본은 하나로 합쳤습니다.
실제 파일을 복사했으므로 이 폴더 전체를 다른 PC로 옮길 수 있습니다.

먼저 볼 파일
  00_최신편집_데모/receiver_valve_centered.mp4
    방금 편집한 리시버 영상: 양쪽 96px 제거, 중앙 글자 정렬, 상단 원본 시계 유지.
  00_최신편집_데모/receiver_valve_centered_leak.mp4
    위 편집본의 FASDD 실제 탐지 박스 / leak 라벨 / confidence 포함 영상.
  03_FASDD_탐지결과/02_Elk Grove 냉동 설비실 · 2017__AqPOAPiH0Sk/elk_grove_full_leak.mp4
    옷 입은 남자가 들어오는 Elk Grove 전체 영상의 FASDD 탐지 결과.

폴더 구성
  00_최신편집_데모       2개 — 최신 중앙 편집 원본과 탐지 결과
  01_암모니아_원본       26개 — 내려받은 원본; 뉴스/편집/재게시 영상 포함
  02_암모니아_발췌본     17개 — 발췌 및 기존 추론 입력 영상
  03_FASDD_탐지결과      7개 — 기존 FASDD 분석 영상
  04_이전모델_비교       59개 — 실험 폴더명별 이전 비교 영상
  05_이전편집본          1개 — 왼쪽 벽만 제거했던 이전 편집본
  06_기타보관영상        3개 — 원본/가공 종류가 기록되지 않은 기존 파일
  models                       FASDD leak 표시명 가중치 1개
  metadata                     영상 출처, 파일 대응표, SHA256, 기존 학습/추론 기록

가중치
  models/fasdd_yolo26s_leak_best.pt
    표시명 변경본 best_leak.pt. class 0 = leak.
    학습한 대상은 smoke이고 모델 텐서는 동일합니다. 액체 누출 전용으로 재학습한 모델이 아닙니다.
  초기 모델: 일반 COCO YOLO26s. 최적 에폭: 50.
  검증 mAP50 85.12%, mAP50-95 64.68%; 별도 사진 시험 mAP50 79.86%, mAP50-95 58.55%.
  위 숫자는 FASDD 연기 사진 평가이며 암모니아 CCTV 정확도가 아닙니다.

기록 / 사용 범위
  영상별 출처와 물질·장면 확인 수준: metadata/sources.json
  폴더 내 상대 경로 / 원래 경로 / 중복 대응 / 해시: metadata/package_manifest.json
  metadata/FASDD_기존기록 안의 절대 경로는 이전 실험 당시 기록이며 현재 실행 경로가 아닙니다.
  FASDD 데이터 라이선스는 기존 실험 계획에 CC BY-SA 4.0으로 기록되어 있습니다.
  데이터 출처: https://doi.org/10.57760/sciencedb.j00104.00103
  영상의 공개 게시 여부와 학습·재배포 허용 여부는 별개이며, 이번에는 로컬 검토/데모 자료로 모았습니다.
  원본 영상 ID가 없는 FASDD 분할은 완전한 장면 독립성을 증명하지 않습니다.
  일부 영상의 암모니아 물질명은 게시자 설명 수준입니다. CCTV에 보이는 구름의 화학물질 종류를 모델이 판별하지 않습니다.

영상 출처 목록
01. 암모니아 리시버 밸브 작업
    https://www.youtube.com/watch?v=iOcGOilqYeU
02. Elk Grove 냉동 설비실 · 2017
    https://www.youtube.com/watch?v=AqPOAPiH0Sk
03. 암모니아 압력용기 파열
    https://www.youtube.com/watch?v=NPEcJhbOMWA
04. 냉동 설비실 흰 분출
    https://www.youtube.com/watch?v=uBqybTTIvtQ
05. 2019 NH3 Fertilizer Release 30K
    https://www.youtube.com/watch?v=hX_h8Hk2q4Q
06. 8 cylinder Vilter slugged with liquid ammonia 720p
    https://www.youtube.com/watch?v=gatCSASaFPw
07. AMMONIA LEAK
    https://www.youtube.com/watch?v=HVnb3Rc7it8
08. Ammonia Refrigeration Condenser Tube Failure #2
    https://www.youtube.com/watch?v=n_jLtrs8iWo
09. Catastrophic Failure of an Anhydrous Ammonia Receiver 2019
    https://www.youtube.com/watch?v=VRlxKCiikL4
10. Cold Storage NH3 Explosion and Leak
    https://www.youtube.com/watch?v=tJ_PBcOscoY
11. NH3 Catastrophic Pressure Vessel Failure - Refrigeration #3
    https://www.youtube.com/watch?v=8QZW0rKM9Aw
12. NH3 Compressed Gas Cylinder Catastrophically Fails
    https://www.youtube.com/watch?v=1h3UT_jVDY8
13. NH3 Explosion @ ice cream plant fatalities 2014
    https://www.youtube.com/watch?v=CUWCrNBzLio
14. NH3 Line Break with COVID Face Mask
    https://www.youtube.com/watch?v=4qxowQsJNpg
15. NH3 Purger Safety
    https://www.youtube.com/watch?v=Hw5vCpmRx6E
16. NH3 RV release downward discharge
    https://www.youtube.com/watch?v=C_v7wwWawPM
17. Pipe Inspections matter in NH3 processing
    https://www.youtube.com/watch?v=hMVPR8_p-QA
18. Seward 암모니아 구름 · 2007
    https://www.youtube.com/watch?v=sNkdAs1e7Cw
19. Sumykhimprom 암모니아 탱크 손상
    https://www.youtube.com/watch?v=x0vBwzl1Ox4
20. weatherford_ammonia
    https://www.youtube.com/watch?v=Eq5bHxbsgdU
21. 상하이 냉동공장 배관 사고 · 2013
    https://www.youtube.com/watch?v=13_DYJS5mKY
22. 암모니아 탱크 설비 안전밸브 방출
    https://www.youtube.com/watch?v=Ve8c9h0-dbc
23. 야간 암모니아 탱크 조작
    https://www.youtube.com/watch?v=4ZXBwQ7Fx4c
24. 중국 공장 흰 분출
    https://www.youtube.com/watch?v=y_s8VpQczB8
25. 파라과이 Ochsi 공장 · 2024
    https://www.youtube.com/watch?v=65M1EurDQV0
