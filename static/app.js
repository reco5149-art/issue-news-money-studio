const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const state = {
  ratio: "4:5",
  asset: null,
  current: null,
  slide: 0,
  posts: [],
  status: null,
};
const labels = {
  draft: "초안",
  scheduled: "예약됨",
  published: "게시 완료",
  failed: "실패",
  publishing: "게시 중",
  needs_check: "확인 필요",
};
let toastTimer;
function toast(text, error = false) {
  $("toast").textContent = text;
  $("toast").className = error ? "error" : "";
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(
    () => ($("toast").hidden = true),
    error ? 14000 : 7000,
  );
}
async function api(path, options = {}) {
  let r;
  try {
    r = await fetch(path, {
      ...options,
      headers:
        options.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch {
    throw Error(
      "프로그램 연결이 끊겼습니다. start.bat 실행 상태를 확인하세요.",
    );
  }
  if (!r.ok) {
    let e;
    try {
      e = await r.json();
    } catch {
      e = { detail: "서버 요청 실패" };
    }
    throw Error(
      typeof e.detail === "string"
        ? e.detail
        : "입력값 또는 글자 수를 확인하세요.",
    );
  }
  return r.json();
}
async function busy(button, fn) {
  const old = button.textContent;
  button.disabled = true;
  button.textContent = "처리 중…";
  try {
    await fn();
  } catch (e) {
    toast(e.message, true);
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}
async function refresh() {
  [state.posts, state.status] = await Promise.all([
    api("/api/posts"),
    api("/api/status"),
  ]);
  $("nav-count").textContent = state.posts.filter(p => !p.trashed_at).length;
  const today = state.status.time.slice(0, 10);
  const count = state.posts.filter(
    (p) => p.created_at.slice(0, 10) === today,
  ).length;
  $("daily-count").textContent = count;
  const target = state.status.daily.daily_target;
  $("daily-target-label").textContent = ` / ${target}개`;
  $("daily-bar").style.width = Math.min(100, count * 100 / target) + "%";
  renderLibrary();
  renderSchedule();
  renderSettings();
}
function view(name) {
  document
    .querySelectorAll(".view")
    .forEach((v) => (v.hidden = v.id !== "view-" + name));
  document
    .querySelectorAll(".nav")
    .forEach((n) => n.classList.toggle("active", n.dataset.view === name));
  $("page-name").textContent = document.querySelector(
    `[data-view="${name}"] span`,
  ).textContent;
  if (name === "schedule") loadEvents();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
document
  .querySelectorAll(".nav")
  .forEach((b) => (b.onclick = () => view(b.dataset.view)));
document.querySelectorAll("[data-input]").forEach(
  (b) =>
    (b.onclick = () => {
      document
        .querySelectorAll("[data-input]")
        .forEach((x) => x.classList.toggle("selected", x === b));
      $("url-input").hidden = b.dataset.input !== "url";
    }),
);
document.querySelectorAll("[data-ratio]").forEach(
  (b) =>
    (b.onclick = () => {
      state.ratio = b.dataset.ratio;
      document
        .querySelectorAll("[data-ratio]")
        .forEach((x) => x.classList.toggle("selected", x === b));
    }),
);
$("source-text").oninput = () =>
  ($("char-count").textContent =
    $("source-text").value.length.toLocaleString() + " / 30,000");
const demo =
  "AI 답변, 그대로 믿어도 될까요?\nAI가 만든 답변에는 잘못된 정보가 포함될 수 있습니다.\n중요한 숫자와 날짜는 원문 자료에서 다시 확인하세요.\n출처 링크를 직접 열고 실제로 같은 내용이 있는지 비교하세요.\n개인정보와 비밀번호는 공개 AI 서비스에 입력하지 마세요.";
$("demo-btn").onclick = () => {
  $("source-link").value = "";
  $("source-review").open = true;
  $("source-text").value = demo;
  $("source-text").oninput();
  $("source-name").value = "시연용 자체 작성 원고";
  $("source-url").value = "";
  $("category").value = "AI";
  $("count").value = "5";
  toast("시연용 원고를 넣었습니다. 카드뉴스 생성하기를 눌러보세요.");
};
let importedLink = "";
let importPending = false;
async function importSource(url) {
  url = url.trim();
  if (!url) throw Error("영상 링크를 입력하세요.");
  if (importPending) throw Error("영상 내용을 분석 중입니다. 완료 후 생성하세요.");
  importPending = true;
  importedLink = "";
  $("source-link").value = url;
  $("import-status").textContent = "자막 또는 음성을 분석 중입니다. 영상 길이에 따라 몇 분 걸릴 수 있습니다.";
  try {
  const data = await api("/api/import", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  if ($("source-link").value.trim() !== url)
    throw Error("분석 중 링크가 바뀌었습니다. 새 링크의 내용을 다시 가져오세요.");
  importedLink = url;
  $("source-link").value = url;
  $("source-text").value = data.text;
  $("source-text").oninput();
  $("source-name").value = data.source_name;
  $("source-url").value = data.source_url;
  $("import-status").textContent = data.warning || "원문을 가져왔습니다.";
  toast(data.warning || "원문을 가져왔습니다.");
  } catch (error) {
    $("import-status").textContent = error.message;
    $("source-review").open = true;
    throw error;
  } finally { importPending = false; }
}
$("import-btn").onclick = () =>
  busy($("import-btn"), () => importSource($("source-link").value));
$("manual-transcript-btn").onclick = () => {
  if (importPending) return toast("영상 분석이 끝난 후 입력하세요.", true);
  if ($("source-text").value.trim().length < 20)
    return toast("직접 확인한 자막을 20자 이상 입력하세요.", true);
  importedLink = $("source-link").value.trim();
  $("source-url").value = importedLink;
  $("source-name").value = "사용자가 직접 확인한 영상 자막";
  $("import-status").textContent = "직접 입력한 자막을 사용합니다. 자동으로 영상을 분석한 결과가 아닙니다.";
  toast("입력한 자막으로 생성할 준비가 되었습니다.");
};
function showPreview() {
  const p = state.current;
  if (!p) return;
  state.slide = Math.min(state.slide, p.images.length - 1);
  const container = $("preview-card");
  container.className = "";
  container.innerHTML = `<img class="preview-img" src="${esc(p.images[state.slide])}?v=${Date.now()}" alt="${esc(p.slides[state.slide].title)}">`;
  $("preview-label").textContent = `${p.ratio} · ${p.slides.length}장`;
  $("preview-pager").hidden = false;
  $("result-actions").hidden = false;
  $("slide-position").textContent = `${state.slide + 1} / ${p.slides.length}`;
  $("engine-note").textContent = p.engine_note + " · " + ({passed:"자가평가 통과",blocked:"자가평가 미달: 문안 편집에서 확인",stale:"재평가 필요",error:"평가 실패: 재평가 필요"}[p.quality?.status] || "자가평가 필요");
  $("download-btn").href = `/api/posts/${p.id}/download`;
}
$("prev-slide").onclick = () => {
  if (state.current) {
    state.slide =
      (state.slide - 1 + state.current.images.length) %
      state.current.images.length;
    showPreview();
  }
};
$("next-slide").onclick = () => {
  if (state.current) {
    state.slide = (state.slide + 1) % state.current.images.length;
    showPreview();
  }
};
$("generate-btn").onclick = () =>
  busy($("generate-btn"), async () => {
    const link = $("source-link").value.trim();
    if (importPending) throw Error("영상 내용을 분석 중입니다. 완료 후 생성하세요.");
    if (link && importedLink !== link) await importSource(link);
    const text = $("source-text").value.trim();
    if (text.length < 5) throw Error("주제나 원고를 5자 이상 입력하세요.");
    let videoAssets = [];
    let imageMode = $("image-mode").value;
    if (imageMode === "web" && !state.asset)
      toast("AI가 카드별 검색어로 사진을 찾아 검토하고 있습니다. 잠시 기다려 주세요.");
    if (imageMode === "upload" && !state.asset)
      throw Error("사용할 사진 파일을 업로드한 후 생성하세요.");
    if ($("image-mode").value === "video") {
      toast("영상에서 카드별 장면을 자동 캡처하고 있습니다.");
      videoAssets = await captureVideoFrames(Number($("count").value));
      if (!videoAssets.length && Number($("count").value) === 0) imageMode = "design";
    }
    const body = {
      video_asset_ids: videoAssets,
      text,
      category: $("category").value,
      tone: $("tone").value,
      ratio: state.ratio,
      count: Number($("count").value),
      engine: $("engine").value,
      image_mode: imageMode,
      ai_image_provider: $("ai-image-provider")?.value || "openai",
      asset_id: state.asset?.asset_id || "",
      source_name: $("source-name").value || "직접 입력",
      source_url: $("source-url").value,
      cta: $("cta").value,
    };
    state.current = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.slide = 0;
    showPreview();
    await refresh();
    toast(imageMode === "design" && $("image-mode").value === "video"
      ? "적합한 영상 사진이 없어 텍스트 카드로 자동 구성했습니다. 문안을 확인하세요."
      : (state.current.generation_note || "카드뉴스를 만들었습니다. 문안을 확인하고 파일로 저장하세요."));
  });
function setAsset(a) {
  state.asset = a;
  $("asset-preview").src = a.url;
  $("asset-preview").hidden = false;
  if ($("web-image-status")) $("web-image-status").textContent = "사진 선택 완료. 아래 미리보기 사진이 카드에 적용됩니다. 생성하기를 눌러 주세요.";
  toast("이미지를 선택했습니다. 생성 시 카드에 적용됩니다.");
}
function waitVideo(video, event, action) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => done(new Error("영상 읽기가 지연됩니다. MP4 파일을 다시 선택하세요.")), 15000);
    const ok = () => done();
    const fail = () => done(new Error("브라우저에서 읽을 수 없는 영상입니다. MP4 파일을 선택하세요."));
    function done(error) { clearTimeout(timer); video.removeEventListener(event, ok); video.removeEventListener("error", fail); error ? reject(error) : resolve(); }
    video.addEventListener(event, ok, {once:true}); video.addEventListener("error", fail, {once:true});
    if (action) action();
  });
}
async function captureVideoFrames(count) {
  const v = $("local-video");
  if (!$("video-file")?.files.length) {
    const url = $("source-url").value.trim() || $("source-link").value.trim();
    if (!url) throw Error("영상 파일을 선택하거나 유튜브 링크를 가져오세요.");
    const result = await api("/api/video/frames", {method:"POST", body:JSON.stringify({url,count})});
    toast(result.note);
    return result.assets.map(a => a.asset_id);
  }
  if (v.readyState < 2) await waitVideo(v, "loadeddata");
  if (!Number.isFinite(v.duration) || v.duration <= 0 || v.duration > 1200) throw Error("20분 이하의 일반 영상 파일을 선택하세요.");
  v.pause();
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 3840 / v.videoWidth);
  canvas.width = Math.round(v.videoWidth * scale); canvas.height = Math.round(v.videoHeight * scale);
  const assets = [];
  const candidates = count === 0 ? 20 : Math.min(20, count * 3);
  for (let i=0; i<candidates; i++) {
    const at = v.duration * (i + .5) / candidates;
    if (Math.abs(v.currentTime - at) > .001) await waitVideo(v, "seeked", () => { v.currentTime = at; });
    canvas.getContext("2d").drawImage(v, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", .92));
    if (!blob) throw Error("영상 장면을 캡처하지 못했습니다.");
    const form = new FormData(); form.append("file", blob, `capture-${i+1}.jpg`);
    const asset = await api("/api/assets/upload", {method:"POST",body:form}); assets.push(asset.asset_id);
  }
  const cleaned = await api("/api/video/clean-frames", {method:"POST",body:JSON.stringify({asset_ids:assets,count})});
  return cleaned.assets.map(a => a.asset_id);
}
let videoObjectUrl = null;
$("image-mode").onchange = () => {
  state.asset = null;
  $("asset-preview").hidden = true;
  const mode = $("image-mode").value;
  const box = $("asset-controls");
  box.innerHTML = "";
  if (videoObjectUrl) {
    URL.revokeObjectURL(videoObjectUrl);
    videoObjectUrl = null;
  }
  if (mode === "ai") {
    box.innerHTML =
      '<label for="ai-image-provider">AI 이미지 엔진</label><select id="ai-image-provider"><option value="kie" selected>KIE AI · 기본 nano-banana-2</option><option value="openai">OpenAI · gpt-image-1</option></select><p class="hint">카드마다 이미지를 1장씩 생성하므로 장수만큼 크레딧·이용료가 발생합니다. KIE AI는 카드 사진 영역 비율로 만들며 장당 수십 초 걸릴 수 있습니다. 생성된 이미지는 설명용이며 실제 보도사진이 아닙니다.</p>';
  }
  if (mode === "upload") {
    box.innerHTML =
      '<label for="image-file">사진 파일 · 15MB 이하</label><input id="image-file" type="file" accept="image/png,image/jpeg,image/webp">';
    $("image-file").onchange = async () => {
      try {
        const file = $("image-file").files[0];
        if (!file) return;
        const form = new FormData();
        form.append("file", file);
        setAsset(
          await api("/api/assets/upload", { method: "POST", body: form }),
        );
      } catch (e) {
        toast(e.message, true);
      }
    };
  }
  if (mode === "video") {
    box.innerHTML =
      '<label for="video-file">영상 파일 (선택 · 공개 영상 링크는 생략 가능)</label><input id="video-file" type="file" accept="video/*"><video id="local-video" controls hidden></video><p class="hint">링크의 영상을 캡처하고 약 1.1배 확대를 먼저 시도합니다. 방송 로고·자막은 화면 밖으로 크롭하고 얼굴이나 핵심 동작이 잘리는 장면은 제외합니다. 제목과 본문은 짧게, 캡션은 링크 없이 생성합니다. 상세 출처는 편집 정보에 보관합니다. 공개 유튜브·인스타그램·틱톡 또는 보유 영상, 20분·150MB 이하. AI 장면 정리 비용이 발생합니다.</p>';
    $("video-file").onchange = () => {
      if (videoObjectUrl) URL.revokeObjectURL(videoObjectUrl);
      const f = $("video-file").files[0];
      if (f) {
        if (f.size > 150000000) { toast("영상은 150MB 이하로 선택하세요.", true); $("video-file").value = ""; return; }
        videoObjectUrl = URL.createObjectURL(f);
        $("local-video").src = videoObjectUrl;
        $("local-video").hidden = false;
      }
    };

  }
  if (mode === "web") {
    box.innerHTML =
      '<p class="hint" id="web-image-status" role="status">사진을 고르지 않고 생성하기를 누르면 AI가 카드별 웹 사진을 자동 검색·선택합니다. 적합한 사진이 없으면 자체 디자인으로 구성합니다. 직접 검색·선택도 가능합니다. 사진 검토에는 AI API 비용이 발생합니다.</p><label for="image-query">직접 사진 선택 (선택 사항) · 영문 검색 권장</label><div class="input-row"><input id="image-query" placeholder="artificial intelligence"><button id="search-images" class="secondary">검색</button></div><div id="image-results" class="image-results"></div>';
    $("search-images").onclick = () =>
      busy($("search-images"), async () => {
        const query = $("image-query").value.trim();
        if (!query) throw Error("이미지 검색어를 먼저 입력하세요. 예: skateboard, city, technology");
        $("web-image-status").textContent = "사진을 검색하고 있습니다…";
        let list;
        try { list = await api(
          "/api/images/search?q=" + encodeURIComponent(query),
        );
        } catch (e) { $("web-image-status").textContent = "검색 실패: " + e.message; throw e; }
        $("web-image-status").textContent = list.length ? "검색 완료. 사용할 사진 아래의 ‘선택’을 눌러 주세요." : "검색 결과가 없습니다. 다른 검색어로 시도해 주세요.";
        $("image-results").innerHTML = list.length
          ? list
              .map(
                (x, i) =>
                  `<div class="image-result"><img src="${esc(x.thumbnail || x.url)}" alt="${esc(x.title)}"><p>${esc(x.credit)} · ${esc(x.license)}</p><a href="${esc(x.page)}" target="_blank" rel="noreferrer">이용 조건 ↗</a><button data-image="${i}" class="secondary">선택</button></div>`,
              )
              .join("")
          : "검색 결과가 없습니다. 다른 검색어를 사용하세요.";
        document.querySelectorAll("[data-image]").forEach(
          (b) =>
            (b.onclick = () =>
              busy(b, async () => {
                const x = list[Number(b.dataset.image)];
                setAsset(
                  await api("/api/assets/web", {
                    method: "POST",
                    body: JSON.stringify({
                      url: x.url,
                      credit: `${x.title} / ${x.credit} / ${x.license} / ${x.license_url} / ${x.page} / 카드 비율 크롭·색감 보정`.slice(
                        0,
                        1000,
                      ),
                    }),
                  }),
                );
              })),
        );
      });
  }
  if (mode === "ai")
    box.innerHTML +=
      '<p class="notice">API 사용료가 발생합니다. 문안을 만든 뒤 각 카드의 제목·본문에 맞는 설명용 이미지를 1장씩 생성합니다. 카드 5장이면 이미지 5장 비용과 대기 시간이 발생합니다. 실제 보도사진이 아닙니다.</p>';
};
const librarySelected = new Set();
function updateLibrarySelection() {
  const boxes = [...document.querySelectorAll("[data-select-post]")];
  const selected = boxes.filter(b => librarySelected.has(b.dataset.selectPost));
  $("library-selection-count").textContent = `${selected.length}개 선택`;
  $("library-select-all").checked = boxes.length > 0 && selected.length === boxes.length;
  $("library-select-all").indeterminate = selected.length > 0 && selected.length < boxes.length;
  $("library-delete").disabled = $("library-restore").disabled = selected.length === 0;
  $("library-delete").hidden = $("library-filter").value === "trash";
  $("library-restore").hidden = $("library-filter").value !== "trash";
  $("library-schedule").disabled = selected.length === 0;
  $("library-schedule").hidden = $("library-filter").value === "trash";
}
$("library-schedule").onclick = () => busy($("library-schedule"), async () => {
  const ids = [...document.querySelectorAll("[data-select-post]")].filter(b => b.checked).map(b => b.dataset.selectPost);
  if (!ids.length) return;
  const result = await api("/api/schedule/batch", {method:"POST",body:JSON.stringify({post_ids:ids})});
  librarySelected.clear();
  await refresh();
  view("schedule");
  toast(`${result.reservations.length}개를 시간대별로 예약했습니다. 아래 게시 시각을 확인하세요.`);
}).finally(updateLibrarySelection);
$("library-select-all").onchange = e => {
  document.querySelectorAll("[data-select-post]").forEach(b => {
    b.checked = e.target.checked;
    if (b.checked) librarySelected.add(b.dataset.selectPost); else librarySelected.delete(b.dataset.selectPost);
  });
  updateLibrarySelection();
};
for (const action of ["delete", "restore"]) {
  $("library-" + action).onclick = () => busy($("library-" + action), async () => {
    const ids = [...document.querySelectorAll("[data-select-post]")].filter(b => b.checked).map(b => b.dataset.selectPost);
    if (!ids.length) return;
    await api("/api/library/" + (action === "delete" ? "trash" : "restore"), {method:"POST",body:JSON.stringify(ids)});
    librarySelected.clear();
    await refresh();
    toast(`${ids.length}개를 ${action === "delete" ? "휴지통으로 이동했습니다. 예약은 취소됩니다." : "복원했습니다. 예약은 자동 복구되지 않습니다."}`);
  }).finally(updateLibrarySelection);
}
function renderLibrary() {
  const filter = $("library-filter").value;
  const items = state.posts.filter(
    (p) => filter === "trash" ? !!p.trashed_at : !p.trashed_at && (filter === "all" || p.status === filter),
  );
  $("library-grid").innerHTML = items.length
    ? items
        .map(
          (p) =>
            `<article class="content-card">${["publishing","needs_check"].includes(p.status) ? '<p class="hint">게시 결과 확인 후 삭제할 수 있습니다.</p>' : `<label style="display:flex;gap:8px;align-items:center;margin-bottom:12px"><input type="checkbox" style="width:auto" data-select-post="${p.id}" aria-label="${esc(p.slides[0].title)} 선택" ${librarySelected.has(p.id) ? "checked" : ""}>콘텐츠 선택</label>`}<img loading="lazy" src="${esc(p.images[0])}" alt="${esc(p.slides[0].title)}"><p><span class="badge">${labels[p.status]}</span>${esc(p.category)} · ${p.ratio} · ${p.slides.length}장</p><h3>${esc(p.slides[0].title)}</h3><div class="input-row">${p.trashed_at ? '<span class="hint">복원 후 편집할 수 있습니다.</span>' : `<button class="secondary" data-open="${p.id}">검토 · 예약</button>`}<a class="primary" href="/api/posts/${p.id}/download">다운로드</a></div>${p.error ? `<p>${esc(p.error)}</p>` : ""}${p.status === "draft" && p.automation_hold ? `<p class="hint">자동 제작 보류: ${esc(p.automation_hold)}</p>` : ""}</article>`,
        )
        .join("")
    : '<div class="empty">아직 만든 카드뉴스가 없습니다.<br>예시 원고로 첫 콘텐츠를 만들어보세요.</div>';
  document.querySelectorAll("[data-select-post]").forEach(b => b.onchange = () => {
    if (b.checked) librarySelected.add(b.dataset.selectPost); else librarySelected.delete(b.dataset.selectPost);
    updateLibrarySelection();
  });
  updateLibrarySelection();
  document.querySelectorAll("[data-open]").forEach(
    (b) =>
      (b.onclick = () => {
        state.current = state.posts.find((p) => p.id === b.dataset.open);
        openEditor();
      }),
  );
}
$("library-filter").onchange = () => { librarySelected.clear(); renderLibrary(); };
let editorDirty = false;
function openEditor() {
  editorDirty = false;
  const p = state.current;
  if (!p) return;
  const writable = ["draft", "failed"].includes(p.status);
  $("editor-slides").innerHTML = p.slides
    .map(
      (s, i) =>
        `<div class="slide-editor"><small>${String(i + 1).padStart(2, "0")} / ${p.slides.length}</small><label for="title-${i}">제목</label><input id="title-${i}" value="${esc(s.title)}" maxlength="65"><label for="photo-${i}">이 카드 사진 교체</label><input type="file" id="photo-${i}" accept="image/*" data-asset-id="${esc(s.asset_id || p.asset_id || "")}" ${writable ? "" : "disabled"}><small>선택한 사진은 이 카드에만 적용됩니다. 문안 변경 후에는 사진도 다시 확인하세요.</small><label for="body-${i}">본문</label><textarea id="body-${i}" rows="3" maxlength="230">${esc(s.body)}</textarea></div>`,
    )
    .join("");
  p.slides.forEach((_, i) => {
    const input = $("photo-" + i);
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      $("save-edit").disabled = true;
      input.disabled = true;
      try {
        const form = new FormData(); form.append("file", file);
        const asset = await api("/api/assets/upload", {method: "POST", body: form});
        input.dataset.assetId = asset.asset_id;
        editorDirty = true;
        $("rights-check").checked = false;
        toast(`${i + 1}번 카드 사진을 선택했습니다. 저장하면 반영됩니다.`);
      } catch (e) { toast(e.message); }
      finally { input.disabled = !writable; $("save-edit").disabled = !writable || Array.from(document.querySelectorAll('[id^="photo-"]')).some(x => x.disabled); }
    };
  });
  $("edit-caption").value = p.caption;
  $("edit-source-name").value = p.source_name;
  $("edit-source-url").value = p.source_url;
  $("facts-check").checked = p.facts_checked;
  $("rights-check").checked = p.rights_checked;
  $("save-edit").disabled = !writable;
  renderQuality(p);
  $("evaluate-post").disabled = !writable;
  $("schedule-at").value = "";
  $("editor").showModal();
}
$("edit-btn").onclick = openEditor;
$("close-editor").onclick = () => $("editor").close();
async function saveEditor() {
    const p = state.current;
    const body = {
      slides: p.slides.map((_, i) => ({
        title: $("title-" + i).value,
        body: $("body-" + i).value,
        asset_id: $("photo-" + i).dataset.assetId || null,
      })),
      caption: $("edit-caption").value,
      source_name: $("edit-source-name").value,
      source_url: $("edit-source-url").value,
      facts_checked: $("facts-check").checked,
      rights_checked: $("rights-check").checked,
    };
    state.current = await api("/api/posts/" + p.id, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    showPreview();
    editorDirty = false;
    renderQuality(state.current);
    $("facts-check").checked = state.current.facts_checked;
    $("rights-check").checked = state.current.rights_checked;
}
let editorWorking = false;
async function editorAction(fn) {
  if (editorWorking) return;
  if ([...document.querySelectorAll('[id^="photo-"]')].some(el => el.disabled) && ["draft", "failed"].includes(state.current.status)) {
    toast("사진 업로드가 끝난 후 다시 시도하세요.", true); return;
  }
  editorWorking = true;
  const controls = [...document.querySelectorAll('#editor input, #editor textarea, #editor button')];
  const disabled = controls.map(el => el.disabled);
  controls.forEach(el => el.disabled = true);
  $("editor-notice").textContent = "처리 중입니다. 잠시 기다려 주세요.";
  try { await fn(); }
  catch (e) { $("editor-notice").textContent = e.message; toast(e.message, true); }
  finally {
    editorWorking = false;
    controls.forEach((el, i) => el.disabled = disabled[i]);
    const writable = ["draft", "failed"].includes(state.current.status);
    ["save-edit", "evaluate-post", "schedule-post", "approve-post"].forEach(id => $(id).disabled = !writable);
  }
}
$("save-edit").onclick = () => editorAction(async () => {
  await saveEditor();
  $("editor-notice").textContent = "저장 완료. " + reservationReason(state.current);
  await refresh();
});
function reservationReason(p) {
  if (editorDirty) return "수정 사항이 있습니다. 재평가 또는 예약 시 먼저 저장합니다.";
  const q = p.quality || {};
  if (q.status === "blocked") {
    const failed = (q.cards || []).filter(c => c.critical || c.sync < 25 || c.grounding < 20 || c.hook+c.sync+c.grounding+c.cta < 65);
    return "예약 보류: " + failed.map(c => `${c.card}번 카드 (${[
      c.critical ? "중대 오류" : "",
      c.sync < 25 ? `사진 일치 ${c.sync}/25점 미달` : "",
      c.grounding < 20 ? `원고 근거 ${c.grounding}/20점 미달` : "",
      c.hook+c.sync+c.grounding+c.cta < 65 ? "총점 65점 미달" : ""
    ].filter(Boolean).join(", ")})`).join(" · ") + ". 수정 후 재평가하거나, 사실·사용권 확인 후 ‘점수 경고 확인 · 게시 승인’을 누르세요.";
  }
  if (q.status !== "passed") return "예약 전 저장된 내용 다시 평가가 필요합니다.";
  if (!p.facts_checked || !p.rights_checked) return "평가 통과. 사실관계와 사진 사용권을 직접 확인하고 두 항목에 체크하세요.";
  return "평가 통과. 미래의 예약 날짜와 시간을 선택한 후 예약하기를 누르세요.";
}
function renderQuality(p) {
  const q = p.quality || {};
  $("approve-post").hidden = q.status !== "blocked" || (q.cards || []).some(c => c.critical);
  const labels = {evaluating:"평가 중",passed:"통과",blocked:"게시 보류",stale:"수정 후 재평가 필요",error:"평가 실패"};
  $("quality-result").innerHTML = `<p><b>${esc(q.manual_approved ? "사용자 게시 승인" : labels[q.status] || "평가 필요")}</b> ${esc(q.message || "")}</p>` + (q.cards || []).map(c => `<p><b>${c.card}번 · ${c.hook+c.sync+c.grounding+c.cta}/100점${c.critical ? " · 중대 오류" : ""}</b><br>후킹 ${c.hook}/25 · 사진 일치 ${c.sync}/40 · 원고 근거 ${c.grounding}/25 · CTA ${c.cta}/10<br>${esc(c.reason)}<br>수정 제안: ${esc(c.fix)}</p>`).join("");
  $("editor-notice").textContent = reservationReason(p);
  $("schedule-post").disabled = editorWorking || !["draft","failed"].includes(p.status);
}
$("editor").addEventListener("input", e => {
  if (e.target.id !== "schedule-at") {
    editorDirty = true;
    $("editor-notice").textContent = reservationReason(state.current);
  }
});
$("evaluate-post").onclick = () => editorAction(async () => {
  if (editorDirty) await saveEditor();
  state.current.quality = {status:"evaluating", message:"카드 이미지와 문안을 검토하고 있습니다."};
  renderQuality(state.current);
  $("editor-notice").textContent = "저장된 카드 이미지를 평가 중입니다…";
  try { state.current = await api(`/api/posts/${state.current.id}/evaluate`, {method:"POST"}); }
  catch (e) { state.current.quality = {status:"error", message:e.message}; renderQuality(state.current); throw e; }
  renderQuality(state.current); showPreview(); await refresh();
  toast(state.current.quality.status === "passed" ? "평가를 통과했습니다. 사실·권한 확인 후 예약하세요." : "게시를 보류했습니다. 수정 제안을 확인하세요.");
});
$("approve-post").onclick = () => editorAction(async () => {
  if (editorDirty) await saveEditor();
  state.current = await api(`/api/posts/${state.current.id}/approve`, {method:"POST"});
  renderQuality(state.current); showPreview(); await refresh();
  toast("게시 승인 완료. 날짜와 시간을 선택해 예약하세요.");
});
$("schedule-post").onclick = () =>
  editorAction(async () => {
    if (editorDirty) await saveEditor();
    if (state.current.quality?.status !== "passed" || !state.current.facts_checked || !state.current.rights_checked)
      throw Error(reservationReason(state.current));
    if (!$("schedule-at").value)
      throw Error("게시할 날짜와 시간을 선택하세요.");
    if (new Date($("schedule-at").value + "+09:00").getTime() <= Date.now())
      throw Error("현재보다 이후의 예약 시간을 선택하세요. 한국 시간 기준입니다.");
    state.current = await api(`/api/posts/${state.current.id}/schedule`, {
      method: "POST",
      body: JSON.stringify({ at: $("schedule-at").value + "+09:00" }),
    });
    $("editor").close();
    await refresh();
    view("schedule");
    toast("게시를 예약했습니다. 프로그램을 켜두세요.");
  });
$("discover-btn").onclick = () =>
  busy($("discover-btn"), async () => {
    const data = await api(
      "/api/discover?category=" +
        encodeURIComponent($("discover-category").value),
    );
    $("discover-results").innerHTML = data.items.length
      ? data.items
          .map(
            (x, i) =>
              `<article class="content-card"><span class="badge">${esc(x.source)}</span><span class="badge">우선순위 ${x.score}</span><h3>${esc(x.title)}</h3><p>${esc(x.summary)}</p><p>${x.views === null ? "조회수 제공 없음" : x.views.toLocaleString() + " 조회"}<br>${esc(x.score_basis)}</p><div class="input-row"><a class="secondary" href="${esc(x.url)}" target="_blank" rel="noreferrer">원문 ↗</a><button class="primary" data-import="${i}">원고로 가져오기</button></div></article>`,
          )
          .join("")
      : '<div class="empty">조건에 맞는 소재를 찾지 못했습니다.</div>';
    document.querySelectorAll("[data-import]").forEach(
      (b) =>
        (b.onclick = () =>
          busy(b, async () => {
            const x = data.items[Number(b.dataset.import)];
            await importSource(x.url);
            $("category").value = x.category;
            view("create");
          })),
    );
    if (data.warnings.length) toast(data.warnings.join(" / "), true);
  });
for (let h = 0; h < 24; h++)
  $("daily-hour").add(new Option(String(h).padStart(2, "0") + ":00", h));
function renderSchedule() {
  const c = state.status.daily;
  $("daily-enabled").checked = c.enabled;
  $("daily-hour").value = c.hour;
  $("daily-target").value = c.daily_target;
  const cadence = state.status.cadence;
  $("cadence-enabled").checked = cadence.enabled;
  $("cadence-limit").value = cadence.daily_limit;
  $("cadence-start").value = cadence.start_hour;
  $("cadence-size").value = cadence.batch_size;
  $("cadence-batch-gap").value = cadence.batch_interval;
  $("cadence-item-gap").value = cadence.item_interval;
  const times = [];
  for (let start = cadence.start_hour * 60; start < 1440 && times.length < cadence.daily_limit; start += cadence.batch_interval) {
    for (let i = 0; i < cadence.batch_size && times.length < cadence.daily_limit; i++) {
      const minute = start + i * cadence.item_interval;
      if (minute >= 1440 || (minute >= 60 && minute < 360)) continue;
      times.push(`${String(Math.floor(minute / 60)).padStart(2,"0")}:${String(minute % 60).padStart(2,"0")}`);
    }
  }
  $("cadence-summary").textContent = `${cadence.enabled ? (cadence.autopilot ? "자동 제작·게시 켜짐" : "검토 완료 글 자동 예약만 켜짐") : "자동 예약 꺼짐"} · 하루 최대 ${cadence.daily_limit}개 · 게시물 사이 최소 ${cadence.item_interval}분 · ${times.join(" / ")}`;
  $("autopilot-status").textContent = (state.status.autopilot?.message || "아직 자동 제작 전입니다.") + sourcePolicyLabel(state.status);
  renderOperations(state.status);
  const posts = state.posts
    .filter((p) =>
      ["scheduled", "publishing", "needs_check"].includes(p.status),
    )
    .sort((a, b) => (a.scheduled_at || "").localeCompare(b.scheduled_at || ""));
  $("scheduled-list").innerHTML = posts.length
    ? posts
        .map(
          (p) =>
            `<div class="schedule-item"><div>${esc(p.slides[0].title)}<small>${esc(p.scheduled_at?.replace("T", " ").slice(0, 16))} · ${labels[p.status]}</small></div>${p.status === "scheduled" ? `<button class="secondary" data-cancel="${p.id}">예약 취소</button>` : ""}</div>`,
        )
        .join("")
    : '<div class="empty">예약된 게시물이 없습니다. 보관함에서 검토 후 예약하세요.</div>';
  document.querySelectorAll("[data-cancel]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          await api(`/api/posts/${b.dataset.cancel}/cancel`, {
            method: "POST",
          });
          await refresh();
          toast("예약을 취소했습니다.");
        })),
  );
}
$("daily-save").onclick = () =>
  busy($("daily-save"), async () => {
    await api("/api/daily", {
      method: "PUT",
      body: JSON.stringify({
        enabled: $("daily-enabled").checked,
        hour: Number($("daily-hour").value),
        daily_target: Number($("daily-target").value),
        categories: ["뉴스", "이슈", "연예", "경제", "AI"],
      }),
    });
    await refresh();
    toast("일일 생성 설정을 저장했습니다.");
  });
$("daily-run").onclick = () =>
  busy($("daily-run"), async () => {
    const r = await api("/api/daily/run", { method: "POST" });
    await refresh();
    await loadEvents();
    toast(r.message);
  });
$("cadence-save").onclick = () => busy($("cadence-save"), async () => {
  await api("/api/posting-cadence", {method:"PUT",body:JSON.stringify({
    enabled:$("cadence-enabled").checked, autopilot:$("cadence-enabled").checked, daily_limit:Number($("cadence-limit").value),
    start_hour:Number($("cadence-start").value), batch_size:Number($("cadence-size").value),
    batch_interval:Number($("cadence-batch-gap").value), item_interval:Number($("cadence-item-gap").value)
  })});
  await refresh();
  toast($("cadence-enabled").checked ? "자동 제작·검증·예약·게시를 켰습니다. 통과한 새 콘텐츠부터 게시합니다." : "자동 제작을 껐습니다. 이미 예약된 글은 개별 취소할 수 있습니다.");
});
$("autopilot-retry").onclick = () => busy($("autopilot-retry"), async () => {
  const result = await api("/api/autopilot/retry", {method:"POST"});
  await refresh();
  toast(result.message);
});
async function loadEvents() {
  try {
    const d = await api("/api/events");
    $("events").innerHTML = d.events.length
      ? d.events
          .map(
            (x) =>
              `<div class="event"><time>${esc(x.at.slice(0, 19).replace("T", " "))}</time>${esc(x.message)}</div>`,
          )
          .join("")
      : '<p class="hint">아직 실행 기록이 없습니다.</p>';
  } catch (e) {
    toast(e.message, true);
  }
}
function renderSettings() {
  const list = [
    [
      "ai",
      state.status.ai_settings?.provider === "semyung" ? "학교 AI · 세명대학교" : "개인 OpenAI",
      "연결 선택: AI_PROVIDER · 학교 설정: set-school-api.bat",
      `문안 모델: ${esc(state.status.ai_settings?.models?.text || "기본 모델")} · 학교 연결에서는 문안·사진 검수를 지원합니다. 음성 전사·AI 이미지 생성은 미지원이며 개인 API로 자동 전환하지 않습니다.`,
    ],
    [
      "kie",
      "KIE AI 이미지",
      "KIE_API_KEY (선택: KIE_IMAGE_MODEL / KIE_IMAGE_RESOLUTION)",
      "카드별 AI 이미지 생성",
    ],
    [
      "news",
      "Naver 뉴스",
      "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET",
      "실시간 뉴스 검색 및 일일 소재 수집",
    ],
    [
      "youtube",
      "YouTube",
      "YOUTUBE_API_KEY",
      "인기 영상 조회수, 영상 제목·설명 불러오기",
    ],
    [
      "instagram",
      "Instagram",
      "INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_USER_ID / PUBLIC_MEDIA_BASE_URL",
      "검토를 마친 콘텐츠 예약 게시",
    ],
  ];
  $("connection-grid").innerHTML = list
    .map(
      ([key, name, env, desc]) =>
        `<article class="content-card"><span class="badge">${state.status.connections[key] ? "설정 있음 · 검증 필요" : "미연결"}</span><h3>${name}</h3><p>${desc}</p><p style="overflow-wrap:anywhere;font-size:11px">${env}</p></article>`,
    )
    .join("");
}
$("image-mode").onchange();
refresh().catch((e) => toast(e.message, true));
// Refresh production status without overwriting unsaved scheduling inputs.
setInterval(async () => {
  if (document.hidden || $("view-schedule").hidden) return;
  try {
    const latest = await api("/api/status");
    $("autopilot-status").textContent = (latest.autopilot?.message || "아직 자동 제작 전입니다.") + sourcePolicyLabel(latest);
    renderOperations(latest);
  } catch (_) { $("autopilot-status").textContent = "프로그램 연결을 확인하세요. 제작 상태를 확인하지 못했습니다."; }
}, 15000);

function sourcePolicyLabel(status) {
  const p = status.source_policy;
  return p ? ` · 서버 소재 기준: 업로드 ${p.max_age_hours}시간 이내 / ${p.min_views.toLocaleString()}회 이상 / 게시 직전 재확인` : "";
}

function renderOperations(status) {
  const op = status.operations;
  if (!op) return;
  $("operations-status").textContent = op.summary;
  const r = op.rules;
  $("operations-rules").textContent = `서버 운영 기준 ${op.version} · 자동/수동 공통 게시 검사 · 사진·최종 로고·공개 이미지 확인 · 최소 ${r.min_post_interval_minutes}분 간격 · 소재 ${r.source_attempt_limit}회 / 생성 ${r.generation_attempt_limit}회 / 영상당 ${r.video_attempt_limit}회 · 오늘 전체 게시 ${op.today_published}건 중 실제 조회 확인 ${op.today_live_verified}건`;
}
