from pathlib import Path

exec(compile(Path(__file__).with_name('docx_layout.py').read_text(), 'docx_layout.py', 'exec'))

for border in list(doc.styles.element.iter(qn('w:pBdr'))):
    border.getparent().remove(border)

footer.runs[0].text = '화학보호복 페이지 PRD 1.0  |  '
footer.paragraph_format.line_spacing = Pt(11)


def page_architecture():
    img = Image.new('RGB', (2000, 440), 'white')
    draw = ImageDraw.Draw(img)
    fs = ImageFont.truetype(FONTFILE, 30, index=1)
    small = ImageFont.truetype(FONTFILE, 26, index=1)
    bold = ImageFont.truetype(FONTFILE, 31, index=1)

    def box(x, y, w, title, sub):
        draw.rounded_rectangle((x, y, x+w, y+120), 12, fill='#F0F5F8', outline='#B7C5CE', width=2)
        draw.text((x+18, y+18), title, font=fs, fill='black')
        draw.text((x+18, y+70), sub, font=small, fill='#34444F')

    def arrow(x1, y, x2):
        draw.line((x1, y, x2-10, y), fill='#34444F', width=4)
        draw.polygon([(x2, y), (x2-15, y-10), (x2-15, y+10)], fill='#34444F')

    draw.text((18, 0), '기존 구현', font=bold, fill='black')
    box(18, 51, 430, '로컬 홈페이지', '카탈로그  조합 초안')
    box(557, 51, 570, '로컬 Python API', '물질 근거 조회  응답 검증')
    box(1240, 51, 740, 'Codex App Server', '현재 PC 로그인 기반 상담')
    arrow(455, 110, 547)
    arrow(1135, 110, 1230)
    draw.text((18, 217), '해커톤 구현', font=bold, fill='black')
    box(18, 270, 430, 'Vercel 홈페이지', '같은 제품과 조합 화면')
    box(557, 270, 570, '별도 HTTPS Python API', '기존 조회와 JSON 계약 유지')
    box(1240, 270, 740, 'Responses API', '서버 API 키로 새 상담 연결')
    arrow(455, 330, 547)
    arrow(1135, 330, 1230)
    path = OUT / 'page_architecture.png'
    img.save(path)
    return path


# 1
doc.add_paragraph('화학보호복 페이지 제품 요구사항 문서', style='Title')
doc.add_paragraph('기존 구현과 해커톤 구현', style='Subtitle')
p('버전 1.0  |  기존 구현 기준 2026년 10월 8일  |  해커톤 구현 10월 9일', size=10)
p('대상은 화학보호복 페이지 /kit-catalog/다. 사업장에서 사용하는 물질과 작업 조건을 입력하면, 보호복과 화학장갑·장화·호흡·안면 보호구의 검토 조합을 제안하고 제품 근거와 국내 구매 경로를 보여 준다.')
p('우리는 현재 로컬에서 구현한 페이지를 기준선으로 남기고, 내일 Vercel 화면과 API 챗봇을 연결한 해커톤 데모를 만든다. 이 PRD는 영상 분석·감시 화면·모델 실험·Mac 반입 계획을 다루지 않는다.')
h('구현 범위')
table(['구분', '범위', '완료의 의미'], [
    ('기존 구현', '카탈로그·물질 상담·조합 추천·실제 색상 비교·구매 링크·브라우저 초안', '현재 PC에서 동작한 기능. 공개 배포와 회사 사용 승인은 미완료.'),
    ('해커톤 구현', 'Vercel 홈페이지·Responses 상담 API·근거/오류 표시·초안 유지', '공개 미리보기에서 한 작업의 검토 후보 선택과 JSON 내보내기까지 동작.'),
    ('후속 범위', '회사별 로그인·영구 회사 DB·합성 사진 생성·승인 후 감지 DB 연동', '이번 페이지 P0 완료 조건에 포함하지 않음.')
], [1.03, 3.65, 2.38])
h('사용자와 핵심 흐름')
p('안전 담당자가 물질·농도·온도·작업·노출 조건을 입력한다. 챗봇이 근거 있는 제품 후보를 제시하면 담당자는 조합과 남은 확인을 비교하고, 조합 하나를 초안으로 선택한다. 구매 링크와 검토 JSON을 확인할 수 있다.')
bullet('제품 성능과 구성품 연결 근거를 먼저 검토하고, 실제 판매 색상으로 작업 간 구분을 확인한다.')
bullet('보호복의 형식, 호흡보호구·장갑·장화의 기준을 품목별로 표시한다. 다른 품목을 보호복 1~4형식으로 일괄 분류하지 않는다.')
bullet('챗봇의 선정 결과는 검토 후보다. 미확인 품목과 조건을 남기며 전체 세트나 안전 적합성을 자동 승인하지 않는다.')
h('성공 기준')
p('공개 HTTPS 페이지에서 검색→상담→출처 확인→조합 선택→저장·JSON 내보내기를 한 사례로 완료한다. 기존 기능과 당일 구현을 구분해 기록한다. 요구되지 않은 규칙 엔진·다중 에이전트·새 DB를 선제적으로 추가하지 않는다.')

# 2
page('기존 구현')
p('현재 로컬 주소는 http://127.0.0.1:34401/kit-catalog/다. 다음 기능은 기존 구현이며 내일 새로 구현한 성과로 세지 않는다. [S1 S2 S3]')
table(['ID', '기능', '확인된 상태'], [
    ('B01', '제품 탐색', '44개 제품 검색·품목/형식/색상 필터·제품 카드. 제품 출처 기록 150개. 43개 제품에 국내 판매·견적 경로 연결. 전체 국내 시장이나 실재고 확인은 아님.'),
    ('B02', '사진과 구매 링크', '44개 제품의 로컬 사진 확보. 15개는 대표 사진으로 정확 판매 스타일과의 일치 미확정. 구매·제조사 링크 연결. 사진 재배포 권리 미확인.'),
    ('B03', '물질 상담', '브라우저→Python→Codex App Server의 단일 상담 에이전트. 작업 조건을 검토하고 최대 3개 조합과 후보·질문·근거를 구조화 출력.'),
    ('B04', '실시간 물질 조회', '정확 CAS로 DuPont 제품 3종의 공식 원단시험표 조회. 시험 조건·원문 표·matched/not_found/error 보존. 다른 제품과 법규는 수합 근거 중심.'),
    ('B05', '조합 선택', '보호복·화학장갑·장화·호흡/안면 후보 비교. 서로 다른 제조사도 후보가 될 수 있음. 구성품 호환은 근거가 있을 때만 제안. 제외·미확인 품목은 통과시키지 않음.'),
    ('B06', '작업별 색상 구분', 'use_type과 work_group 저장. 다른 형식 또는 같은 형식의 다른 작업에서 동일한 실제 보호복 색이면 충돌 표시. 형식별 고정색 없음.'),
    ('B07', '초안 저장', '여러 조합의 브라우저 저장·복원·수정·JSON 내보내기. 근거와 남은 확인 보존. 편집 시 추천 근거 무효화. 승인·감지 등록·합성 생성은 false.'),
    ('B08', '현재 운영 경계', 'localhost Origin 제한·전역 상담 잠금으로 동시 1건. 회사 로그인·회사별 서버 저장·공개 배포 미구현. PC의 Codex 로그인에 의존.')
], [.53, 1.23, 5.30], 10.2)
h('현재 확인한 상담 사례')
p('황산과 수산화나트륨의 별도 이송 작업을 입력해 회색과 노랑의 서로 다른 검토 후보를 생성했다. 실제 상담 1회는 84.53초였다. 장화·호흡 품목 등 일부 항목은 비워 두고 남은 확인을 표시했다. 기능 확인 결과이며 실제 사업장 사용 승인이나 정확도 수치가 아니다.')
p('사진 확보와 제품 실물 일치, 국내 판매 경로와 실재고, 원단시험과 완제품 적합성은 각각 다른 확인 상태다. 현재 자료의 표시 상태를 공개 페이지에서도 보존한다.', size=10.5)

# 3
page('해커톤 구현 연결 구조')
p('내일 기본안은 기존 페이지의 화면과 제품 자료를 유지하고, 상담 연결을 공개 환경에 맞게 바꾸는 것이다. Vercel에는 화면을 올리고 별도 HTTPS Python API에 Responses 상담 어댑터를 둔다. [O1 O2 O3]')
doc.add_picture(str(page_architecture()), width=Inches(7.06))
doc.paragraphs[-1].paragraph_format.line_spacing = 1.0
h('화면에서 이어지는 흐름')
bullet('입력: 물질명/CAS, 농도, 온도, 작업, 노출 방식, 별도 작업인지 혼합·동시 노출인지 받는다. 모르는 항목은 질문한다.')
bullet('근거 조회: 현재의 제조사 조회와 제품/출처 JSON을 재사용한다. 조회 가능한 범위와 미조회 품목을 구분한다.')
bullet('후보 생성: 실제 카탈로그 ID로 구성한 최대 3개 조합, 제품별 이유, 구매 링크, 미확인 정보를 반환한다.')
bullet('색상 비교: 다른 형식·작업 그룹의 실제 보호복 색을 비교한다. 성능 근거가 있는 다른 색 제품이 없으면 충돌 또는 대안 미확인을 남긴다.')
bullet('선택과 저장: 사용자가 조합 하나를 선택하고 브라우저 초안과 JSON으로 저장한다. 자동 승인이나 자동 감지 등록으로 전환하지 않는다.')
h('최소 기술 선택')
p('상담은 단일 에이전트 흐름으로 시작한다. Agents SDK나 Agents API를 추가로 붙이지 않고 Responses API와 필요한 조회 도구만 연결한다. 모델 이름은 서버 설정으로 지정한다. 기존 구조화 응답을 유지해 화면을 다시 만들지 않는다.')
p('Vercel의 API 경로를 별도 서버로 전달하거나 설정된 HTTPS API 주소를 사용한다. Nginx는 별도 서버 호스팅 방식에 따라 선택한다. Vercel 앞의 추가 Nginx는 필수 요구사항이 아니다.')
p('Vercel Functions만 쓰는 대안은 추후 선택할 수 있다. 그때는 기존 상시 Python/Codex 프로세스를 그대로 옮기지 않는다. 로컬 파일이나 /tmp를 영구 회사 DB로 사용하지 않는다. 이번 P0 저장은 기존 브라우저 초안과 JSON이다. [O3 O4]', size=10.5)

# 4
page('해커톤 구현 필수 요구사항')
p('H01부터 H05까지는 P0다. 배포 계정과 서버 API 키는 당일 의존성이다. 오늘 문서 작성으로 구현·유료 호출·배포를 실행한 것은 아니다.')
requirement('H01', 'Vercel 미리보기',
    '화학보호복 페이지를 HTTPS에서 제공한다. 정적 파일과 API 경로를 환경별로 설정하고 페이지에 필요한 공개 파일만 배포한다.',
    '다른 기기에서 검색·필터·제품 카드·구매 링크·조합 선택이 동작한다. 키·사적 DB·연구 자료가 공개 파일에 포함되지 않는다.')
requirement('H02', 'Responses 상담 API',
    '카탈로그 전용 어댑터로 모델 연결을 교체한다. 현재 제품·출처 자료, 제조사 조회, 구조화 JSON을 유지하고 후속 질문을 같은 대화에서 처리한다.',
    '페이지 요청이 실제 API 응답과 근거를 받아 조합 카드로 표시된다. 제품/출처 ID를 등록 목록으로 검증한다. 기존 개인 Codex 인증으로 자동 우회하지 않는다.')
requirement('H03', '최소 공개 접근과 사용량 제한',
    '서버에만 키를 저장한다. 시연용 접근 제어, 요청 수·비용 제한, 상담 중지 기능을 둔다. 허용 Origin은 공개 주소에 맞게 설정한다.',
    '허용되지 않은 요청과 과도한 요청을 처리 전에 거절한다. 브라우저와 오류 응답에 키가 없다. Origin 검사만 사용자 인증으로 취급하지 않는다.')
requirement('H04', '근거와 오류 표시',
    '상담 중·완료·조회 실패·시간 초과를 구분한다. 원문 출처, 원단시험 조건, 조회 시각, 미확인 품목을 보여 준다.',
    'matched/not_found/error가 보존된다. 원단시험값을 완제품 승인이나 착용 가능 시간으로 표현하지 않는다. 실패 후 기존 초안은 남고 재요청은 사용자 동작으로 수행한다.')
requirement('H05', '초안 보존과 공개 사진 처리',
    '기존 저장·복원·JSON 내보내기를 유지한다. 공개 사용 근거가 있는 사진만 배포하고 미확인 사진은 출처 링크나 자리 표시로 대체한다.',
    '새로고침 뒤 초안과 근거를 복원한다. approved/runtime_registration/synthesis_created는 false다. 대표 사진 상태와 실제 판매 색상 표시를 유지한다.')

# 5
page('추천과 데이터의 판단 기준')
p('과도한 물질별 고정 룰을 만들지 않는다. 챗봇은 작업 조건과 제공된 근거를 검토하고, 서버는 제품/출처 ID·응답 형식·제외 상태 등 필수 경계만 검증한다.')
table(['상황', '페이지 동작', '확정하지 않을 것'], [
    ('같은 작업의 대안', '같은 형식·작업 그룹이면 같은 색 대안 허용', '대체 후보를 별도 작업의 색상 충돌로 간주하지 않음'),
    ('형식이나 작업이 다름', '같은 색이면 충돌 표시하고 근거 있는 실제 색 대안 조회', '색상만 다른 가상 SKU 생성이나 사진 변색'),
    ('산/염기 별도 작업', '각 작업 조건과 제품 근거를 따로 검토하고 작업 그룹 구분', '산/염기라는 이름만으로 모든 제품을 고정 배정'),
    ('혼합액·동시 노출', '공통 노출 조건을 질문하고 근거 부족 표시', '순물질 두 시험의 교집합으로 혼합물 적합성 승인'),
    ('형식/작업/색 미상', '구분 확인 전 또는 추가 질문 표시', '사업장 전체 색상 구분 완료'),
    ('품목 근거 없음', '부분 조합과 missing_information 반환', '빈 항목을 근거 없는 제품으로 채워 전체 세트 승인')
], [1.23, 2.98, 2.85], 10.2)
h('유지할 데이터 계약')
table(['데이터', '주요 필드', '보존 원칙'], [
    ('작업 입력', '물질/CAS·농도·온도·작업·노출', '질문의 물질만 조회. 없는 CAS나 조건은 만들지 않음.'),
    ('추천 조합', 'product_ids·use_type·work_group·근거·missing_information', '기존 응답 구조 유지. 실제 제품/출처와 제외 상태 검증.'),
    ('제품 근거', '정확 모델·시험 조건·인증 확인 수준·국내 구매 링크·사진 상태', '형식 적합 근거와 개별 인증 확인 수준을 구분. 미확인 표시 유지.'),
    ('저장 초안', '선택 품목·작업 그룹·검토 근거·세 상태 플래그', '브라우저/JSON 저장. 편집 시 근거 재검토. 승인/등록/합성 false.')
], [1.23, 2.98, 2.85], 10.2)
h('후속 범위')
p('회사별 로그인·영구 서버 DB·승인 권한·자동 합성 착용사진·감지 DB 연동은 후속 제품화에서 다룬다. 이번 페이지 P0에 새 벡터 DB·대규모 법규 엔진·전체 시장 크롤링·영상 기능을 추가하지 않는다.')

# 6
page('당일 실행과 완료 확인')
table(['순서', '당일 할 일', '남길 결과'], [
    ('1 기준선', '페이지 파일/자료와 변경 범위 확인. 배포 계정·키 준비.', '기존 구현과 당일 구현 목록'),
    ('2 API 연결', 'Responses 어댑터·제조사 조회·기존 JSON 연결.', '상담 응답·근거·오류 상태'),
    ('3 공개 화면', 'Vercel과 HTTPS API 연결. 접근/사용량 제한.', '미리보기 URL·배포 버전'),
    ('4 최소 확인', '한 작업의 상담→선택→저장/복원→JSON 내보내기.', '동작 결과와 남은 확인'),
    ('5 인계', '확인된 경로 동결. 변경 파일·설정·다음 작업 기록.', '데모와 최신 핸드오프')
], [1.05, 3.45, 2.56], 10.2)
h('필요한 확인만 수행')
bullet('실제 상담 1사례에서 제품/출처 일치, 조건 보존, 색상 구분, 초안 저장·복원·내보내기를 확인한다. 후속 질문은 같은 대화에서 확인한다.')
bullet('정보 부족 1사례와 모의 오류 1사례로 부분 조합/질문, 오류 표시, 기존 초안 보존을 확인한다. 실패를 유료 모델로 반복 호출하지 않는다.')
bullet('공개 경계에서 키 미노출, 허용되지 않은 요청 차단, 공개 사진 목록만 확인한다. 광범위한 반복 모델 시험은 하지 않는다.')
p('배포 계정이나 API 설정이 준비되지 않으면 로컬 계약을 완성하고 공개 배포 미완료를 기록한다. 현장 안전 적합성, 전체 품목 확정률, 일정한 응답 시간은 시연 성공으로 주장하지 않는다.', size=10.5)
h('근거와 핸드오프')
for label, target in [
    ('S1 화학보호복 페이지 처리 설명', ROOT / 'demo/video-gallery/kit-catalog/process.md'),
    ('S2 기존 상담 서버와 조회 도구', ROOT / 'catalog_chat_server.py'),
    ('S3 작업별 조합과 색상 확인', ROOT / 'research/work_group_colours_20261007/README.md'),
    ('전체 핸드오프', ROOT / 'HANDOFF.md'),
]:
    link(label, target.as_uri())
link('O1 Codex App Server 인증 조건', 'https://learn.chatgpt.com/docs/app-server')
link('O2 Responses API와 에이전트 선택', 'https://developers.openai.com/api/docs/guides/agents')
link('O3 Vercel 외부 API rewrites', 'https://vercel.com/docs/routing/rewrites')
link('O4 Vercel Functions 런타임과 파일시스템', 'https://vercel.com/docs/functions/runtimes')
p('공식 기술 근거 확인 2026년 10월 8일. 개인 Codex App Server 인증은 상업·호스팅 서비스용으로 허용되지 않으므로 새 서버 API 연결을 사용한다. baseline_snapshot.json은 페이지와 상담 코드의 SHA256 인덱스이며 소스·DB·키를 복제하지 않는다.', size=10)

for border in list(doc.element.iter(qn('w:pBdr'))):
    border.getparent().remove(border)
doc.core_properties.title = '화학보호복 페이지 제품 요구사항 문서'
doc.core_properties.subject = '기존 구현과 2026년 10월 9일 해커톤 페이지 구현'
doc.core_properties.author = '케미가드 팀'
doc.core_properties.keywords = 'PRD, 화학보호복, 카탈로그, 챗봇, 기존 구현, 해커톤 구현'
doc.save(FILE)

paths = [
    'demo/video-gallery/kit-catalog/index.html',
    'demo/video-gallery/kit-catalog/app.js',
    'demo/video-gallery/kit-catalog/style.css',
    'demo/video-gallery/kit-catalog/catalog-data.json',
    'demo/video-gallery/kit-catalog/process.md',
    'catalog_chat_server.py', 'chemical_live_lookup.py',
    'research/work_group_colours_20261007/README.md',
]
snapshot = {
    'document_version': '1.0',
    'scope': 'Chemical PPE kit-catalog page only; video/operations/model/contest carry scope excluded',
    'prepared_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
    'baseline_date': '2026-10-08', 'hackathon_date': '2026-10-09',
    'root': str(ROOT), 'git_repository': False,
    'note': 'Hash index only; no source, media, DB or secrets copied. No model call or deployment performed.',
    'files': [],
}
for rel in paths:
    item = ROOT / rel
    snapshot['files'].append({'path': rel, 'bytes': item.stat().st_size,
                              'sha256': hashlib.sha256(item.read_bytes()).hexdigest()})
(OUT / 'baseline_snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'docx': str(FILE), 'scope': snapshot['scope']}, ensure_ascii=False))
