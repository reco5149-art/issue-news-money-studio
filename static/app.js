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
  $("nav-count").textContent = state.posts.length;
  const today = state.status.time.slice(0, 10);
  const count = state.posts.filter(
    (p) => p.created_at.slice(0, 10) === today,
  ).length;
  $("daily-count").textContent = count;
  $("daily-bar").style.width = Math.min(100, count * 10) + "%";
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
  $("source-text").value = demo;
  $("source-text").oninput();
  $("source-name").value = "시연용 자체 작성 원고";
  $("source-url").value = "";
  $("category").value = "AI";
  $("count").value = "5";
  toast("시연용 원고를 넣었습니다. 카드뉴스 생성하기를 눌러보세요.");
};
async function importSource(url) {
  const data = await api("/api/import", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  $("source-text").value = data.text;
  $("source-text").oninput();
  $("source-name").value = data.source_name;
  $("source-url").value = data.source_url;
  toast(data.warning || "원문을 가져왔습니다.");
}
$("import-btn").onclick = () =>
  busy($("import-btn"), () => importSource($("source-link").value));
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
    const text = $("source-text").value.trim();
    if (text.length < 5) throw Error("주제나 원고를 5자 이상 입력하세요.");
    let videoAssets = [];
    let imageMode = $("image-mode").value;
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
  const scale = Math.min(1, 1280 / v.videoWidth);
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
      '<label for="video-file">영상 파일 (선택 · 유튜브 링크는 생략 가능)</label><input id="video-file" type="file" accept="video/*"><video id="local-video" controls hidden></video><p class="hint">카드뉴스 생성하기를 누르면 영상 구간별 장면을 자동 캡처해 카드마다 배치합니다. 파일이 없으면 위 출처 URL의 공개 유튜브 영상을 사용합니다. 20분·150MB 이하. AI가 홍보 화면을 제외하고 로고·방송 자막을 크롭합니다. 정리 API 비용이 발생하며 핵심 장면이 잘렸는지 확인하세요.</p>';
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
      '<label for="image-query">이미지 검색어 · 영문 검색 권장</label><div class="input-row"><input id="image-query" placeholder="artificial intelligence"><button id="search-images" class="secondary">검색</button></div><div id="image-results" class="image-results"></div>';
    $("search-images").onclick = () =>
      busy($("search-images"), async () => {
        const list = await api(
          "/api/images/search?q=" + encodeURIComponent($("image-query").value),
        );
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
    box.innerHTML =
      '<p class="notice">API 사용료가 발생합니다. 문안을 만든 뒤 각 카드의 제목·본문에 맞는 설명용 이미지를 1장씩 생성합니다. 카드 5장이면 이미지 5장 비용과 대기 시간이 발생합니다. 실제 보도사진이 아닙니다.</p>';
};
function renderLibrary() {
  const filter = $("library-filter").value;
  const items = state.posts.filter(
    (p) => filter === "all" || p.status === filter,
  );
  $("library-grid").innerHTML = items.length
    ? items
        .map(
          (p) =>
            `<article class="content-card"><img loading="lazy" src="${esc(p.images[0])}" alt="${esc(p.slides[0].title)}"><p><span class="badge">${labels[p.status]}</span>${esc(p.category)} · ${p.ratio} · ${p.slides.length}장</p><h3>${esc(p.slides[0].title)}</h3><div class="input-row"><button class="secondary" data-open="${p.id}">검토 · 예약</button><a class="primary" href="/api/posts/${p.id}/download">다운로드</a></div>${p.error ? `<p>${esc(p.error)}</p>` : ""}</article>`,
        )
        .join("")
    : '<div class="empty">아직 만든 카드뉴스가 없습니다.<br>예시 원고로 첫 콘텐츠를 만들어보세요.</div>';
  document.querySelectorAll("[data-open]").forEach(
    (b) =>
      (b.onclick = () => {
        state.current = state.posts.find((p) => p.id === b.dataset.open);
        openEditor();
      }),
  );
}
$("library-filter").onchange = renderLibrary;
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
$("save-edit").onclick = () =>
  busy($("save-edit"), async () => {
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
    await refresh();
    editorDirty = false;
    renderQuality(state.current);
    $("evaluate-post").disabled = false;
    toast("편집 내용과 확인 결과를 저장했습니다. 평가 상태를 확인하세요.");
  });
function renderQuality(p) {
  const q = p.quality || {};
  const labels = {passed:"통과",blocked:"게시 보류",stale:"수정 후 재평가 필요",error:"평가 실패"};
  $("quality-result").innerHTML = `<p><b>${esc(labels[q.status] || "평가 필요")}</b> ${esc(q.message || "")}</p>` + (q.cards || []).map(c => `<p><b>${c.card}번 · ${c.hook+c.sync+c.grounding+c.cta}/100점${c.critical ? " · 중대 오류" : ""}</b><br>후킹 ${c.hook}/25 · 사진 일치 ${c.sync}/40 · 원고 근거 ${c.grounding}/25 · CTA ${c.cta}/10<br>${esc(c.reason)}<br>수정 제안: ${esc(c.fix)}</p>`).join("");
  $("schedule-post").disabled = !["draft","failed"].includes(p.status) || q.status !== "passed" || editorDirty;
}
$("editor").addEventListener("input", e => {
  if (e.target.id !== "schedule-at") {
    editorDirty = true;
    $("schedule-post").disabled = true;
    $("evaluate-post").disabled = true;
    $("quality-result").textContent = "변경 내용을 저장한 후 평가 상태를 확인하세요.";
  }
});
$("evaluate-post").onclick = () => busy($("evaluate-post"), async () => {
  if (editorDirty) throw Error("변경 내용을 먼저 저장하세요.");
  state.current.quality = {status:"error", message:"평가 중입니다. 실패하면 다시 시도하세요."};
  renderQuality(state.current);
  state.current = await api(`/api/posts/${state.current.id}/evaluate`, {method:"POST"});
  renderQuality(state.current); showPreview(); await refresh();
  toast(state.current.quality.status === "passed" ? "평가를 통과했습니다. 사실·권한 확인 후 예약하세요." : "게시를 보류했습니다. 수정 제안을 확인하세요.");
});
$("schedule-post").onclick = () =>
  busy($("schedule-post"), async () => {
    if (!$("schedule-at").value)
      throw Error("게시할 날짜와 시간을 선택하세요.");
    await api(`/api/posts/${state.current.id}/schedule`, {
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
        daily_target: 10,
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
      "AI 문안 · 이미지",
      "OPENAI_API_KEY",
      "원고 요약, 후킹 문구, 주제 설명용 이미지 생성",
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
refresh().catch((e) => toast(e.message, true));
