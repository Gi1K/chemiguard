// Postwork: one live catalog snapshot drives cards, pickers and counseling.
let catalogRefreshInFlight = false;
let renderedCatalogStatus = "";

async function fetchCatalog() {
  const response = await fetch(`${apiBase}/api/ppe/catalog`, {
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error("제품 DB 연결을 확인하지 못했습니다.");
  const snapshot = await response.json();
  if (
    !Array.isArray(snapshot.products) ||
    !Array.isArray(snapshot.product_sources)
  )
    throw new Error("제품 DB 형식을 확인하지 못했습니다.");
  return snapshot;
}

function renderCatalogMaintenance(status) {
  const badge = $("catalogUpdateBadge");
  const content = $("catalogUpdateDetails");
  $("catalogDataLink").href = status
    ? `${apiBase}/api/ppe/catalog`
    : "catalog-data.json";
  if (!status) {
    renderedCatalogStatus = "";
    badge.textContent = "저장된 기본 목록";
    content.textContent =
      "제품 DB에 연결하지 못해 저장된 기본 목록을 보여주고 있어요. 자동 업데이트 상태는 확인할 수 없습니다.";
    return;
  }
  const run = status.last_run;
  const schedule = status.schedule;
  const collected = run?.checked_sources || [];
  const manufacturers = [...new Set(collected.map((source) => source.manufacturer))];
  badge.textContent =
    collected.length
      ? `공식 자료 ${collected.length}곳 수집`
      : run
        ? "새 수집 자료 없음"
        : schedule
          ? "매일 오전 9시 확인"
          : "정기 확인 설정 전";
  const statusKey = JSON.stringify(status);
  if (statusKey === renderedCatalogStatus) return;
  renderedCatalogStatus = statusKey;
  const when = run?.finished_at
    ? new Date(run.finished_at).toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
      })
    : "아직 실행 전";
  content.innerHTML = `<p><strong>${schedule ? "매일 오전 9시 · 한국 시간" : "정기 일정 설정 전"}</strong><br>최근 확인: ${esc(when)}</p>
    <p>전체 ${status.product_count}개 · 자동 발견 ${status.discovered_count}개${run ? ` · 이번 추가 ${run.added.length}개 · 갱신 ${run.updated.length}개` : ""}</p>
    ${collected.length ? `<p>이번에 수집한 공식 페이지 ${collected.length}곳<br>수집 확인 제조사: ${manufacturers.map(esc).join(" · ")}</p>` : run ? "<p>이번 확인에서 새로 수집한 자료가 없습니다. 저장된 제품 목록을 보여드려요.</p>" : ""}
    ${
      run?.added?.length
        ? `<div class="recent-catalog-products">${run.added
            .map((id) => product(id))
            .filter(Boolean)
            .map(
              (p) =>
                `<button type="button" data-detail="${esc(p.product_id)}">${esc(p.display_name)} ↗</button>`,
            )
            .join("")}</div>`
        : ""
    }
    <p class="small muted">자동 발견은 출시일 확인이나 현장 사용 승인을 뜻하지 않습니다. 기본 정보만 확인한 제품은 성능 검토 전으로 표시합니다.</p>
    ${schedule ? '<p class="small muted">현재 정기 확인은 이 PC와 Codex 앱이 켜져 있을 때 실행됩니다.</p>' : ""}`;
}

function refreshProductPickers() {
  for (const part of [
    ...parts,
    { id: "respiratorAccessory", accessory: true },
  ]) {
    const select = $(part.id),
      selected = select.value;
    select
      .querySelectorAll('option:not([value=""])')
      .forEach((o) => o.remove());
    const products = data.products.filter((p) =>
      part.accessory
        ? isRespiratoryAccessory(p)
        : p.category === part.category && !isRespiratoryAccessory(p),
    );
    for (const p of products)
      select.add(new Option(p.display_name, p.product_id));
    select.value = selected;
  }
  const colourSelect = $("colourFilter"),
    selectedColour = colourSelect.value;
  colourSelect
    .querySelectorAll('option:not([value="all"])')
    .forEach((o) => o.remove());
  for (const id of new Set(data.products.map(colour)))
    colourSelect.add(new Option(colours[id]?.label || id, id));
  colourSelect.value = selectedColour;
  $("catalogScope").textContent =
    `국내 구매 경로 ${data.products.filter((p) => p.domestic_purchase?.length).length}종 / 전체 ${data.products.length}종의 제품 자료를 비교합니다.`;
}

async function refreshCatalog(force = false) {
  if (
    catalogRefreshInFlight ||
    (!force &&
      (busy || document.querySelector("dialog[open]") || document.hidden))
  )
    return;
  catalogRefreshInFlight = true;
  try {
    const statusResponse = await fetch(`${apiBase}/api/ppe/catalog/status`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!statusResponse.ok)
      throw new Error("제품 확인 상태를 가져오지 못했어요.");
    const status = await statusResponse.json();
    if (force || status.revision !== data.catalog_meta?.revision) {
      data = await fetchCatalog();
      refreshProductPickers();
      renderProducts();
      renderHero();
      renderKit();
      renderWorksiteKits();
      $("catalogNotice").textContent = "제품 DB의 최신 목록을 반영했어요.";
    }
    renderCatalogMaintenance(status);
  } catch {
    $("catalogUpdateBadge").textContent = "업데이트 연결 확인 필요";
  } finally {
    catalogRefreshInFlight = false;
  }
}
