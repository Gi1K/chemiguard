# 본선 구현 범위

시작일: 2026-10-09 KST. 최초 기록 커밋 이후 모든 새 코드는 본선 작업이다.

## 이번 구현

1. 작업 정책 생성과 불변 revision, 실행 시 snapshot 고정.
2. 제품 참고 사진·몸통 영역·출처 등록, SigLIP2 임베딩, 외형 후보 표시.
3. 로컬 시연 영상 선택·업로드·시작·일시정지·탐색·중지.
4. YOLO26 Medium/Large 사람 검출, ByteTrack, 원본 좌표와 Pose crop.
5. Luna Decisions API 비동기 부위별 관찰, 오류·가림·TTL·추적 세대·연속 관측 처리.
6. FASDD smoke 장면 분석과 지속 관측 사건. 사람/API와 독립적인 처리 상태.
7. 관제 화면, 사람별 상태, 사건·원본 맥락·crop·원시 응답·입력 시각 저장.
8. 담당자 확인·반려·보류 이력 추가, 실행·사건 JSON 내보내기.

화학보호복 검색·카탈로그·상담 페이지, 신규 모델 학습, 다중 카메라, 자동 설비 제어는 이번 범위에 포함하지 않는다.

## 검증 방침

사용자 요청에 따라 광범위한 성능 시험·반복 벤치마크를 생략한다. 빌드, 실제 GPU/Decisions 연결, 영상과 사건 검토의 짧은 동작 확인에 집중한다. 실행하지 않은 검증이나 외부 모델 품질을 완료로 기록하지 않는다. 구체 결과는 구현 후 추가한다.

## API 근거

- https://developers.openai.com/api/docs/guides/decisions
- https://developers.openai.com/api/reference/resources/decisions/methods/create

`POST /v1/decisions`, `model=gpt-6-luna`, inline 이미지, 이름이 있는 choice 질문을 사용한다. 선택 점수는 시연용 관찰 신호이며 현장 정확도나 안전 확률로 표시하지 않는다.
