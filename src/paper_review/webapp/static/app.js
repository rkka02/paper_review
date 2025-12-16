/* eslint-disable no-console */
const $ = (id) => document.getElementById(id);

const loginSection = $("loginSection");
const appSection = $("appSection");
const logoutBtn = $("logoutBtn");

const usernameInput = $("username");
const passwordInput = $("password");
const loginBtn = $("loginBtn");
const loginError = $("loginError");

const pdfFileInput = $("pdfFile");
const driveFileIdInput = $("driveFileId");
const doiInput = $("doi");
const titleInput = $("title");
const createBtn = $("createBtn");
const createStatus = $("createStatus");

const refreshBtn = $("refreshBtn");
const papersList = $("papersList");

const analyzeBtn = $("analyzeBtn");
const stopPollBtn = $("stopPollBtn");
const detailMeta = $("detailMeta");
const detailError = $("detailError");
const mdView = $("mdView");
const jsonView = $("jsonView");

let selectedPaperId = null;
let pollHandle = null;
let authEnabled = false;

function show(el) {
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function setText(el, text) {
  el.textContent = text ?? "";
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...opts,
    headers: {
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    const msg = text || `${res.status} ${res.statusText}`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

function normalizeTitle(p) {
  const t = p.paper?.title || p.paper?.doi || p.paper?.drive_file_id || p.paper?.id;
  return t || "(untitled)";
}

function runBadgeText(run) {
  if (!run) return "run: -";
  return `run: ${run.status}`;
}

function renderPapers(items) {
  papersList.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No papers yet.";
    papersList.appendChild(empty);
    return;
  }

  for (const item of items) {
    const div = document.createElement("div");
    div.className = "list-item";
    if (item.paper.id === selectedPaperId) div.classList.add("active");

    const title = document.createElement("div");
    title.textContent = normalizeTitle(item);
    title.style.fontWeight = "700";

    const meta = document.createElement("div");
    meta.className = "muted";
    meta.style.fontSize = "12px";
    meta.textContent = `${item.paper.id}  •  doi: ${item.paper.doi || "-"}  •  status: ${item.paper.status}`;

    const badge = document.createElement("div");
    badge.className = "badge";
    badge.textContent = runBadgeText(item.latest_run);

    div.appendChild(title);
    div.appendChild(meta);
    div.appendChild(badge);

    div.addEventListener("click", async () => {
      selectedPaperId = item.paper.id;
      await refreshPapers();
      await loadDetails(selectedPaperId);
    });

    papersList.appendChild(div);
  }
}

function stopPolling() {
  if (pollHandle) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
  hide(stopPollBtn);
}

async function refreshSession() {
  const s = await api("/api/session");
  authEnabled = !!s.auth_enabled;

  if (!authEnabled) {
    hide(loginSection);
    show(appSection);
    hide(logoutBtn);
    return;
  }

  if (!s.authenticated) {
    show(loginSection);
    hide(appSection);
    hide(logoutBtn);
    return;
  }

  hide(loginSection);
  show(appSection);
  show(logoutBtn);
}

async function login() {
  setText(loginError, "");
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    setText(loginError, "username/password를 입력해줘.");
    return;
  }
  try {
    await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    passwordInput.value = "";
    await refreshSession();
    await refreshPapers();
  } catch (e) {
    setText(loginError, String(e.message || e));
  }
}

async function logout() {
  stopPolling();
  await api("/api/session", { method: "DELETE" });
  selectedPaperId = null;
  await refreshSession();
}

async function refreshPapers() {
  const items = await api("/api/papers/summary");
  renderPapers(items);
}

async function loadDetails(paperId) {
  stopPolling();
  setText(detailError, "");
  setText(mdView, "");
  setText(jsonView, "");
  analyzeBtn.disabled = !paperId;

  if (!paperId) {
    setText(detailMeta, "");
    return;
  }

  const d = await api(`/api/papers/${paperId}`);
  const run = d.latest_run;
  const runStatus = run?.status || "-";
  const err = run?.error || "";
  setText(detailMeta, `paper_id=${paperId}  •  run=${runStatus}`);
  setText(detailError, err);
  setText(mdView, d.latest_content_md || "");
  setText(jsonView, d.latest_output ? JSON.stringify(d.latest_output, null, 2) : "");
}

async function startPolling(paperId) {
  stopPolling();
  show(stopPollBtn);
  pollHandle = setInterval(async () => {
    try {
      const d = await api(`/api/papers/${paperId}`);
      const run = d.latest_run;
      const runStatus = run?.status || "-";
      setText(detailMeta, `paper_id=${paperId}  •  run=${runStatus}`);
      setText(detailError, run?.error || "");
      setText(mdView, d.latest_content_md || "");
      setText(jsonView, d.latest_output ? JSON.stringify(d.latest_output, null, 2) : "");
      if (runStatus !== "queued" && runStatus !== "running") stopPolling();
      await refreshPapers();
    } catch (e) {
      console.warn("poll failed:", e);
    }
  }, 3000);
}

async function enqueueAnalyze() {
  if (!selectedPaperId) return;
  setText(detailError, "");
  await api(`/api/papers/${selectedPaperId}/analyze`, { method: "POST" });
  await loadDetails(selectedPaperId);
  await startPolling(selectedPaperId);
}

async function createPaper() {
  createBtn.disabled = true;
  setText(createStatus, "Working...");
  try {
    const doi = doiInput.value.trim() || null;
    const title = titleInput.value.trim() || null;
    const driveFileId = driveFileIdInput.value.trim() || null;
    const file = pdfFileInput.files && pdfFileInput.files[0] ? pdfFileInput.files[0] : null;

    let paper = null;
    if (file) {
      paper = await api(
        `/api/papers/upload?${new URLSearchParams({ doi: doi || "", title: title || "" }).toString()}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/pdf" },
          body: file,
        },
      );
    } else {
      paper = await api("/api/papers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ drive_file_id: driveFileId, doi, title }),
      });
    }

    selectedPaperId = paper.id;
    pdfFileInput.value = "";
    driveFileIdInput.value = "";
    doiInput.value = "";
    titleInput.value = "";
    setText(createStatus, "OK");
    await refreshPapers();
    await loadDetails(selectedPaperId);
  } catch (e) {
    setText(createStatus, `Error: ${String(e.message || e)}`);
  } finally {
    createBtn.disabled = false;
    setTimeout(() => setText(createStatus, ""), 3000);
  }
}

function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  for (const t of tabs) {
    t.addEventListener("click", () => {
      for (const x of tabs) x.classList.remove("active");
      t.classList.add("active");
      const tab = t.getAttribute("data-tab");
      if (tab === "json") {
        hide(mdView);
        show(jsonView);
      } else {
        show(mdView);
        hide(jsonView);
      }
    });
  }
}

async function main() {
  initTabs();
  loginBtn.addEventListener("click", login);
  usernameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") login();
  });
  passwordInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") login();
  });
  logoutBtn.addEventListener("click", logout);

  createBtn.addEventListener("click", createPaper);
  refreshBtn.addEventListener("click", async () => {
    await refreshPapers();
    if (selectedPaperId) await loadDetails(selectedPaperId);
  });
  analyzeBtn.addEventListener("click", enqueueAnalyze);
  stopPollBtn.addEventListener("click", stopPolling);

  await refreshSession();
  if (!authEnabled || !loginSection.classList.contains("hidden")) return;
  await refreshPapers();
}

main().catch((e) => {
  console.error(e);
});

