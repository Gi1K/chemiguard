// Baseline initialization adapted for the new public UI.
async function init() {
  const r = await fetch("catalog-data.json", { cache: "no-store" });
  if (!r.ok) throw new Error("제품 자료를 불러오지 못했습니다.");
  data = await r.json();
  parts.forEach((part) => {
    $(part.id).insertAdjacentHTML(
      "beforeend",
      data.products
        .filter(
          (p) => p.category === part.category && !isRespiratoryAccessory(p),
        )
        .map(
          (p) =>
            `<option value="${esc(p.product_id)}">${esc(p.display_name)}</option>`,
        )
        .join(""),
    );
    $("categoryFilter").insertAdjacentHTML(
      "beforeend",
      `<option value="${part.category}">${part.label}</option>`,
    );
  });
  $("respiratorAccessory").insertAdjacentHTML(
    "beforeend",
    data.products
      .filter(isRespiratoryAccessory)
      .map(
        (p) =>
          `<option value="${esc(p.product_id)}">${esc(p.display_name)}</option>`,
      )
      .join(""),
  );
  $("colourFilter").insertAdjacentHTML(
    "beforeend",
    [...new Set(data.products.map(colour))]
      .map(
        (id) =>
          `<option value="${esc(id)}">${esc(colours[id]?.label || id)}</option>`,
      )
      .join(""),
  );
  const domestic = data.products.filter(
    (p) => p.domestic_purchase?.length,
  ).length;
  $("catalogScope").textContent =
    `국내 구매 경로 ${domestic}종 / 전체 ${data.products.length}종의 제품 자료를 비교합니다.`;
  $("reviewDate").textContent = data.review_date;
  try {
    savedKits = JSON.parse(localStorage.getItem(savedKitsKey) || "[]");
    if (!Array.isArray(savedKits)) savedKits = [];
  } catch {
    savedKits = [];
  }
  renderHero();
  renderTypeGuide();
  renderWorksiteKits();
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  document
    .querySelectorAll("[data-open]")
    .forEach((b) => b.addEventListener("click", () => showTab(b.dataset.open)));
  ["categoryFilter", "typeFilter", "colourFilter", "domesticOnly"].forEach(
    (id) => $(id).addEventListener("change", renderProducts),
  );
  $("searchInput").addEventListener("input", () => {
    showTab("products");
    renderProducts();
  });
  $("resetFilters").addEventListener("click", () => {
    ["categoryFilter", "typeFilter", "colourFilter"].forEach(
      (id) => ($(id).value = "all"),
    );
    $("domesticOnly").checked = false;
    $("searchInput").value = "";
    renderProducts();
  });
  $("products").addEventListener("click", (e) => {
    const b = e.target.closest("[data-product]");
    if (b) chooseProduct(b.dataset.product);
  });
  $("worksiteKits").addEventListener("click", (e) => {
    const b = e.target.closest("[data-apply-kit],[data-load-kit]");
    if (b?.hasAttribute("data-apply-kit"))
      applyRecommendedKit(Number(b.dataset.applyKit));
    else if (b) loadKit(savedKits[Number(b.dataset.loadKit)]);
  });
  $("kitPanel").addEventListener("input", (e) => {
    if (
      [
        "workZone",
        "exposureNote",
        "useType",
        "workGroup",
        ...parts.map((part) => part.id),
      ].includes(e.target.id)
    )
      invalidateRecommendation();
    $("savedStatus").textContent = "";
    $("draftExport").hidden = true;
    renderKit();
  });
  parts.forEach((part) =>
    $(part.id).addEventListener("change", () => {
      recommendationEvidence = null;
      activeKitReview = null;
      renderKit();
    }),
  );
  $("addRespiratorAccessory").addEventListener("click", () => {
    const id = $("respiratorAccessory").value;
    if (id && !respiratoryAddons.includes(id)) {
      respiratoryAddons.push(id);
      invalidateRecommendation();
    }
    $("draftExport").hidden = true;
    renderKit();
  });
  $("respiratoryParts").addEventListener("click", (e) => {
    const b = e.target.closest("[data-remove-accessory]");
    if (b) {
      respiratoryAddons = respiratoryAddons.filter(
        (id) => id !== b.dataset.removeAccessory,
      );
      invalidateRecommendation();
      $("draftExport").hidden = true;
      renderKit();
    }
  });
  $("chatForm").addEventListener("submit", submitChat);
  $("attachPhoto").addEventListener("click", () => $("chatPhotoInput").click());
  $("chatPhotoInput").addEventListener("change", selectChatPhotos);
  $("unknownMaterial").addEventListener("click", () => {
    $("chatInput").value =
      "처음이라 제품명과 성분을 잘 모르겠어요. 무엇부터 확인하면 될까요?";
    $("chatInput").focus();
  });
  document.querySelectorAll("[data-example]").forEach((b) =>
    b.addEventListener("click", () => {
      $("chatInput").value = b.dataset.example;
      $("chatInput").focus();
    }),
  );
  $("newChat").addEventListener("click", () => {
    chatSession = null;
    userMessages = [];
    recommendedKits = [];
    renderWorksiteKits();
    $("chatMessages").replaceChildren();
    $("chatWelcome").hidden = false;
    $("chatInput").value = "";
    clearChatPhotos();
    checkBackend();
  });
  try {
    $("loadDraft").disabled = !getSavedDraft();
  } catch {}
  $("saveDraft").addEventListener("click", () => {
    try {
      const d = payload();
      activeKitId = d.kit_id;
      localStorage.setItem(draftKeys[0], JSON.stringify(d));
      savedKits = savedKits.filter((k) => k.kit_id !== d.kit_id);
      savedKits.push(d);
      localStorage.setItem(savedKitsKey, JSON.stringify(savedKits));
      $("loadDraft").disabled = false;
      renderWorksiteKits();
      renderKit();
      $("savedStatus").textContent =
        "작업 조합과 실제 제품 색상, 호흡 부품을 사업장 초안으로 저장했습니다.";
    } catch {
      $("savedStatus").textContent =
        "브라우저 저장을 사용할 수 없습니다. JSON 보기를 이용하세요.";
    }
  });
  $("loadDraft").addEventListener("click", () => {
    try {
      const d = getSavedDraft();
      if (
        ![
          "review_draft_v1",
          "review_draft_v2",
          "review_draft_v3",
          "review_draft_v4",
        ].includes(d?.schema_version)
      )
        throw new Error();
      loadKit(d);
    } catch {
      $("savedStatus").textContent = "저장 초안을 불러오지 못했습니다.";
    }
  });
  $("exportDraft").addEventListener("click", () => {
    const d = payload();
    activeKitId = d.kit_id;
    const json = JSON.stringify(d, null, 2);
    $("draftJson").value = json;
    $("draftExport").hidden = false;
    if (exportUrl) URL.revokeObjectURL(exportUrl);
    exportUrl = URL.createObjectURL(
      new Blob([json], { type: "application/json" }),
    );
    $("draftDownload").href = exportUrl;
  });
  renderProducts();
  renderKit();
  showTab("products");
  bindCatalogUI();
  await checkBackend();
}
init()
  .then(() => {
    $("accessForm").addEventListener("submit", (event) => {
      event.preventDefault();
      demoToken = $("accessToken").value.trim();
      $("accessToken").value = "";
      $("accessLabel").textContent = demoToken
        ? "이 탭에 코드 입력됨"
        : "시연 코드를 입력하세요";
      checkBackend();
    });
    $("forgetAccess").addEventListener("click", () => {
      demoToken = "";
      chatSession = null;
      $("accessToken").value = "";
      $("accessLabel").textContent = "시연 코드를 입력하세요";
      checkBackend();
    });
    document.querySelectorAll('[role="tab"]').forEach((tab) => {
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
          return;
        event.preventDefault();
        const tabs = [...document.querySelectorAll('[role="tab"]')];
        const i = tabs.indexOf(tab);
        const next =
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? tabs.length - 1
              : (i + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
                tabs.length;
        tabs[next].focus();
        tabs[next].click();
      });
    });
  })
  .catch((error) => {
    $("loadError").hidden = false;
    $("loadError").textContent = error.message;
  });
