// New public Responses API client and evidence presentation.
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
      ? "물질·농도·온도·작업·노출 조건을 입력하세요."
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
async function submitChat(event) {
  event.preventDefault();
  const message = $("chatInput").value.trim();
  if (!message || busy || !ready) return;
  addMessage("user", message);
  $("chatInput").value = "";
  const answer = addMessage(
    "assistant",
    "물질과 작업 조건을 확인하고 제조사 근거를 조회하고 있습니다.",
  );
  answer
    .querySelector("strong")
    .insertAdjacentHTML(
      "afterbegin",
      '<span class="loading-dot" aria-hidden="true"></span>',
    );
  setBusy(true);
  $("chatProgress").textContent =
    "근거 조회 및 조합 검토 중 · 최대 약 2분 30초";
  try {
    const r = await fetch(`${apiBase}/api/ppe/chat`, {
      method: "POST",
      signal: AbortSignal.timeout(155000),
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${demoToken}`,
      },
      body: JSON.stringify({
        session_id: chatSession,
        message,
        auto_kit_options: true,
        existing_kits: savedKits
          .slice(-20)
          .map((k) => ({
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
    userMessages.push(message);
    renderAnswer(answer, response);
    $("chatStatus").textContent = "상담 연결됨";
    $("chatProgress").textContent =
      "조합의 근거와 남은 확인을 검토하세요. 추가 조건을 같은 대화에서 입력할 수 있습니다.";
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
