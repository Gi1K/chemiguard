"""Live, unauthenticated DuPont fabric evidence for verified catalog models.

Only the allowlisted product pages below are fetched. No model, credentials,
browser session, garment selection rules, or third-party service is involved.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
import re
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PRODUCT_PAGES = {
    "TYCHEM_2000_YELLOW": {
        "title": "DuPont Tychem 2000 TC198T YL",
        "fabric": "Tychem 2000",
        "url": "https://www.dupont.co.kr/products/tychem-2000-model-tc198t-yl.html",
    },
    "TYCHEM_6000_CHA6_GRAY": {
        "title": "DuPont Tychem 6000 F CHA6",
        "fabric": "Tychem 6000 F",
        "url": "https://www.dupont.co.kr/products/tychem-6000-f-model-cha6.html",
    },
    "TYCHEM_4000_CHZ5_WHITE": {
        "title": "DuPont Tychem 4000 S CHZ5",
        "fabric": "Tychem 4000 S",
        "url": "https://www.dupont.co.kr/products/tychem-4000-s-model-chz5.html",
    },
}

_TIMEOUT_SECONDS = 12
_MAX_PAGE_BYTES = 4 * 1024 * 1024
_SCOPE = "manufacturer_fabric_permeation_test_data"
_COLUMNS = ("chemical_name", "phase", "cas", "bt_act", "bt_0_1", "bt_1_0",
            "en_class", "sspr", "mdpr", "cum_480", "time_150", "iso_class")
_EXPECTED_HEADERS = ("위험 요소 / 화학물질 이름", "물리적 상태", "CAS", "BT Act",
                     "BT 0.1", "BT 1.0", "EN", "SSPR", "MDPR", "Cum 480",
                     "Time 150", "ISO")

METRIC_DEFINITIONS = {
    "bt_act": {"unit": "min", "meaning": "actual breakthrough at MDPR"},
    "bt_0_1": {"unit": "min", "threshold": "0.1 µg/cm²/min"},
    "bt_1_0": {"unit": "min", "threshold": "1.0 µg/cm²/min"},
    "en_class": {"standard": "EN 14325"},
    "sspr": {"unit": "µg/cm²/min", "meaning": "steady state permeation rate"},
    "mdpr": {"unit": "µg/cm²/min", "meaning": "minimum detectable permeation rate"},
    "cum_480": {"unit": "µg/cm²", "meaning": "cumulative mass after 480 min"},
    "time_150": {"unit": "min", "meaning": "time to cumulative mass 150 µg/cm²"},
    "iso_class": {"standard": "ISO 16602"},
}


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _PermeationTable(HTMLParser):
    """Retain cell HTML/footnotes without concatenating superscripts into values."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.tables_found = 0
        self.headers = []
        self.rows = []
        self.row = []
        self.cell = None
        self.sup_depth = 0
        self.row_is_header = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table" and attrs_dict.get("id") == "item_permeation":
            self.active = True
            self.tables_found += 1
        if not self.active:
            return
        if tag == "tr":
            self.row = []
            self.row_is_header = False
        if tag in ("th", "td"):
            self.cell = {"text": [], "html": [], "footnotes": []}
            self.row_is_header = self.row_is_header or tag == "th"
            self.sup_depth = 0
        elif self.cell is not None:
            self.cell["html"].append(self.get_starttag_text())
            if tag == "sup":
                self.sup_depth += 1

    def handle_data(self, data):
        if self.active and self.cell is not None:
            self.cell["html"].append(escape(data, quote=False))
            self.cell["footnotes" if self.sup_depth else "text"].append(data)

    def handle_endtag(self, tag):
        if not self.active:
            return
        if tag in ("th", "td") and self.cell is not None:
            cell = self.cell
            self.row.append({
                "value": " ".join("".join(cell["text"]).split()),
                "html": "".join(cell["html"]),
                "footnotes": [s.strip() for s in cell["footnotes"] if s.strip()],
            })
            self.cell = None
        elif self.cell is not None:
            self.cell["html"].append(f"</{tag}>")
            if tag == "sup":
                self.sup_depth = max(0, self.sup_depth - 1)
        if tag == "tr" and self.row:
            if self.row_is_header:
                values = [c["value"] for c in self.row]
                if any(values) and not self.headers:
                    self.headers = values
            else:
                self.rows.append(self.row)
        if tag == "table":
            self.active = False


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _page_notes(page):
    """Decode only the public explanatory JSON literal; never execute scripts."""
    text = ""
    match = re.search(r'hazardPopUpData\s*=\s*"((?:\\.|[^"\\])*)"\s*;', page)
    if match:
        try:
            literal = re.sub(r"\\x([0-9a-fA-F]{2})", r"\\u00\1", match.group(1))
            payload = json.loads(json.loads('"' + literal + '"'))
            parser = _Text()
            parser.feed(payload.get("importantNote", ""))
            text = " ".join(" ".join(parser.parts).split())
        except (ValueError, TypeError, AttributeError):
            pass
    revision_match = re.search(r"Latest Update Permeation Data:\s*(\d{1,2}/\d{1,2}/\d{4})", text)
    revision = revision_match.group(1) if revision_match else None
    notes = [
        "Retrieved manufacturer fabric evidence; suitability is unassessed.",
        "Breakthrough time is not safe wearing duration.",
        "Keep different concentrations, phases, temperatures and compound values separate.",
        "imm means less than 10 minutes; blank cells mean no reported value.",
    ]
    for pattern in (r"All chemicals have been tested.*?unless otherwise stated\.",
                    r"The tests were performed.*?unless otherwise stated\."):
        found = re.search(pattern, text)
        if found:
            notes.append(found.group(0))
    standards = [s for s in ("EN369", "ASTM F739", "ASTM F1383", "EN 374-3",
                            "EN ISO 6529", "ASTM D6978") if s in text]
    return revision, notes, standards


def _footnote_definitions(page):
    section = re.search(r'<div\b[^>]*id="permeationDatatestingDetails"[^>]*>([\s\S]*?)</div>', page)
    definitions = {}
    if section:
        for label, definition in re.findall(r'<li>\s*<label>(.*?)</label>([\s\S]*?)</li>', section.group(1)):
            label_parser, definition_parser = _Text(), _Text()
            label_parser.feed(label)
            definition_parser.feed(definition)
            key = " ".join(" ".join(label_parser.parts).split())
            if key in {"*", "8", "imm", "nm", "na", "N/A", "sat"}:
                definitions[key] = " ".join(" ".join(definition_parser.parts).split())
    return definitions


def _evidence_row(headers, cells, fabric):
    values = dict(zip(_COLUMNS, [c["value"] for c in cells]))
    label = values["chemical_name"]
    concentration = re.search(r"[<>]?\s*\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*(?:%|ppm)", label)
    temperature = re.search(r"[-−]?\d+(?:\.\d+)?\s*[°º]\s*[CF]", label)
    return {
        **values,
        "fabric": fabric,
        "concentration": concentration.group(0).strip() if concentration else None,
        "temperature": temperature.group(0) if temperature else None,
        "conditions_raw": re.findall(r"\([^)]*\)", label),
        "raw_values": dict(zip(headers, [c["value"] for c in cells])),
        "cell_html": {h: c["html"] for h, c in zip(headers, cells) if c["footnotes"]},
        "footnotes": {h: c["footnotes"] for h, c in zip(headers, cells) if c["footnotes"]},
    }


def _fetch_product(product_id, cas_numbers):
    product = PRODUCT_PAGES[product_id]
    source = {
        "product_id": product_id, "title": product["title"], "url": product["url"],
        "retrieved_at": None, "status": "error", "rows": [], "scope": _SCOPE,
        "revision": None, "notes": [], "queries": [],
    }
    started = monotonic()
    try:
        request = Request(product["url"], headers={"User-Agent": "PPE-Catalog-ChemicalLookup/1.0"})
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            if urlparse(response.url).hostname not in {"www.dupont.co.kr", "www.dupont.com"}:
                raise ValueError("Unexpected manufacturer redirect host")
            body = response.read(_MAX_PAGE_BYTES + 1)
            source.update({"http_status": response.status, "resolved_url": response.url,
                           "last_modified": response.headers.get("Last-Modified"),
                           "etag": response.headers.get("ETag")})
        source["retrieved_at"] = _utc_now()
        if len(body) > _MAX_PAGE_BYTES:
            raise ValueError("Manufacturer page exceeded the response size limit")
        page = body.decode("utf-8", errors="strict")
        parser = _PermeationTable()
        parser.feed(page)
        if (parser.tables_found != 1 or parser.active
                or tuple(h.casefold() for h in parser.headers)
                != tuple(h.casefold() for h in _EXPECTED_HEADERS) or not parser.rows
                or any(len(row) != 12 for row in parser.rows)):
            raise ValueError("Expected complete 12-column manufacturer permeation table is unavailable")
        source["revision"], source["notes"], source["page_test_standards"] = _page_notes(page)
        source["footnote_definitions"] = _footnote_definitions(page)
        source["table_row_count"] = len(parser.rows)
        source["headers"] = parser.headers
        requested = set(cas_numbers)
        source["rows"] = [_evidence_row(parser.headers, row, product["fabric"])
                          for row in parser.rows if row[2]["value"] in requested]
        source["queries"] = [{"cas": cas, "status": "matched" if any(r["cas"] == cas for r in source["rows"])
                              else "not_found"} for cas in cas_numbers]
        source["status"] = "matched" if source["rows"] else "not_found"
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        source["retrieved_at"] = source["retrieved_at"] or _utc_now()
        source["error"] = {"type": type(error).__name__, "message": str(error)[:240]}
        if isinstance(error, HTTPError):
            source["http_status"] = error.code
        source["notes"] = ["Source retrieval or parsing failed; this is not chemical absence."]
        source["queries"] = [{"cas": cas, "status": "error"} for cas in cas_numbers]
    source["elapsed_seconds"] = round(monotonic() - started, 3)
    return source


def lookup_chemicals(cas_numbers: list[str], product_ids: list[str] | None = None) -> dict:
    """Fetch up to three verified pages afresh and return exact-CAS fabric rows.

    Source/individual query status is matched, not_found, or error. not_found
    requires a successfully parsed full product table. Values stay strings;
    no product suitability assessment is performed. Invalid inputs raise ValueError.
    """
    if not isinstance(cas_numbers, list) or not 1 <= len(cas_numbers) <= 20:
        raise ValueError("cas_numbers must contain 1 to 20 CAS strings")
    if any(not isinstance(cas, str) or not re.fullmatch(r"\d{2,7}-\d{2}-\d", cas.strip())
           for cas in cas_numbers):
        raise ValueError("CAS values must use the numeric CAS format")
    queries = list(dict.fromkeys(cas.strip() for cas in cas_numbers))
    selected = list(PRODUCT_PAGES) if product_ids is None else product_ids
    if (not isinstance(selected, list) or not selected
            or any(not isinstance(pid, str) or pid not in PRODUCT_PAGES for pid in selected)):
        raise ValueError("product_ids must name verified catalog product IDs")
    selected = list(dict.fromkeys(selected))
    with ThreadPoolExecutor(max_workers=min(3, len(selected))) as executor:
        sources = list(executor.map(lambda pid: _fetch_product(pid, queries), selected))
    return {"queries": queries, "sources": sources, "scope": _SCOPE,
            "metric_definitions": METRIC_DEFINITIONS, "suitability": "unassessed"}
