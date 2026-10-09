// Postwork: readable product browsing, real-photo previews, details, and comparison.
let localPhotos = {};
const comparedProducts = new Set();
const categoryPaths = {
  chemical_protective_coverall:
    '<path d="M38 26c0-18 24-18 24 0l-3 12 18 12 13 39-13 5-12-29-3 40 8 65-18 2-2-52-2 52-18-2 8-65-3-40-12 29-13-5 13-39 18-12zM40 24h20v14H40zM50 43v60M36 106h28"/>',
  chemical_gloves:
    '<path d="M25 153l-5-56-6-25q-1-13 10-7l10 18V35q0-14 9-10v48-55q10-10 12 2v52-47q10-7 11 5v45-35q11-6 10 8l-1 57-10 48zM26 136h41"/>',
  chemical_boots:
    '<path d="M35 30h35l-4 91 16 14q10 16-2 20H24q-10-5-4-19l13-14zM21 146h59M33 57h36"/>',
  respirator:
    '<path d="M30 55q20-16 40 0l9 58-29 24-29-24zM30 67L13 53M70 67l17-14"/><circle cx="50" cy="100" r="17"/><path d="M43 93h14M43 101h14M43 109h14"/>',
  eye_protection:
    '<path d="M13 72h74v42H60l-10-12-10 12H13zM13 82l-9-5M87 82l9-5M24 81h16v21H24zM60 81h16v21H60z"/>',
  face_shield:
    '<path d="M20 40q30-15 60 0v13H20zM22 53v63q28 30 56 0V53M35 65v40"/>',
};

function categoryIcon(category, className = "") {
  return `<svg class="${className}" viewBox="0 0 100 180" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">${categoryPaths[category] || categoryPaths.chemical_protective_coverall}</svg>`;
}

function productPhotoUrl(p) {
  return localPhotos[p.product_id] || null;
}

function productSource(p) {
  return (
    p.images?.[0]?.source_page ||
    sources(p.source_ids).find((s) => /manufacturer/.test(s.kind))?.url
  );
}

function photoNote(p) {
  if (p.discovery)
    return "공식 출처에서 실물 사진 확인 · 사진 사용 권한 검토 전";
  return p.images?.[0]?.exact_style_match
    ? "모델 연결 사진 · 판매 옵션은 별도 확인"
    : "제품군 대표사진 · 정확한 판매 모델 확인 필요";
}

function imageMarkup(p, eager = false) {
  const photo = productPhotoUrl(p);
  if (photo) {
    return `<img class="product-image real-photo" src="${esc(photo)}" alt="${esc(p.display_name)} — ${esc(photoNote(p))}" loading="${eager ? "eager" : "lazy"}" decoding="async">`;
  }
  const label =
    parts.find((part) => part.category === p.category)?.label || "구성품";
  return `<div class="product-symbol">${categoryIcon(p.category)}<small>${esc(label)} · 품목 안내 도식</small><span>실물 사진은 제품 출처에서 확인</span></div>`;
}

function renderHero() {
  const featured = ["TYCHEM_2000_YELLOW", "TYCHEM_6000_CHA6_GRAY"].map(product);
  $("heroGallery").innerHTML =
    `<div class="diagram-header"><span>OUR FIELD ESSENTIALS</span><span>CG — 01</span></div>
    <div class="featured-products">${featured
      .map(
        (
          p,
          i,
        ) => `<button type="button" class="featured-product" data-detail="${esc(p.product_id)}">
      <span class="featured-index">0${i + 1} / ${esc(colours[colour(p)]?.label || "색상 확인 전")}</span>
      ${imageMarkup(p, true)}<strong>${esc(p.identity.model)}</strong><small>${esc(p.manufacturer)} <span>자세히 보기 ↗</span></small>
    </button>`,
      )
      .join(
        "",
      )}</div><div class="diagram-footer"><b>실제 제품에서 시작하는 검토.</b><span>형식 · 성능 · 작업 조건을 함께</span></div>`;
  const domestic = data.products.filter(
    (p) => p.domestic_purchase?.length,
  ).length;
  $("catalogMetrics").innerHTML =
    `<div class="metric"><strong>${data.products.length}</strong><span>등록 제품<br>6개 보호구 품목</span></div>
    <div class="metric"><strong>${data.product_sources.length}</strong><span>제품 출처 기록<br>원문 근거 연결</span></div>
    <div class="metric"><strong>${domestic}</strong><span>국내 판매·견적 경로<br>실재고 별도 확인</span></div>
    <div class="metric"><strong>찾고, 비교하고,<br>조합하세요.</strong><span>현장 조건에 맞춘<br>검토용 초안</span></div>`;
}

function renderCategoryChips() {
  const selected = $("categoryFilter").value;
  $("categoryChips").innerHTML = [{ category: "all", label: "전체" }, ...parts]
    .map((part) => {
      const count =
        part.category === "all"
          ? data.products.length
          : data.products.filter((p) => p.category === part.category).length;
      return `<button type="button" data-category="${part.category}" aria-pressed="${selected === part.category}">${part.label}<span>${count}</span></button>`;
    })
    .join("");
}

function filteredProducts() {
  const query = $("searchInput").value.trim().toLocaleLowerCase();
  return data.products.filter(
    (p) =>
      ($("categoryFilter").value === "all" ||
        p.category === $("categoryFilter").value) &&
      ($("typeFilter").value === "all" ||
        types(p).includes(Number($("typeFilter").value))) &&
      ($("colourFilter").value === "all" ||
        colour(p) === $("colourFilter").value) &&
      (!$("domesticOnly").checked || p.domestic_purchase?.length) &&
      (!query || matchesProductSearch(p, query)),
  );
}

function productCard(p) {
  const label =
    parts.find((part) => part.category === p.category)?.label || "구성품";
  const productTypes = types(p);
  const source = productSource(p);
  return `<article class="product-card compact-product">
    <div class="product-visual"><button type="button" class="product-image-button" data-detail="${esc(p.product_id)}" aria-label="${esc(p.display_name)} 상세 보기">${imageMarkup(p)}</button>
      <button type="button" class="compare-toggle" data-compare="${esc(p.product_id)}" aria-pressed="${comparedProducts.has(p.product_id)}" aria-label="${esc(p.display_name)} 비교 선택">${comparedProducts.has(p.product_id) ? "✓ 비교 중" : "＋ 비교"}</button>
      <span class="photo-status">${productPhotoUrl(p) ? (p.images?.[0]?.exact_style_match ? "모델 연결 사진" : "제품군 대표사진") : "실물 사진 아님"}</span>
    </div>
    <div class="product-meta"><p class="section-kicker">${esc(p.manufacturer)}</p><h3>${esc(p.display_name)}</h3>
      ${p.discovery ? '<p class="discovery-badge">최근 발견 · 성능 검토 전</p>' : ""}
      <div class="card-specs"><span>${esc(label)}</span>${productTypes.length ? `<span>${productTypes.map((t) => `${t}형식`).join(" · ")}</span>` : ""}${swatch(colour(p))}</div>
      <p class="purchase-summary">${p.domestic_purchase?.length ? `국내 판매·견적 경로 ${p.domestic_purchase.length}곳` : "국내 구매 경로 확인 전"} <span>· 실재고 별도 확인</span></p>
      <div class="card-actions"><button type="button" data-detail="${esc(p.product_id)}">상세 보기</button><button type="button" class="choose-product" data-product="${esc(p.product_id)}">조합에 담기 ＋</button></div>
      ${!productPhotoUrl(p) && source ? `<p class="photo-source-link">${link(source, "제품 사진·출처 보기")}</p>` : ""}
    </div></article>`;
}

function renderProducts() {
  const list = filteredProducts();
  $("productCount").textContent = `${list.length}개 제품`;
  $("products").innerHTML =
    list.map(productCard).join("") ||
    '<div class="empty-results"><h3>조건에 맞는 제품이 없습니다.</h3><p>검색어를 줄이거나 품목·형식·색상 필터를 바꿔보세요.</p><button type="button" data-reset-search>필터 초기화</button></div>';
  renderCategoryChips();
}

function openProduct(productId) {
  const p = product(productId);
  if (!p) return;
  const source = productSource(p);
  $("productDetail").innerHTML =
    `<div class="detail-layout"><div class="detail-gallery">
      <button type="button" class="detail-photo" data-photo="${esc(p.product_id)}" ${productPhotoUrl(p) ? "" : "disabled"} aria-label="${esc(p.display_name)} 사진 크게 보기">${imageMarkup(p, true)}</button>
      <p class="small muted">${esc(photoNote(p))}</p>${productPhotoUrl(p) ? '<p class="small">사진을 누르면 크게 볼 수 있습니다.</p>' : ""}
      ${source ? link(source, "원본 사진·출처 확인") : ""}
    </div><div class="detail-info"><p class="section-kicker">${esc(p.manufacturer)}</p><h2 id="productDetailTitle">${esc(p.display_name)}</h2>
      <div class="detail-badges">${types(p)
        .map((t) => `<span class="badge neutral">${t}형식 표시</span>`)
        .join("")}${swatch(colour(p))}</div>
      <p class="small muted">${esc(p.identity.model)}${p.item_standard_summary ? ` · ${esc(p.item_standard_summary)}` : ""}</p>
      ${p.discovery ? `<p class="discovery-badge">${esc(new Date(p.discovery.first_seen_at).toLocaleDateString("ko-KR"))} 처음 발견 · 출시일 미확인</p><p class="small">제조사 제품명과 모델만 확인했습니다. 국내 인증·구매 경로·물질별 성능을 확인하기 전에는 자동 추천에 넣지 않습니다.</p>` : ""}
      <div class="detail-action"><button type="button" class="primary" data-detail-add="${esc(p.product_id)}">내 조합에 담기 ＋</button><button type="button" data-compare="${esc(p.product_id)}">${comparedProducts.has(p.product_id) ? "비교에서 빼기" : "비교에 추가"}</button></div>
      <section class="detail-section"><h3>국내 구매·견적 경로</h3>${purchases(p)}</section>
      <section class="detail-section"><h3>제품·인증 근거</h3><dl>${(p.certifications || []).map(certText).join("")}</dl>${performanceMarkup(p)}</section>
      <section class="detail-section"><h3>확인할 내용</h3><ul>${(p.uncertainties || []).map((n) => `<li>${esc(n)}</li>`).join("") || "<li>실제 노출 조건과 구성품 호환을 확인하세요.</li>"}</ul></section>
    </div></div>`;
  $("productDialog").setAttribute("aria-labelledby", "productDetailTitle");
  $("productDialog").showModal();
}

function openPhoto(productId) {
  const p = product(productId);
  if (!p || !productPhotoUrl(p)) return;
  $("photoDetail").innerHTML =
    `${imageMarkup(p, true)}<h2>${esc(p.display_name)}</h2><p>${esc(photoNote(p))}</p><p class="small muted">원본 사진의 해상도를 유지합니다. 사진의 색상이나 형태를 변경하지 않습니다.</p>`;
  $("photoDialog").showModal();
}

function toggleComparison(productId) {
  if (comparedProducts.has(productId)) comparedProducts.delete(productId);
  else if (comparedProducts.size < 3) comparedProducts.add(productId);
  else {
    $("catalogNotice").textContent =
      "한 번에 최대 3개 제품을 비교할 수 있습니다.";
    return;
  }
  $("compareTray").hidden = comparedProducts.size === 0;
  $("compareCount").textContent = `${comparedProducts.size}개 제품 선택`;
  $("compareNames").textContent = [...comparedProducts]
    .map((id) => product(id).identity.model)
    .join(" · ");
  renderProducts();
  // Refresh the comparison button in an open detail without changing focus.
  document
    .querySelectorAll("#productDetail [data-compare]")
    .forEach((button) => {
      button.textContent = comparedProducts.has(button.dataset.compare)
        ? "비교에서 빼기"
        : "비교에 추가";
    });
}

function openComparison() {
  const selected = [...comparedProducts].map(product);
  $("productDetail").innerHTML =
    `<p class="section-kicker">COMPARE YOUR OPTIONS</p><h2 id="productDetailTitle">제품을 나란히 비교하세요.</h2><p class="small muted">형식 표시는 물질 적합성 승인이 아닙니다. 작업 조건과 제품 근거를 함께 확인하세요.</p>
    <div class="comparison-grid" style="--compare-columns:${selected.length}">${selected
      .map(
        (
          p,
        ) => `<article><div class="compare-photo">${imageMarkup(p, true)}</div><p class="section-kicker">${esc(p.manufacturer)}</p><h3>${esc(p.display_name)}</h3>
    <dl><dt>품목</dt><dd>${esc(parts.find((part) => part.category === p.category)?.label || "구성품")}</dd><dt>보호복 형식</dt><dd>${
      types(p)
        .map((t) => `${t}형식`)
        .join(" / ") || "품목별 기준 확인"
    }</dd><dt>실제 제품 색상</dt><dd>${swatch(colour(p))}</dd><dt>사진 상태</dt><dd>${esc(photoNote(p))}</dd><dt>구매·견적</dt><dd>${purchases(p)}</dd></dl><button type="button" data-detail="${esc(p.product_id)}">근거 상세 보기</button><button type="button" class="primary" data-detail-add="${esc(p.product_id)}">조합에 담기 ＋</button></article>`,
      )
      .join("")}</div>`;
  $("productDialog").setAttribute("aria-labelledby", "productDetailTitle");
  $("productDialog").showModal();
}

function bindCatalogUI() {
  $("mainContent").addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.dataset.detail) openProduct(target.dataset.detail);
    if (target.dataset.photo) openPhoto(target.dataset.photo);
    if (target.dataset.compare) toggleComparison(target.dataset.compare);
    if (target.dataset.detailAdd) {
      $("productDialog").close();
      chooseProduct(target.dataset.detailAdd);
    }
    if (target.dataset.category) {
      $("categoryFilter").value = target.dataset.category;
      renderProducts();
    }
    if (target.hasAttribute("data-reset-search")) $("resetFilters").click();
  });
  $("closeProductDialog").addEventListener("click", () =>
    $("productDialog").close(),
  );
  $("closePhotoDialog").addEventListener("click", () =>
    $("photoDialog").close(),
  );
  $("openComparison").addEventListener("click", openComparison);
  $("clearComparison").addEventListener("click", () => {
    comparedProducts.clear();
    $("compareTray").hidden = true;
    renderProducts();
  });
  for (const id of ["productDialog", "photoDialog"])
    $(id).addEventListener("click", (event) => {
      if (event.target === $(id)) $(id).close();
    });
  document.addEventListener(
    "error",
    (event) => {
      if (event.target instanceof HTMLImageElement) {
        const replacement = document.createElement("div");
        replacement.className = "image-empty";
        replacement.textContent =
          "사진을 불러오지 못했습니다. 제품 출처에서 확인하세요.";
        event.target.replaceWith(replacement);
      }
    },
    true,
  );
}
