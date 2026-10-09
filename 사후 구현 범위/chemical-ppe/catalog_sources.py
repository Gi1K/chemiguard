"""Official-page checks for maintenance. No model claims become approvals."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit, urljoin, urlunsplit

import httpx

WATCH = json.loads(Path(__file__).with_name('catalog_watch.json').read_text())
CATEGORIES = {
    'chemical_protective_coverall': r'coverall|chemical.{0,25}suit|전신.?보호복|화학.?보호복',
    'chemical_gloves': r'glove|장갑', 'chemical_boots': r'boot|장화',
    'respirator': r'respirator|호흡|정화통', 'eye_protection': r'goggle|보안경',
    'face_shield': r'face.?shield|보안면',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def compact(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


def identity(value):
    return ''.join(c for c in compact(value) if c.isalnum())


def manufacturer(name):
    return next((m for m in WATCH['manufacturers']
                 if identity(name) in [identity(n) for n in [m['name'], *m.get('aliases', [])]]), None)


def checked_url(url, brand):
    m = manufacturer(brand)
    if not m or not isinstance(url, str) or len(url) > 1600:
        raise ValueError('허용한 제조사와 공식 URL이 필요합니다.')
    u = urlsplit(url)
    if (u.scheme != 'https' or u.username or u.password or u.port not in (None, 443)
            or not any(u.hostname == d or (u.hostname or '').endswith('.' + d) for d in m['domains'])):
        raise ValueError('등록한 제조사의 HTTPS 출처만 확인합니다.')
    return urlunsplit(('https', u.netloc.lower(), u.path or '/', u.query, ''))


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.pieces = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'template', 'svg'):
            self.skip += 1
        if tag == 'a' and not self.skip:
            self.links.append(dict(attrs).get('href', ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'template', 'svg'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.pieces.append(data.strip())


@dataclass
class Page:
    manufacturer: str
    url: str
    checked_at: str
    text: str
    sha256: str
    links: list[str]


async def fetch_page(url, brand):
    current = checked_url(url, brand)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8), follow_redirects=False,
                                 headers={'User-Agent': 'ChemiGuardCatalog/1.0', 'Accept': 'text/html'}) as client:
        for _ in range(5):
            async with client.stream('GET', current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = checked_url(urljoin(current, response.headers.get('location', '')), brand)
                    continue
                if response.status_code != 200:
                    raise ValueError(f'공식 페이지 HTTP {response.status_code}; 접근 우회 없이 보류')
                if 'text/html' not in response.headers.get('content-type', '').lower():
                    raise ValueError('현재 자동 반영은 HTML 제품 페이지를 확인합니다. PDF·사진은 별도 검토가 필요합니다.')
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 2_000_000:
                        raise ValueError('출처 페이지가 크기 한도를 초과했습니다.')
                parser = VisibleText()
                parser.feed(raw.decode(response.encoding or 'utf-8', errors='replace'))
                text = ' '.join(parser.pieces)
                if len(text) < 100:
                    raise ValueError('확인할 본문이 부족합니다. 동적 페이지는 보류합니다.')
                links = []
                for href in parser.links:
                    try:
                        link = checked_url(urljoin(current, href), brand)
                    except ValueError:
                        continue
                    if link not in links:
                        links.append(link)
                return Page(manufacturer(brand)['name'], current, now(), text,
                            hashlib.sha256(compact(text).encode()).hexdigest(), links)
    raise ValueError('공식 페이지의 이동 횟수를 초과했습니다.')


def verified_product(item, page):
    fields = {'manufacturer', 'model', 'name', 'category', 'source_url', 'category_evidence'}
    if not isinstance(item, dict) or set(item) != fields:
        raise ValueError('제품 입력에는 제조사·모델·이름·품목·공식 URL·품목 근거만 허용합니다.')
    for field in fields:
        limit = 1600 if field == 'source_url' else 180
        if not isinstance(item[field], str) or not 1 <= len(item[field].strip()) <= limit:
            raise ValueError(f'제품 {field} 형식을 확인하세요.')
    brand = manufacturer(item['manufacturer'])
    if not brand or item['category'] not in CATEGORIES or brand['name'] != page.manufacturer:
        raise ValueError('제조사 또는 보호구 품목이 일치하지 않습니다.')
    text = compact(page.text)
    for field in ('model', 'name', 'category_evidence'):
        if compact(item[field]) not in text:
            raise ValueError(f'{field} 값이 이번에 읽은 제조사 본문에 없습니다.')
    if not re.search(CATEGORIES[item['category']], item['category_evidence'], re.I):
        raise ValueError('해당 보호구 품목을 확인할 문구가 없습니다.')
    # Require model, product name and category in the same short passage, not
    # unrelated items in the page navigation or recommended-products footer.
    model = compact(item['model'])
    windows = [text[max(0, m.start()-600):m.end()+600] for m in re.finditer(re.escape(model), text)]
    if not any(compact(item['name']) in w and compact(item['category_evidence']) in w for w in windows):
        raise ValueError('정확한 모델 주변의 제품명·품목 근거를 함께 확인하지 못했습니다.')
    if item['category'] == 'chemical_protective_coverall' and re.search(r'\b(jacket|trousers|apron)\b', item['name'], re.I):
        raise ValueError('부분 보호 의복을 전신 보호복으로 자동 등록할 수 없습니다.')
    return {**item, 'manufacturer': page.manufacturer, 'source_url': page.url}
