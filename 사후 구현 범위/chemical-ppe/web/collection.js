// Read-only collection browser. It never starts collection or model requests.
(() => {
  const $ = (id) => document.getElementById(id);
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const categories = {
    chemical_protective_coverall: "보호복",
    chemical_gloves: "화학장갑",
    chemical_boots: "화학장화",
    respirator: "호흡보호구",
    eye_protection: "눈 보호구",
    face_shield: "안면보호구",
  };
  const params = new URLSearchParams(location.search);
  let view = params.get("view") === "sources" ? "sources" : "products";
  let products = [],
    sources = [],
    loading = false,
    loaded = false,
    renderedSnapshot = "",
    page = 1;
  const pageSize = 20;
  const date = (value) => {
    const parsed = new Date(value);
    return value && Number.isFinite(parsed.getTime())
      ? parsed.toLocaleString("ko-KR", {
          timeZone: "Asia/Seoul",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        })
      : "확인 전";
  };
  const timestamp = (value) => Date.parse(value) || 0;
  function officialLink(url) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "https:" && !parsed.username && !parsed.password)
        return `<a href="${escape(parsed.href)}" target="_blank" rel="noopener noreferrer">공식 출처 열기 ↗</a>`;
    } catch {}
    return "";
  }
  function syncUrl() {
    const query = new URLSearchParams();
    if (view === "sources") query.set("view", view);
    if ($("collectionSearch").value.trim())
      query.set("q", $("collectionSearch").value.trim());
    if ($("collectionManufacturer").value)
      query.set("manufacturer", $("collectionManufacturer").value);
    history.replaceState(
      null,
      "",
      location.pathname + (query.size ? `?${query}` : ""),
    );
  }
  function productCard(p) {
    return `<article class="collection-item"><div><p class="collection-maker">${escape(p.manufacturer)}</p><h3>${escape(p.display_name)}</h3><p class="collection-model">${escape(categories[p.category] || p.category)} · ${escape(p.identity?.model)}</p><span class="discovery-badge">성능 검토 전</span></div><div><dl><dt>처음 발견</dt><dd>${escape(date(p.discovery.first_seen_at))}</dd><dt>최근 확인</dt><dd>${escape(date(p.discovery.last_checked_at))}</dd></dl>${officialLink(p.discovery.source_url)}</div></article>`;
  }
  function sourceCard(s) {
    const matched = products.find((p) => p.discovery.source_url === s.url);
    return `<article class="collection-item"><div><p class="collection-maker">${escape(s.manufacturer)}</p><h3>${escape(matched?.display_name || "제조사 공식 제품·자료 페이지")}</h3><p class="collection-source-url">${escape(s.url)}</p></div><div><dl><dt>수집 확인</dt><dd>${escape(date(s.checked_at))}</dd></dl>${officialLink(s.url)}</div></article>`;
  }
  function render() {
    for (const button of document.querySelectorAll("[data-view]")) {
      const selected = button.dataset.view === view;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    }
    $("collectionResults").setAttribute(
      "aria-labelledby",
      view === "products" ? "collectedProductsTab" : "collectedSourcesTab",
    );
    $("collectionSortNote").textContent =
      view === "products" ? "처음 발견한 순 · 최신 먼저" : "최근 수집 확인 순";
    const query = $("collectionSearch")
      .value.trim()
      .normalize("NFKC")
      .toLocaleLowerCase();
    const maker = $("collectionManufacturer").value;
    const rows = (view === "products" ? products : sources).filter((item) => {
      const text = [
        item.manufacturer,
        item.display_name,
        item.identity?.model,
        item.url,
        categories[item.category],
      ]
        .filter(Boolean)
        .join(" ")
        .normalize("NFKC")
        .toLocaleLowerCase();
      return (
        (!maker || item.manufacturer === maker) &&
        (!query || text.includes(query))
      );
    });
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    page = Math.min(page, totalPages);
    $("collectionResultCount").textContent =
      `${view === "products" ? "수집 제품" : "확인한 출처"} ${rows.length}개${query || maker ? " · 검색 결과" : ""}`;
    $("collectionResults").innerHTML = rows.length
      ? rows
          .slice((page - 1) * pageSize, page * pageSize)
          .map(view === "products" ? productCard : sourceCard)
          .join("")
      : `<div class="collection-empty"><h3>${query || maker ? "조건에 맞는 자료가 없어요." : "아직 표시할 수집 자료가 없어요."}</h3><p>${query || maker ? "검색어를 줄이거나 제조사를 바꿔 보세요." : "공식 자료를 확인해 수집한 결과가 여기에 표시됩니다."}</p></div>`;
    $("collectionPagination").hidden = rows.length <= pageSize;
    $("previousCollection").disabled = page === 1;
    $("nextCollection").disabled = page === totalPages;
    $("collectionPageNumber").textContent = `${page} / ${totalPages}`;
  }
  async function load() {
    if (loading) return;
    loading = true;
    $("reloadCollection").disabled = true;
    $("reloadCollection").textContent = "불러오는 중…";
    $("collectionBrowser").setAttribute("aria-busy", "true");
    try {
      const response = await fetch(
        `${window.PPE_CONFIG?.apiBase || ""}/api/ppe/catalog`,
        { cache: "no-store", signal: AbortSignal.timeout(8000) },
      );
      if (!response.ok) throw new Error("catalog_unavailable");
      const snapshot = await response.json();
      if (!Array.isArray(snapshot.products) || !snapshot.catalog_meta)
        throw new Error("catalog_invalid");
      $("collectionFreshness").textContent =
        `목록을 불러온 시각: ${date(new Date().toISOString())} · 활성 화면에서 1분마다 갱신`;
      $("collectionError").hidden = true;
      const snapshotKey = JSON.stringify(snapshot);
      if (snapshotKey === renderedSnapshot) return;
      const status = snapshot.catalog_meta;
      products = snapshot.products
        .filter((p) => p.discovery)
        .sort(
          (a, b) =>
            timestamp(b.discovery.first_seen_at) -
            timestamp(a.discovery.first_seen_at),
        );
      sources = [
        ...new Map(
          (status.last_run?.checked_sources || []).map((s) => [s.url, s]),
        ).values(),
      ].sort((a, b) => timestamp(b.checked_at) - timestamp(a.checked_at));
      const names = [
        ...new Set([...products, ...sources].map((item) => item.manufacturer)),
      ].sort((a, b) => a.localeCompare(b));
      const selected = loaded
        ? $("collectionManufacturer").value
        : params.get("manufacturer") || "";
      $("collectionManufacturer").replaceChildren(
        new Option("모든 제조사", ""),
        ...names.map((name) => new Option(name, name)),
      );
      $("collectionManufacturer").value = names.includes(selected)
        ? selected
        : "";
      $("collectedProductCount").textContent = products.length;
      $("productsTabCount").textContent = products.length;
      $("collectedSourceCount").textContent = sources.length;
      $("sourcesTabCount").textContent = sources.length;
      $("collectedManufacturerCount").textContent = new Set(
        sources.map((s) => s.manufacturer),
      ).size;
      $("collectionSchedule").textContent = status.schedule
        ? `${status.schedule.label} · 한국 시간`
        : "정기 확인 설정 전";
      $("collectionLastRun").textContent =
        `최근 확인 ${date(status.last_run?.finished_at)}`;
      loaded = true;
      render();
      renderedSnapshot = snapshotKey;
    } catch {
      $("collectionError").textContent = loaded
        ? "최신 목록을 불러오지 못해 이전에 조회한 자료를 보여드려요. 잠시 후 다시 불러와 주세요."
        : "수집 목록에 연결하지 못했어요. 잠시 후 ‘최신 목록 불러오기’를 눌러 주세요.";
      $("collectionError").hidden = false;
      if (!loaded) {
        $("collectionResultCount").textContent = "목록 연결 대기";
        $("collectionSchedule").textContent = "일정 확인 대기";
        $("collectionLastRun").textContent = "";
      }
    } finally {
      loading = false;
      $("reloadCollection").disabled = false;
      $("reloadCollection").textContent = "최신 목록 불러오기";
      $("collectionBrowser").setAttribute("aria-busy", "false");
    }
  }
  $("collectionSearch").value = params.get("q") || "";
  for (const [id, event] of [
    ["collectionSearch", "input"],
    ["collectionManufacturer", "change"],
  ])
    $(id).addEventListener(event, () => {
      page = 1;
      syncUrl();
      render();
    });
  $("resetCollection").addEventListener("click", () => {
    $("collectionSearch").value = "";
    $("collectionManufacturer").value = "";
    page = 1;
    syncUrl();
    render();
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      view = button.dataset.view;
      page = 1;
      syncUrl();
      render();
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
      event.preventDefault();
      const next =
        event.key === "Home"
          ? $("collectedProductsTab")
          : event.key === "End"
            ? $("collectedSourcesTab")
            : document.querySelector(
                `[data-view="${view === "products" ? "sources" : "products"}"]`,
              );
      next.click();
      next.focus();
    });
  });
  $("previousCollection").addEventListener("click", () => {
    page--;
    render();
    $("collectionResults").focus();
  });
  $("nextCollection").addEventListener("click", () => {
    page++;
    render();
    $("collectionResults").focus();
  });
  $("reloadCollection").addEventListener("click", load);
  setInterval(() => {
    if (!document.hidden) load();
  }, 60000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
  load();
})();
