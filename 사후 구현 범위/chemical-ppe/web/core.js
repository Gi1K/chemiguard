// Derived from the SHA256-verified 2026-10-08 prework app; existing logic, reformatted.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const colours = {
  yellow: { label: "노랑", hex: "#f3cb3e" },
  gray: { label: "회색", hex: "#92989e" },
  white: { label: "흰색", hex: "#f4f4ef" },
  green: { label: "초록", hex: "#3d9164" },
  black: { label: "검정", hex: "#252a30" },
  black_green: { label: "검정 / 녹색", hex: "#305641" },
  blue: { label: "파랑", hex: "#4379aa" },
  transparent: { label: "투명", hex: "#d0e1e7" },
  silver: { label: "은색", hex: "#b7bdc3" },
  yellow_black: { label: "노랑 / 검정", hex: "#d6b83b" },
  yellow_green: { label: "노랑 / 녹색", hex: "#d6b83b" },
  orange: { label: "주황", hex: "#e58129" },
  red: { label: "빨강", hex: "#b73638" },
  unknown: { label: "색상 확인 전", hex: "#bec3c7" },
};
const parts = [
  { id: "coverall", category: "chemical_protective_coverall", label: "보호복" },
  { id: "gloves", category: "chemical_gloves", label: "화학장갑" },
  { id: "respirator", category: "respirator", label: "호흡보호구" },
  { id: "eye_protection", category: "eye_protection", label: "눈 보호구" },
  { id: "face_shield", category: "face_shield", label: "안면보호구" },
  { id: "boots", category: "chemical_boots", label: "화학장화" },
];
const draftKeys = [
  "ppe_kit_review_draft_v4",
  "ppe_kit_review_draft_v3",
  "ppe_kit_review_draft_v2",
  "ppe_kit_review_draft_v1",
];
let data,
  ready = false,
  busy = false,
  chatSession = null,
  exportUrl;
let userMessages = [],
  recommendationEvidence = null,
  recommendedKits = [],
  savedKits = [],
  respiratoryAddons = [],
  activeKitId = null,
  activeKitReview = null;
const savedKitsKey = "ppe_worksite_kits_v1";
const product = (id) => data.products.find((p) => p.product_id === id);
const isRespiratoryAccessory = (p) =>
  p?.category === "respirator" &&
  [
    "cartridge",
    "filter",
    "holder",
    "accessory",
    "retainer",
    "adapter",
  ].includes(p.item_role);
const colour = (p) => p?.appearance?.color?.id || "unknown";
const sources = (ids) =>
  (ids || [])
    .map((id) => data.product_sources.find((s) => s.id === id))
    .filter(Boolean);
const searchKey = (value) =>
  String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}]/gu, "");

function matchesProductSearch(p, query) {
  const fields = [
    p.display_name,
    p.manufacturer,
    p.identity.model,
    p.identity.manufacturer_reference,
    ...(p.identity.seller_aliases || []),
    parts.find((part) => part.category === p.category)?.label,
  ];
  const keys = fields.map(searchKey),
    words = fields
      .join(" ")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .split(/[^\p{L}\p{N}]+/u);
  return query
    .trim()
    .split(/\s+/u)
    .map(searchKey)
    .filter(Boolean)
    .every((token) =>
      /^[a-z]$/.test(token)
        ? words.includes(token)
        : keys.some((key) => key.includes(token)),
    );
}

function link(url, title) {
  try {
    const u = new URL(url);
    return u.protocol === "https:"
      ? `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(title)} ↗</a>`
      : esc(title);
  } catch {
    return esc(title);
  }
}

function swatch(id) {
  const c = colours[id];
  return c
    ? `<span class="colour-label"><i class="swatch" style="--swatch-colour:${c.hex}" aria-hidden="true"></i>${c.label}</span>`
    : "색상 확인 전";
}

function types(p) {
  if (p?.category !== "chemical_protective_coverall") return [];
  const result = [];
  for (const c of p.certifications || [])
    for (const t of c.claimed_types || []) {
      for (const m of String(t).matchAll(
        /\btype\s*([1-6])(?:[abc]|-b)?\b|([1-6])(?:[abc])?\s*형식/gi,
      ))
        result.push(Number(m[1] || m[2]));
    }
  return [...new Set(result)].sort();
}

function certText(c) {
  const names = {
    KR_KCs: "국내 KCs",
    KCs: "국내 KCs",
    EU_CE: "유럽 CE",
    "EN/CE": "유럽 규격·제조사 표시",
    DNV_SOLAS: "선박용 DNV / SOLAS · 국내 KCs와 별도",
    KR_NIER_PPE_CONFORMITY: "유해화학물질 보호구 적합성 문서",
    NIER: "유해화학물질 보호구 적합성 문서",
    KR_KCs_SELF_DECLARATION: "자율안전확인 신고",
    KR_self_declaration: "자율안전확인 신고",
    KR_self_declaration_reference: "자율안전확인 참조",
  };
  let s = "개별 증빙 확인 전";
  if (c.status === "individual_registry_header_model_match")
    s = "페이지 머리 모델의 공식 기록 확인 · 표 참조번호/판매품 연결 확인 전";
  else if (c.individual_records?.length)
    s = "공식 모델 기록 확인 · 판매 실물 연결 확인 전";
  else if (c.status === "certificate_document_model_match")
    s = "정확 모델의 CE 문서 확인 · 국내 인증과 별도";
  else if (c.status === "manufacturer_hosted_exact_document_read")
    s = "정확 모델의 제조사 게시 DNV 문서 확인 · 현재 상태와 국내 인증은 별도";
  else if (
    [
      "manufacturer_claim",
      "manufacturer_declared",
      "manufacturer_and_supplier_claim_current_record_not_verified",
    ].includes(c.status)
  )
    s = "제조사 표시 · 개별 인증 확인 전";
  else if (
    [
      "supplier_certificate_copy",
      "supplier_certificate_copy_reviewed_current_status_not_verified",
    ].includes(c.status)
  )
    s = "공급자 인증 사본 확인 · 공식 최신 상태와 판매 실물 연결 확인 전";
  else if (c.status === "manufacturer_certificate_copy")
    s = "제조사 인증 사본 확인 · 공식 최신 상태와 판매 실물 연결 확인 전";
  else if (c.status === "manufacturer_catalog_claim")
    s = "제조사 목록 표시 · 개별 인증 확인 전";
  else if (
    c.status ===
    "supplier_performance_claim_individual_certificate_not_verified"
  )
    s = "공급자 성능 표시 · 개별 인증 확인 전";
  else if (
    c.status ===
    "historical_document_model_configuration_match_with_literal_conflict"
  )
    s = "과거 구성 문서 확인 · 문언 불일치와 현재 상태 확인 필요";
  else if (
    c.status === "manufacturer_certification_claim_and_seller_number_only"
  )
    s = "제조사 인증 표시·판매자 번호 · 개별 증명서와 현재 상태 확인 전";
  else if (c.status === "manufacturer_hosted_declaration_document_model_match")
    s = "제조사 게시 개별 신고증명서 확인 · 현재 상태와 판매 실물 연결 확인 전";
  const records =
    c.individual_records
      ?.map(
        (r) =>
          `<li>${esc(r.certificate_number)} · ${esc(r.type || "형식 확인 전")} · ${esc(r.registry_validity_label)} · ${esc(r.manufacturer_site)}${r.cancellation_date ? ` · 취소 ${esc(r.cancellation_date)}` : ""}</li>`,
      )
      .join("") || "";
  const docs = sources(c.source_ids).filter(
    (s) =>
      s.url &&
      (/\.pdf(?:$|\?)/i.test(s.url) ||
        s.kind === "manufacturer_hosted_certification_document"),
  );
  const links = [
    c.registry_query_url ? link(c.registry_query_url, "공식 조회") : "",
    ...docs.map((s) => link(s.url, "증빙 문서")),
  ]
    .filter(Boolean)
    .join(" · ");
  const references = (c.reference_documents || [])
    .map(
      (d) =>
        `<br><span class="muted">${d.model_match_status === "exact" ? "정확 모델 문서" : "유사 모델 문서 · 동등성 확인 전"}${d.document_valid_until ? ` · 문서상 만료 ${esc(d.document_valid_until)} · 현재 취소/변경 여부 별도 확인` : ""}</span>`,
    )
    .join("");
  return `<dt>${esc(names[c.system] || c.system)}</dt><dd>${esc(s)}${c.claimed_types?.length ? `<br><span class="muted">표시: ${esc(c.claimed_types.join(" / "))}</span>` : ""}${c.certificate_number ? `<br>번호: ${esc(c.certificate_number)}` : ""}${c.document_valid_until ? `<br>문서상 만료 ${esc(c.document_valid_until)} · 취소 여부 별도 확인` : ""}${references}${records ? `<ul>${records}</ul>` : ""}${links ? `<br>${links}` : ""}</dd>`;
}

function performanceMarkup(p) {
  const g = p.chemical_suitability || {},
    rows = g.performance_evidence || [];
  const resultText = (r) =>
    typeof r.result === "string"
      ? r.result
      : [
          r.result?.permeation_level != null
            ? `투과 성능수준 ${r.result.permeation_level}`
            : "",
          r.result?.degradation_percent != null
            ? `열화 ${r.result.degradation_percent}%`
            : "",
          r.result?.reported_breakthrough_time
            ? `보고된 시험 돌파시간 ${r.result.reported_breakthrough_time}`
            : "",
        ]
          .filter(Boolean)
          .join(" · ");
  const facts = rows
    .map((r) => {
      const concentration =
          r.concentration ||
          (r.concentration_percent != null
            ? `${r.concentration_percent}%`
            : "농도 미기재"),
        source = sources([r.source_id])[0];
      return `<li><strong>${esc(r.chemical_name)} ${esc(concentration)}</strong><br>${esc(resultText(r))}<br><span class="muted">${esc(r.test_standard || r.test_method || "시험방법 미기재")} · ${r.temperature_c != null ? `${esc(r.temperature_c)}℃` : "시험온도 미기재"}${r.sample_scope ? ` · ${esc(r.sample_scope)}` : ""}</span>${r.note ? `<p>${esc(r.note)}</p>` : ""}${source ? `<br>${link(source.url, "원본 근거")}` : ""}</li>`;
    })
    .join("");
  const notes = [
    ...(p.manufacturer_target_substances?.length
      ? [
          `제조사 표시 대상: ${p.manufacturer_target_substances.join(" · ")}. 실제 노출 조건과 완성 구성은 별도 검토합니다.`,
        ]
      : []),
    ...(g.notes || []),
    ...(p.compatibility?.notes || []),
  ];
  if (!facts && !notes.length) return "";
  return `<details class="certificate-details"><summary>물질·부품 적용 근거</summary>${facts ? `<ul class="performance-list">${facts}</ul><p class="small muted">시험 조건의 결과이며 현장 안전 사용시간이나 실제 혼합물 적합성 승인이 아닙니다.</p>` : ""}${notes.map((n) => `<p class="small muted">${esc(n)}</p>`).join("")}</details>`;
}

function stockLabel(s) {
  return (
    {
      unknown: "재고 미확정",
      seller_reported_zero: "판매자 표시: 재고 0",
      seller_reported_sold_out: "판매자 표시: 품절",
    }[s] || "실재고 미확정"
  );
}

function purchases(p) {
  if (p.domestic_purchase?.length)
    return p.domestic_purchase
      .map(
        (s) =>
          `<p class="small">${link(s.url, s.seller)}<br><span class="muted">${s.stock_evidence_level === "inquiry_only" ? "국내 견적 문의" : s.exact_style_match ? "모델 수준 연결 확인" : "정확 스타일 연결 확인 전"} · ${esc(stockLabel(s.stock_status))}</span></p>`,
      )
      .join("");
  const s = sources(p.source_ids).find((s) =>
    ["manufacturer_product_page", "manufacturer_product"].includes(s.kind),
  );
  return `<p class="small">${s ? link(s.url, "해외 제조사 자료") : "구매처 자료 확인 전"}<br><span class="muted">국내 판매·수입처 미확인</span></p>`;
}

function showTab(name) {
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.tab === name)),
    );
  ["products", "sets", "chat", "kit"].forEach(
    (id) => ($(id + "Panel").hidden = id !== name),
  );
  $("storeHero").hidden = name !== "products";
  $("catalogMetrics").hidden = name !== "products";
}

function renderTypeGuide() {
  const g = data.classification_guide;
  if (!g) {
    $("typeGuide").textContent = "형식별 기준 자료를 확인 중입니다.";
    return;
  }
  const table = (headers, rows) =>
    `<div class="table-scroll"><table><thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  $("typeGuide").innerHTML = `<p>${esc(g.summary)}</p>${table(
    ["보호복 형식", "보호복 기준", "호흡·안면", "장갑·장화"],
    g.clothing_types.map((t) => [
      `${t.type}형식`,
      t.description,
      t.respiratory_face,
      t.gloves_boots,
    ]),
  )}<h3>함께 쓰는 보호구는 품목별로 확인합니다</h3>${table(
    ["품목", "확인할 기준"],
    g.component_criteria.map((c) => [c.label, c.description]),
  )}<p class="small muted">${esc(g.limit)}</p><div class="sources">${sources(
    g.source_ids,
  )
    .map((s) => link(s.url, s.title))
    .join(" · ")}</div>`;
}

function setBusy(value) {
  busy = value;
  $("chatSend").disabled = busy || !ready;
  $("chatSend").textContent = busy ? "검토 중…" : "보내기 ↑";
  $("chatInput").disabled = busy;
  $("newChat").disabled = busy;
  $("chatForm").setAttribute("aria-busy", String(busy));
}

function addMessage(role, text) {
  const el = document.createElement("article");
  el.className = `chat-message ${role}`;
  el.innerHTML = `<strong>${role === "user" ? "나" : "PPE 도우미"}</strong><p class="message-text">${esc(text)}</p>`;
  $("chatMessages").append(el);
  $("chatWelcome").hidden = true;
  return el;
}

function renderAnswerBase(el, response) {
  el.querySelector(".message-text").textContent =
    response.reply || "답변 내용이 없습니다.";
  if (response.questions?.length)
    el.insertAdjacentHTML(
      "beforeend",
      `<div class="followup-questions"><strong>추가로 알려주세요</strong><ul>${response.questions.map((q) => `<li>${esc(q)}</li>`).join("")}</ul></div>`,
    );
  const evidence = {
    backend: response.backend,
    model: response.model || null,
    reply: response.reply,
    questions: response.questions || [],
    candidates: response.candidates || [],
    kits: response.kits || [],
    sources: response.sources || [],
    live_lookup: response.live_lookup || null,
    generated_at: new Date().toISOString(),
  };
  const currentKits = (response.kits || []).map((k) => ({
    ...k,
    recommendation_evidence: evidence,
  }));
  recommendedKits = currentKits;
  renderWorksiteKits();
  if (currentKits.length) {
    el.insertAdjacentHTML(
      "beforeend",
      `<div class="recommended-kits">${kitOptionsMarkup(currentKits)}</div>`,
    );
    el.querySelectorAll("[data-apply-kit]").forEach((b) =>
      b.addEventListener("click", () =>
        applyRecommendedKit(currentKits[Number(b.dataset.applyKit)]),
      ),
    );
  } else {
    const candidates = (response.candidates || [])
      .map((c) => ({ c, p: product(c.product_id) }))
      .filter((x) => x.p);
    if (candidates.length)
      el.insertAdjacentHTML(
        "beforeend",
        `<div class="recommended-products">${candidates.map(({ c, p }) => `<div class="recommended-product">${imageMarkup(p)}<div><h3>${esc(p.display_name)}</h3>${c.selection_status === "excluded" ? '<span class="badge pending">선정 제외 · 비교 자료</span>' : ""}<p>${esc(c.reason)}</p><div class="purchase-links">${purchases(p)}</div>${c.selection_status === "review_candidate" ? `<button type="button" class="choose-product" data-product="${esc(p.product_id)}">내 조합에 넣기</button>` : ""}</div></div>`).join("")}</div>`,
      );
    el.querySelectorAll("[data-product]").forEach((b) =>
      b.addEventListener("click", () => chooseProduct(b.dataset.product)),
    );
  }
  if (response.live_lookup) {
    const l = response.live_lookup;
    el.insertAdjacentHTML(
      "beforeend",
      `<p class="small muted">${l.status === "fetched" ? `제조사 원문 조회 · ${l.source_count}개 제품 · ${esc(new Date(l.retrieved_at).toLocaleString("ko-KR"))}` : l.status === "error" ? "제조사 조회에 실패했습니다. 이번 답변의 실시간 물질 근거는 미확인입니다." : "이번 답변은 추가 원문 조회 없이 작성되었습니다."}</p>${l.sources?.length ? `<details class="chat-sources"><summary>물질 조회 결과</summary>${l.sources.map((s) => `<p>${link(s.url, s.title)}<br><span class="small muted">${s.status === "matched" ? `해당 CAS 행 ${s.match_count}건` : s.status === "not_found" ? "해당 CAS 행 없음" : "조회 실패"}${s.revision ? ` · 자료 개정 ${esc(s.revision)}` : ""}</span>${s.queries?.length ? `<br><span class="small">${s.queries.map((q) => `CAS ${esc(q.cas)}: ${q.status === "matched" ? "시험 행 있음" : q.status === "not_found" ? "시험 행 없음" : "조회 실패"}`).join(" · ")}</span>` : ""}</p>`).join("")}</details>` : ""}`,
    );
  }
  if (response.sources?.length)
    el.insertAdjacentHTML(
      "beforeend",
      `<details class="chat-sources"><summary>답변 근거 ${response.sources.length}개</summary>${response.sources.map((s) => `<p>${link(s.url, s.title)}<br><span class="small muted">${s.kind === "live_manufacturer_source" ? "이번 원문 조회" : "등록 자료"}</span>${s.evidence ? `<br><span class="small">${esc(s.evidence)}</span>` : ""}</p>`).join("")}</details>`,
    );
}
