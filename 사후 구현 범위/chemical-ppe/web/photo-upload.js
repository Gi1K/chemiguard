// Postwork: user-selected photos stay in this tab until an explicit send.
let chatPhotos = [];
let preparingPhotos = false;
let photoSelectionVersion = 0;
const PHOTO_MAX_BYTES = 700000;

function refreshPhotoControls() {
  $("attachPhoto").disabled = busy || preparingPhotos || chatPhotos.length >= 2;
  $("chatPhotoInput").disabled = busy || preparingPhotos;
  $("chatSend").disabled = busy || preparingPhotos;
  $("chatSend").textContent = busy
    ? "검토 중…"
    : preparingPhotos
      ? "사진 준비 중…"
      : ready
        ? "보내기 ↑"
        : serverReady
          ? "상담 코드 입력"
          : "연결 다시 확인";
  document
    .querySelectorAll("[data-remove-chat-photo], .photo-review button")
    .forEach((b) => {
      b.disabled = busy || preparingPhotos || b.dataset.consumed === "true";
    });
}

function renderChatPhotos() {
  $("chatPhotoPreview").replaceChildren();
  chatPhotos.forEach((photo, index) => {
    const item = document.createElement("div");
    item.className = "chat-photo-preview";
    item.innerHTML = `<img src="${photo.dataUrl}" alt="첨부할 사진 ${index + 1}"><div><span>${esc(photo.name)}</span><button type="button" data-remove-chat-photo aria-label="사진 ${index + 1} 제거">제거</button></div>`;
    item.querySelector("button").addEventListener("click", () => {
      chatPhotos.splice(index, 1);
      renderChatPhotos();
    });
    $("chatPhotoPreview").append(item);
  });
  $("chatPhotoPreview").hidden = chatPhotos.length === 0;
  $("photoFeedback").textContent = chatPhotos.length
    ? `사진 ${chatPhotos.length}장 준비됨 · 보내기를 눌러야 전송됩니다.`
    : "";
  refreshPhotoControls();
}

function clearChatPhotos() {
  photoSelectionVersion++;
  chatPhotos = [];
  $("chatPhotoInput").value = "";
  renderChatPhotos();
}

async function prepareChatPhoto(file) {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type))
    throw new Error(
      "JPG·PNG·WebP 사진을 골라 주세요. HEIC 사진은 JPG로 저장한 뒤 첨부할 수 있어요.",
    );
  if (file.size > 10 * 1024 * 1024)
    throw new Error(
      "사진은 한 장에 10MB까지 선택할 수 있어요. 라벨 부분만 잘라 다시 골라 주세요.",
    );
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () =>
        reject(
          new Error(
            "사진을 열 수 없어요. 다른 JPG·PNG·WebP 사진을 골라 주세요.",
          ),
        );
      image.src = url;
    });
    const canvas = document.createElement("canvas");
    const scale = Math.min(
      1,
      2048 / Math.max(image.naturalWidth, image.naturalHeight),
    );
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.9, 0.8, 0.65, 0.5]) {
      const dataUrl = canvas.toDataURL("image/jpeg", quality);
      if ((dataUrl.length - dataUrl.indexOf(",") - 1) * 0.75 <= PHOTO_MAX_BYTES)
        return { name: file.name, dataUrl };
    }
    throw new Error(
      "사진이 너무 복잡해요. 라벨 글자 부분만 잘라 다시 골라 주세요.",
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function selectChatPhotos(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = "";
  if (!files.length || busy || preparingPhotos) return;
  if (chatPhotos.length + files.length > 2) {
    $("photoFeedback").textContent =
      "사진은 앞·뒷면 등 최대 2장까지 첨부할 수 있어요. 기존 사진을 제거한 뒤 골라 주세요.";
    return;
  }
  const version = ++photoSelectionVersion;
  preparingPhotos = true;
  refreshPhotoControls();
  $("photoFeedback").textContent = "사진을 준비하고 있어요…";
  try {
    const prepared = [];
    for (const file of files) prepared.push(await prepareChatPhoto(file));
    if (version !== photoSelectionVersion) return;
    chatPhotos.push(...prepared);
    renderChatPhotos();
  } catch (error) {
    if (version === photoSelectionVersion)
      $("photoFeedback").textContent = error.message;
  } finally {
    preparingPhotos = false;
    refreshPhotoControls();
  }
}

function renderPhotoReading(el, reading) {
  if (!reading) return;
  const review = document.createElement("section");
  review.className = "photo-review";
  review.innerHTML = `<strong>사진에서 읽은 내용 · 확인 전</strong>${reading.uncertainty ? `<p>${esc(reading.uncertainty)}</p>` : ""}`;
  if (reading.review_id) {
    const label = document.createElement("label");
    label.textContent = "라벨과 다른 글자는 여기서 수정해 주세요";
    const input = document.createElement("textarea");
    input.rows = 5;
    input.maxLength = 2000;
    input.value = reading.visible_text;
    label.append(input);
    review.append(label);
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.dataset.photoReview = reading.review_id;
    confirm.className = "primary";
    confirm.textContent = "이 내용으로 상담하기";
    confirm.addEventListener("click", () => {
      if (!input.value.trim()) {
        input.setCustomValidity("읽은 내용을 확인하거나 직접 적어 주세요.");
        input.reportValidity();
        return;
      }
      if (busy || preparingPhotos || confirm.disabled) return;
      submitChat(
        { preventDefault() {} },
        { review_id: reading.review_id, text: input.value.trim() },
      );
    });
    input.addEventListener("input", () => input.setCustomValidity(""));
    review.append(confirm);
  }
  const retry = document.createElement("button");
  retry.type = "button";
  retry.textContent = "다른 사진 첨부";
  retry.addEventListener("click", () => $("chatPhotoInput").click());
  review.append(retry);
  el.append(review);
}
