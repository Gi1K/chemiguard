// Derived from the SHA256-verified 2026-10-08 prework app; existing logic, reformatted.
function idsOfKit(k) {
  return (
    k.product_ids ||
    Object.values(k.component_product_ids || {})
      .flat()
      .filter(Boolean)
  );
}

function kitUseType(k) {
  const value = Number(
    k.selected_use_type ?? k.use_type ?? k.kit_review?.use_type ?? null,
  );
  return Number.isInteger(value) && value >= 1 && value <= 6 ? value : null;
}

function kitWorkGroup(k) {
  const value =
    k.selected_work_group ?? k.work_group ?? k.kit_review?.work_group ?? null;
  return typeof value === "string" && value.trim()
    ? value.trim().replace(/\s+/g, " ").slice(0, 80)
    : null;
}

function colourOverlap(k, coverall, excludeKit = null) {
  const useType = kitUseType(k),
    workGroup = kitWorkGroup(k),
    coverallColour = coverall ? colour(coverall) : null,
    displayTypes = types(coverall),
    sameColour = [...savedKits, ...recommendedKits].filter((other) => {
      if (
        other === k ||
        other === excludeKit ||
        (k.kit_id && other.kit_id && other.kit_id === k.kit_id) ||
        !coverallColour ||
        coverallColour === "unknown"
      )
        return false;
      const otherColour =
        other.selected_coverall_colour ??
        colour(
          idsOfKit(other)
            .map(product)
            .find((p) => p?.category === "chemical_protective_coverall"),
        );
      return otherColour === coverallColour;
    });
  return {
    conflicts: sameColour.filter(
      (other) =>
        useType !== null &&
        kitUseType(other) !== null &&
        (kitUseType(other) !== useType ||
          (workGroup !== null &&
            kitWorkGroup(other) !== null &&
            kitWorkGroup(other) !== workGroup)),
    ),
    unconfirmed: sameColour.filter(
      (other) =>
        useType === null ||
        kitUseType(other) === null ||
        (kitUseType(other) === useType &&
          (workGroup === null || kitWorkGroup(other) === null)),
    ),
    typeMismatch:
      useType !== null &&
      displayTypes.length > 0 &&
      !displayTypes.includes(useType),
  };
}

function colourOverlapText(overlap) {
  const notes = [];
  if (overlap.conflicts.length)
    notes.push(
      `색상 충돌 · 대안 확인 필요. 다른 ${[...new Set(overlap.conflicts.map((k) => `${kitUseType(k)}형식${kitWorkGroup(k) ? ` / ${kitWorkGroup(k)}` : ""}`))].join(" · ")} 조합과 보호복 색상이 겹칩니다. 물질별 성능 근거가 있는 다른 색상 제품을 확인해야 합니다.`,
    );
  else if (overlap.unconfirmed.length)
    notes.push(
      "같은 색상의 다른 조합에서 사용 형식 또는 작업 구분이 미확인입니다. 형식과 작업 목적을 확인한 후 색상 구분을 검토하세요.",
    );
  if (overlap.typeMismatch)
    notes.push(
      "선택 형식과 제품 표시 불일치. 실제 인증 문서와 사용할 구성의 형식을 확인하세요.",
    );
  return notes.join(" ");
}

function kitMarkup(k, kind, index) {
  const products = idsOfKit(k).map(product).filter(Boolean),
    coverall = products.find(
      (p) => p.category === "chemical_protective_coverall",
    ),
    saved = kind === "saved";
  const reason =
      k.selection_reason ||
      k.kit_review?.selection_reason ||
      "저장한 검토용 초안입니다.",
    comparison = k.comparison_note || k.kit_review?.comparison_note || "",
    missing = k.missing_information || k.kit_review?.missing_information || [];
  const useType = kitUseType(k),
    workGroup = kitWorkGroup(k),
    overlapNote = coverall ? colourOverlapText(colourOverlap(k, coverall)) : "";
  const details = `<p class="small kit-selection-reason">${esc(reason)}</p><p class="small muted">${esc(k.colour_note || k.kit_review?.colour_note || "색상은 실제 선택한 제품 외형입니다.")}</p>`;
  return `<article class="work-kit-card ${saved ? "saved-kit-card" : "kit-option-card"}">${saved ? '<p class="section-kicker">SAVED DRAFT · 검토용 초안</p>' : `<div class="kit-option-label"><span class="kit-option-number">선택지 ${String(index + 1).padStart(2, "0")}</span><span class="badge neutral">검토용</span></div>`}<h3>${esc(k.name || k.company_set_name || "검토 조합")}</h3><p class="kit-use-type"><span class="badge neutral">${useType ? `사용 ${useType}형식` : "사용 형식 확인 전"}</span>${
    coverall && types(coverall).length
      ? `<span class="small muted">제품 표시: ${types(coverall)
          .map((t) => `${t}형식`)
          .join(" / ")}</span>`
      : ""
  }</p><p class="kit-work-group">작업 구분: ${esc(workGroup || "확인 전")}</p><p class="small muted">${esc(k.work_context || k.work_description || "")}</p>${comparison ? `<p class="kit-comparison-note">${esc(comparison)}</p>` : ""}<div class="kit-product-strip">${products.map((p) => `<div>${imageMarkup(p)}<p><span class="muted">${esc(isRespiratoryAccessory(p) ? "호흡 부품" : parts.find((part) => part.category === p.category)?.label || "구성품")}</span><br>${esc(p.display_name)}</p></div>`).join("")}</div>${coverall ? `<p>보호복 ${swatch(colour(coverall))}</p>` : ""}${overlapNote ? `<p class="small kit-colour-overlap">${esc(overlapNote)}</p>` : ""}${saved ? `<details><summary>선정 근거와 색상</summary>${details}</details>` : `<div class="kit-choice-evidence"><h4>선정 근거</h4>${details}</div>`}${missing.length ? `<div class="kit-missing-information"><h4>남은 확인 ${missing.length}개</h4><ul>${missing.map((q) => `<li>${esc(q)}</li>`).join("")}</ul></div>` : ""}<button type="button" class="primary" ${saved ? `data-load-kit="${index}"` : `data-apply-kit="${index}"`}>${saved ? "이 초안 불러오기" : "이 조합 선택하기"}</button></article>`;
}

function kitOptionsMarkup(kits) {
  return `<div class="kit-options-heading"><h3>조합 선택지 <span class="small muted">${kits.length}개</span></h3><p class="small muted">구성품과 남은 조건을 비교해 내 조합에 넣으세요. 선택하면 검토용 초안으로 이어집니다.</p></div><div class="kit-grid">${kits.map((k, i) => kitMarkup(k, "recommended", i)).join("")}</div>`;
}

function renderWorksiteKits() {
  $("worksiteKits").innerHTML =
    (recommendedKits.length ? kitOptionsMarkup(recommendedKits) : "") +
      (savedKits.length
        ? `<h3>저장한 사업장 초안</h3><div class="kit-grid">${savedKits.map((k, i) => kitMarkup(k, "saved", i)).join("")}</div>`
        : "") ||
    '<div class="message">사용 물질과 작업을 입력하면 검토할 조합 선택지를 자동으로 보여드립니다. 구성품을 비교해 내 조합에 넣고 초안으로 저장할 수 있습니다.</div>';
  $("chatExistingColours").textContent = savedKits.length
    ? "저장한 조합: " +
      savedKits
        .map(
          (k) =>
            `${k.company_set_name || "조합"} · ${kitUseType(k) ? `${kitUseType(k)}형식` : "사용 형식 확인 전"} · ${kitWorkGroup(k) || "작업 구분 확인 전"} · ${colours[k.selected_coverall_colour]?.label || "색상 미확인"}`,
        )
        .join(" / ")
    : "사업장에서 함께 쓰는 다른 형식과 별도 작업은 실제 보호복 색상을 구분합니다. 적합한 색상 대안이 없으면 남은 확인으로 알려드립니다.";
}

function selectedProductIds() {
  return [
    ...new Set(
      [...parts.map((part) => $(part.id).value), ...respiratoryAddons].filter(
        Boolean,
      ),
    ),
  ];
}

function invalidateRecommendation() {
  recommendationEvidence = null;
  activeKitReview = null;
}

function applyProductIds(ids) {
  parts.forEach((part) => ($(part.id).value = ""));
  respiratoryAddons = [];
  ids
    .map(product)
    .filter(Boolean)
    .forEach((p) => {
      if (isRespiratoryAccessory(p)) respiratoryAddons.push(p.product_id);
      else {
        const part = parts.find((part) => part.category === p.category);
        if (part && !$(part.id).value) $(part.id).value = p.product_id;
      }
    });
}

function applyRecommendedKit(indexOrKit) {
  const k =
    typeof indexOrKit === "object" ? indexOrKit : recommendedKits[indexOrKit];
  if (!k) return;
  applyProductIds(idsOfKit(k));
  $("companyType").value = k.name || "검토 조합";
  $("workZone").value = k.work_context || "";
  $("useType").value = kitUseType(k) || "";
  $("workGroup").value = kitWorkGroup(k) || "";
  $("exposureNote").value = (k.missing_information || []).join("\n");
  activeKitReview = k;
  activeKitId = null;
  recommendationEvidence = k.recommendation_evidence || null;
  $("draftExport").hidden = true;
  renderKit();
  showTab("kit");
  $("savedStatus").textContent =
    "추천 제품과 호흡 부품을 함께 넣었습니다. 조합 근거와 남은 조건을 검토하세요.";
}

function chooseProduct(id) {
  const p = product(id),
    part = parts.find((part) => part.category === p?.category);
  if (!part) return;
  if (isRespiratoryAccessory(p)) {
    if (!respiratoryAddons.includes(id)) respiratoryAddons.push(id);
  } else $(part.id).value = id;
  if (userMessages.length && !$("workZone").value.trim())
    $("workZone").value = userMessages.join("\n");
  invalidateRecommendation();
  $("draftExport").hidden = true;
  renderKit();
  showTab("kit");
  $("savedStatus").textContent =
    "검토용 조합에 넣었습니다. 다른 제조사의 제품도 함께 선정할 수 있습니다.";
}

function renderKit() {
  const coverall = product($("coverall").value),
    ids = selectedProductIds(),
    useType = kitUseType({ use_type: $("useType").value }),
    workGroup = kitWorkGroup({ work_group: $("workGroup").value });
  const overlap = colourOverlap(
    { kit_id: activeKitId, use_type: useType, work_group: workGroup },
    coverall,
    activeKitReview,
  );
  $("colourBadge").className = "badge neutral";
  $("colourBadge").textContent = !coverall
    ? "제품 선택 전"
    : overlap.conflicts.length
      ? "색상 충돌 · 대안 확인 필요"
      : overlap.typeMismatch
        ? "선택 형식과 제품 표시 불일치"
        : overlap.unconfirmed.length
          ? "형식·작업 구분 확인 전"
          : !useType
            ? "사용 형식 확인 전"
            : !workGroup
              ? "작업 구분 확인 전"
              : colours[colour(coverall)]?.label || "색상 확인 전";
  $("criteriaNote").textContent = activeKitReview
    ? activeKitReview.selection_reason
    : "물질과 작업에 맞는 제품을 먼저 검토합니다. 사업장에서 함께 쓰는 다른 형식과 별도 작업은 실제 보호복 색상을 구분합니다.";
  const overlapNote = colourOverlapText(overlap);
  if (overlapNote) $("criteriaNote").textContent += " " + overlapNote;
  const componentNotes = coverall?.set_components || {};
  $("kitPreview").innerHTML = parts
    .map((part) => {
      const p = product($(part.id).value);
      return `<div class="component">${p ? imageMarkup(p) : '<div class="empty-component">미선정</div>'}<h4>${part.label}</h4><p>${esc(p?.display_name || "후보를 선택하세요")}</p>${componentNotes[part.id] ? `<p class="small muted">${esc(componentNotes[part.id].reason)}</p>` : ""}</div>`;
    })
    .join("");
  $("respiratoryParts").innerHTML =
    respiratoryAddons
      .map(
        (id) =>
          `<span class="accessory-chip">${esc(product(id)?.identity.model || id)}<button type="button" data-remove-accessory="${esc(id)}" aria-label="${esc(product(id)?.identity.model || id)} 삭제">×</button></span>`,
      )
      .join("") ||
    '<p class="small muted">정화통·필터는 필요한 구성과 호환성을 확인한 뒤 추가합니다.</p>';
  $("cartCount").textContent = String(ids.length);
  $("reviewNote").textContent = ids.length
    ? "제품별 물질 성능과 호흡 부품·소매·장화 연결, 판매 실물의 인증을 함께 검토하세요. 저장은 검토용 초안입니다."
    : "사용 물질로 추천받거나 제품 후보를 선택해 조합을 구성하세요.";
  $("saveDraft").disabled = !ids.length;
  $("exportDraft").disabled = !ids.length;
}

function payload() {
  const ids = selectedProductIds(),
    selected = ids.map(product).filter(Boolean),
    coverall = product($("coverall").value);
  return {
    schema_version: "review_draft_v4",
    kit_id: activeKitId || crypto.randomUUID(),
    created_at: new Date().toISOString(),
    source_review_date: data.review_date,
    approved: false,
    draft_only: true,
    runtime_registration: false,
    synthesis_created: false,
    work_description: $("workZone").value.trim(),
    company_set_name: $("companyType").value.trim() || "사업장 보호구 조합",
    selected_use_type: kitUseType({ use_type: $("useType").value }),
    selected_work_group: kitWorkGroup({ work_group: $("workGroup").value }),
    selected_coverall_colour: coverall ? colour(coverall) : null,
    colour_policy: "material_first_site_type_work_group_colours",
    notes: $("exposureNote").value.trim(),
    components: Object.fromEntries(
      parts.map((part) => [part.id, $(part.id).value || null]),
    ),
    component_product_ids: Object.fromEntries(
      parts.map((part) => [
        part.id,
        selected
          .filter((p) => p.category === part.category)
          .map((p) => p.product_id),
      ]),
    ),
    respiratory_parts: respiratoryAddons,
    product_ids: ids,
    kit_review: activeKitReview,
    recommendation_evidence: recommendationEvidence,
    product_certification_snapshot: Object.fromEntries(
      selected.map((p) => [p.product_id, p.certifications]),
    ),
    component_system_notes: coverall?.set_components || null,
    purchase_links: Object.fromEntries(
      selected.map((p) => [p.product_id, p.domestic_purchase]),
    ),
  };
}

function loadKit(d) {
  $("workZone").value = d.work_description || d.work_zone || "";
  $("companyType").value = d.company_set_name || d.company_type || "";
  $("exposureNote").value = d.notes || d.exposure_note || "";
  $("useType").value = kitUseType(d) || "";
  $("workGroup").value = kitWorkGroup(d) || "";
  if (d.product_ids) applyProductIds(d.product_ids);
  else {
    parts.forEach(
      (part) =>
        ($(part.id).value =
          d.components?.[part.id] ||
          (part.id === "coverall" ? d.coverall_product_id : "") ||
          ""),
    );
    respiratoryAddons = d.respiratory_parts || [];
  }
  activeKitId = d.kit_id || null;
  activeKitReview = d.kit_review || null;
  recommendationEvidence = d.recommendation_evidence || null;
  $("draftExport").hidden = true;
  renderKit();
  showTab("kit");
  $("savedStatus").textContent =
    "저장한 작업 조합 초안을 불러왔습니다. 사업장의 사용 형식·작업 구분과 보호복 색상을 확인하세요.";
}

function getSavedDraft() {
  for (const key of draftKeys) {
    const value = localStorage.getItem(key);
    if (value) return JSON.parse(value);
  }
  return null;
}
