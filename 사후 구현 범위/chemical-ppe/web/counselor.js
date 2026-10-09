// Public counselor client (Agents or Responses) and evidence presentation.
let demoToken = "";
let serverReady = false;
const apiBase = window.PPE_CONFIG?.apiBase || "";
async function checkBackend() {
  try {
    const r = await fetch(`${apiBase}/api/ppe/status`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) throw new Error("상담 서버 상태를 확인하지 못했습니다.");
    const status = await r.json();
    if (!apiBase) {
      localPhotos = status.local_photos || {};
      renderHero();
      renderProducts();
      renderKit();
      renderWorksiteKits();
    }
    serverReady = status.ready === true;
    ready = serverReady && Boolean(demoToken);
    $("chatStatus").className = `badge ${ready ? "good" : "pending"}`;
    $("chatStatus").textContent = ready
      ? "상담 준비됨 · 시연 코드 확인 후 요청"
      : serverReady
        ? "시연 코드 필요"
        : "상담 설정 대기";
    $("chatProgress").textContent = ready
      ? "아는 내용만 편하게 적어 주세요. 제품명을 모르면 라벨 사진으로 시작해도 돼요."
      : serverReady
        ? "상담 접근 설정에 시연 코드를 입력하세요."
        : status.message ||
          "서버 상담 설정이 필요합니다. 제품 검색과 초안 저장은 사용할 수 있습니다.";
    $("accessPanel").open = serverReady && !demoToken;
  } catch {
    serverReady = ready = false;
    $("chatStatus").className = "badge pending";
    $("chatStatus").textContent = "상담 서버 연결 대기";
    $("chatProgress").textContent =
      "서버 연결을 확인하지 못했습니다. 제품 검색과 저장된 초안은 계속 사용할 수 있습니다.";
  }
  setBusy(busy);
}
function renderAnswer(el, response) {
  renderAnswerBase(el, response);
  renderPhotoReading(el, response.photo_reading);
  for (const source of response.live_lookup?.sources || []) {
    const rows = source.rows || [];
    const conditions = (source.notes || [])
      .map((n) => `<p>${esc(n)}</p>`)
      .join("");
    const table = rows.length
      ? `<div class="evidence-table"><table><thead><tr><th>물질 · CAS</th><th>농도 · 상태</th><th>온도</th><th>BT 0.1 / 1.0 (분)</th><th>원문 값</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.chemical_name)}<br>${esc(r.cas)}</td><td>${esc(r.concentration || "원문 미기재")} · ${esc(r.phase)}</td><td>${esc(r.temperature || "개별 행 미기재 · 시험 주석 확인")}</td><td>${esc(r.bt_0_1)} / ${esc(r.bt_1_0)}</td><td><details><summary>원문 시험 행</summary><pre>${esc(JSON.stringify(r.raw_values, null, 2))}</pre>${esc(JSON.stringify(r.footnotes || {}))}</details></td></tr>`).join("")}</tbody></table></div>`
      : '<p class="small muted">이번 조회에서 표시할 시험 행이 없습니다.</p>';
    el.insertAdjacentHTML(
      "beforeend",
      `<details class="live-fabric-evidence"><summary>${esc(source.title)} · 시험 조건과 원문</summary><p class="small">조회 ${esc(source.retrieved_at ? new Date(source.retrieved_at).toLocaleString("ko-KR") : "시각 미확인")} · ${esc((source.page_test_standards || []).join(", ") || "시험 규격 주석 확인")}</p>${table}<div class="evidence-note">원단 시험값이며 완제품 승인·현장 착용 가능 시간이 아닙니다.${conditions}<p>${esc(JSON.stringify(source.footnote_definitions || {}))}</p></div>${link(source.url, "제조사 원문 열기")}</details>`,
    );
  }
}
async function submitChat(event, confirmation = null) {
  event.preventDefault();
  const message = confirmation
    ? "사진에서 읽은 내용을 확인했어요. 이 내용으로 상담을 이어가 주세요."
    : $("chatInput").value.trim();
  if ((!message && !chatPhotos.length) || busy || preparingPhotos || !ready)
    return;
  if (confirmation && chatPhotos.length) {
    $("photoFeedback").textContent =
      "새 사진이 준비되어 있어요. 보내기로 사진을 먼저 확인하거나 사진을 제거해 주세요.";
    return;
  }
  const sentPhotos = [...chatPhotos];
  const userEntry = addMessage(
    "user",
    message || "사진으로 어떤 제품인지 확인하고 싶어요.",
  );
  if (sentPhotos.length) {
    const previews = document.createElement("div");
    previews.className = "sent-chat-photos";
    sentPhotos.forEach((photo, index) => {
      const img = document.createElement("img");
      img.src = photo.dataUrl;
      img.alt = `전송한 라벨 사진 ${index + 1}`;
      previews.append(img);
    });
    userEntry.append(previews);
  }
  if (confirmation) {
    const confirmed = document.createElement("p");
    confirmed.className = "confirmed-photo-text";
    confirmed.textContent = confirmation.text;
    userEntry.append(confirmed);
  }
  $("chatInput").value = "";
  const answer = addMessage(
    "assistant",
    sentPhotos.length
      ? "사진에서 읽을 수 있는 라벨 내용을 확인하고 있어요."
      : "말씀해 주신 내용을 확인하고 있어요.",
  );
  answer
    .querySelector("strong")
    .insertAdjacentHTML(
      "afterbegin",
      '<span class="loading-dot" aria-hidden="true"></span>',
    );
  setBusy(true);
  $("chatProgress").textContent = sentPhotos.length
    ? "사진의 글자를 확인 중 · 최대 약 3분"
    : "답변을 준비 중 · 최대 약 3분";
  try {
    const r = await fetch(`${apiBase}/api/ppe/chat`, {
      method: "POST",
      signal: AbortSignal.timeout(175000),
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${demoToken}`,
      },
      body: JSON.stringify({
        session_id: chatSession,
        message,
        photos: sentPhotos.map((p) => p.dataUrl),
        ...(confirmation ? { photo_confirmation: confirmation } : {}),
        auto_kit_options: true,
        existing_kits: savedKits.slice(-20).map((k) => ({
          name: k.company_set_name,
          use_type: kitUseType(k),
          work_group: kitWorkGroup(k),
          coverall_colour: k.selected_coverall_colour,
          product_ids: idsOfKit(k),
        })),
      }),
    });
    let response;
    try {
      response = await r.json();
    } catch {
      throw new Error("서버 응답을 읽지 못했습니다. 잠시 후 다시 요청하세요.");
    }
    if (!r.ok) {
      if (r.status === 401) {
        demoToken = "";
        ready = false;
        $("accessPanel").open = true;
        $("accessLabel").textContent = "시연 코드를 다시 확인하세요";
      }
      if (r.status === 410) chatSession = null;
      throw new Error(response.error || "상담 요청을 완료하지 못했습니다.");
    }
    chatSession = response.session_id;
    if (
      response.catalog_revision &&
      response.catalog_revision !== data.catalog_meta?.revision
    )
      await refreshCatalog(true);
    userMessages.push(message || "라벨 사진 첨부");
    if (confirmation || response.photo_reading) {
      document.querySelectorAll("[data-photo-review]").forEach((button) => {
        button.dataset.consumed = "true";
        button.disabled = true;
        button.textContent =
          confirmation && button.dataset.photoReview === confirmation.review_id
            ? "확인한 내용으로 상담 중"
            : "이전 사진 확인";
      });
    }
    clearChatPhotos();
    renderAnswer(answer, response);
    $("chatStatus").textContent = "상담 연결됨";
    $("chatProgress").textContent = response.photo_reading?.review_id
      ? "사진에서 읽은 글자를 확인하고 ‘이 내용으로 상담하기’를 눌러 주세요."
      : response.questions?.length
        ? "위 질문 하나에만 답해 주세요. 모르겠으면 그대로 말씀해도 괜찮아요."
        : "아는 내용이나 궁금한 점을 이어서 적어 주세요.";
  } catch (error) {
    answer.classList.add("chat-error");
    answer.querySelector(".message-text").textContent =
      error.name === "TimeoutError" || error.name === "AbortError"
        ? "상담 응답 시간이 초과되었습니다. 저장된 초안은 유지됩니다. 잠시 후 직접 다시 요청하세요."
        : error.message || "연결 오류가 발생했습니다.";
    $("chatInput").value = message;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "retry-chat";
    retry.textContent = "입력 확인 후 다시 보내기";
    retry.addEventListener("click", () => {
      $("chatInput").value = message;
      $("chatInput").focus();
    });
    answer.append(retry);
    $("chatProgress").textContent =
      "요청을 완료하지 못했습니다. 입력과 기존 초안을 보존했습니다. 자동으로 재요청하지 않습니다.";
  } finally {
    answer.querySelector(".loading-dot")?.remove();
    setBusy(false);
    $("chatInput").focus();
  }
}
