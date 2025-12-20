/* eslint-disable no-console */
const $ = (id) => document.getElementById(id);

const loginSection = $("loginSection");
const appSection = $("appSection");
const logoutBtn = $("logoutBtn");
const themeToggle = $("themeToggle");
const toastHost = $("toastHost");

const usernameInput = $("username");
const passwordInput = $("password");
const loginBtn = $("loginBtn");
const loginError = $("loginError");

const pdfFileInput = $("pdfFile");
const driveFileIdInput = $("driveFileId");
const doiInput = $("doi");
const titleInput = $("title");
const analysisJsonFileInput = $("analysisJsonFile");
const analysisJsonText = $("analysisJsonText");
const analysisJsonClearBtn = $("analysisJsonClearBtn");
const createBtn = $("createBtn");
const createStatus = $("createStatus");

const refreshBtn = $("refreshBtn");
const newFolderBtn = $("newFolderBtn");
const newPaperBtn = $("newPaperBtn");
const paperSearch = $("paperSearch");
const paperStatusAll = $("paperStatusAll");
const paperStatusUnread = $("paperStatusUnread");
const paperStatusRead = $("paperStatusRead");
const paperCount = $("paperCount");
const paperPrevBtn = $("paperPrevBtn");
const paperNextBtn = $("paperNextBtn");
const paperPageInfo = $("paperPageInfo");
const foldersList = $("foldersList");
const papersList = $("papersList");

const analyzeBtn = $("analyzeBtn");
const stopPollBtn = $("stopPollBtn");
const detailTitle = $("detailTitle");
const detailMeta = $("detailMeta");
const paperControls = $("paperControls");
const detailError = $("detailError");
const overviewView = $("overviewView");
const personasView = $("personasView");
const personaTabs = $("personaTabs");
const personaContent = $("personaContent");
const normalizedView = $("normalizedView");
const normalizedTabs = $("normalizedTabs");
const normalizedContent = $("normalizedContent");
const diagnosticsView = $("diagnosticsView");
const mdView = $("mdView");
const jsonPanel = $("jsonPanel");
const jsonEditor = $("jsonEditor");
const jsonCopyBtn = $("jsonCopyBtn");
const jsonLangOriginal = $("jsonLangOriginal");
const jsonLangKorean = $("jsonLangKorean");
const jsonSaveBtn = $("jsonSaveBtn");
const jsonLogsPanel = $("jsonLogsPanel");
const jsonLogs = $("jsonLogs");
const detailTabsMoreBtn = $("detailTabsMoreBtn");
const newPaperDrawer = $("newPaperDrawer");
const newPaperDrawerPanel = $("newPaperDrawerPanel");
const newPaperCloseBtn = $("newPaperCloseBtn");

const graphBtn = $("graphBtn");
const graphOverlay = $("graphOverlay");
const graphCanvas = $("graphCanvas");
const graphCloseBtn = $("graphCloseBtn");
const graphSearch = $("graphSearch");
const graphStatus = $("graphStatus");

const recsBtn = $("recsBtn");
const recsBadge = $("recsBadge");
const recsOverlay = $("recsOverlay");
const recsCloseBtn = $("recsCloseBtn");
const recsRunBtn = $("recsRunBtn");
const recsLogsBtn = $("recsLogsBtn");
const recsRefreshBtn = $("recsRefreshBtn");
const recsTaskMeta = $("recsTaskMeta");
const recsLogsPanel = $("recsLogsPanel");
const recsLogs = $("recsLogs");
const recsMeta = $("recsMeta");
const recsContent = $("recsContent");
const recsLangOriginal = $("recsLangOriginal");
const recsLangKorean = $("recsLangKorean");
const recsTranslateBtn = $("recsTranslateBtn");
const recsTranslateLogsPanel = $("recsTranslateLogsPanel");
const recsTranslateLogs = $("recsTranslateLogs");

let selectedPaperId = null;
let pollHandle = null;
let authEnabled = false;
let paperSummaries = [];
let paperById = new Map();
const PAPER_PAGE_SIZE = 5;
let paperPageIndex = 0;
let lastPaperFilterKey = null;
let lastPagerSelectedPaperId = null;
let paperFilteredCache = [];
let folders = [];
let folderById = new Map();
let selectedFolderMode = "all"; // all | unfiled | folder
let selectedFolderId = null;
let selectedPaperStatusFilter = "all"; // all | unread | read
let selectedDetailTab = "overview";
let selectedPersonaId = null;
let selectedNormalizedTab = "section_map";
let selectedJsonLang = "original";
let selectedRecsLang = "original";
let lastDetailOutputKey = null;
let currentDetail = null;
let jsonDraftPaperId = null;
let jsonDraftByLang = { original: "", ko: "" };
let jsonDirtyByLang = { original: false, ko: false };
let overviewCtx = null;
let paperMenuEl = null;
let paperMenuToken = null;
let graphState = null;
let latestRecs = null;
let latestRecsTask = null;
let recsTaskPollHandle = null;
let recsLogsVisible = false;
let newPaperDrawerHideTimer = null;

function show(el) {
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function setText(el, text) {
  el.textContent = text ?? "";
}

const DRAWER_ANIM_MS = 220;

function isNewPaperDrawerOpen() {
  return newPaperDrawer && !newPaperDrawer.classList.contains("hidden");
}

function openNewPaperDrawer() {
  if (!newPaperDrawer) return;
  if (newPaperDrawerHideTimer) {
    window.clearTimeout(newPaperDrawerHideTimer);
    newPaperDrawerHideTimer = null;
  }
  show(newPaperDrawer);
  document.body.classList.add("drawer-open");
  newPaperDrawer.classList.remove("open");
  requestAnimationFrame(() => newPaperDrawer.classList.add("open"));
  window.addEventListener("keydown", onNewPaperDrawerKeydown, true);
  window.setTimeout(() => {
    if (analysisJsonFileInput) analysisJsonFileInput.focus();
  }, 0);
}

function closeNewPaperDrawer() {
  if (!newPaperDrawer) return;
  if (!isNewPaperDrawerOpen()) return;
  newPaperDrawer.classList.remove("open");
  window.removeEventListener("keydown", onNewPaperDrawerKeydown, true);
  document.body.classList.remove("drawer-open");
  if (newPaperDrawerHideTimer) window.clearTimeout(newPaperDrawerHideTimer);
  newPaperDrawerHideTimer = window.setTimeout(() => {
    hide(newPaperDrawer);
    newPaperDrawerHideTimer = null;
  }, DRAWER_ANIM_MS);
}

function onNewPaperDrawerKeydown(e) {
  if (e.key === "Escape") {
    e.preventDefault();
    closeNewPaperDrawer();
  }
}

async function copyToClipboard(text) {
  const value = String(text || "");
  if (!value) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = value;
  ta.setAttribute("readonly", "true");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
}

function setLogPanel(panel, pre, logs) {
  if (!panel || !pre) return;
  const text = Array.isArray(logs) ? logs.join("\n").trim() : String(logs || "").trim();
  if (!text) {
    pre.textContent = "";
    hide(panel);
    panel.setAttribute("aria-hidden", "true");
    return;
  }
  pre.textContent = text;
  show(panel);
  panel.setAttribute("aria-hidden", "false");
}

function getDetailOutputState(detail) {
  const original = detail?.latest_output || null;
  const translated = detail?.latest_output_ko || null;
  const useKo = selectedJsonLang === "ko";
  const selected = useKo ? translated : original;
  const missing = useKo && !translated && !!original;
  const key = selected ? JSON.stringify(selected) : "";
  return { original, translated, selected, missing, key };
}

function currentJsonLangKey() {
  return selectedJsonLang === "ko" ? "ko" : "original";
}

function resetJsonDrafts(paperId) {
  jsonDraftPaperId = paperId;
  jsonDraftByLang = { original: "", ko: "" };
  jsonDirtyByLang = { original: false, ko: false };
}

function syncJsonEditor(detail) {
  if (!jsonEditor) return;
  const langKey = currentJsonLangKey();

  let desired = "";
  if (jsonDirtyByLang?.[langKey]) {
    desired = String(jsonDraftByLang?.[langKey] || "");
  } else if (detail) {
    const obj = langKey === "ko" ? detail.latest_output_ko : detail.latest_output;
    desired = obj ? JSON.stringify(obj, null, 2) : "";
    jsonDraftByLang[langKey] = desired;
  }

  if (jsonEditor.value !== desired) jsonEditor.value = desired;
}

function renderMarkdownFromCanonical(canonical) {
  if (!canonical || typeof canonical !== "object") return "";
  const paper = canonical.paper || {};
  const meta = paper && typeof paper === "object" ? paper.metadata || {} : {};
  const title = meta.title || "(untitled)";
  const doi = meta.doi || "";
  const year = meta.year || "";
  const venue = meta.venue || "";

  const final = canonical.final_synthesis || {};
  const oneLiner = final.one_liner || "";
  const strengths = asArray(final.strengths);
  const weaknesses = asArray(final.weaknesses);

  const lines = [];
  lines.push(`# ${title}`);
  if (doi || year || venue) {
    const bits = [];
    if (year) bits.push(String(year));
    if (venue) bits.push(String(venue));
    if (doi) bits.push(String(doi));
    lines.push("");
    lines.push(bits.join(" / "));
  }

  if (oneLiner) {
    lines.push("");
    lines.push(`**One-liner:** ${oneLiner}`);
  }

  if (strengths.length) {
    lines.push("");
    lines.push("## Strengths");
    for (const s of strengths) lines.push(`- ${s}`);
  }

  if (weaknesses.length) {
    lines.push("");
    lines.push("## Weaknesses");
    for (const w of weaknesses) lines.push(`- ${w}`);
  }

  const personas = asArray(canonical.personas);
  if (personas.length) {
    lines.push("");
    lines.push("## Personas");
    for (const p of personas) {
      const titleP = p?.title || p?.id || "persona";
      lines.push(`### ${titleP}`);
      for (const h of asArray(p?.highlights)) {
        const point = h?.point;
        if (point) lines.push(`- ${point}`);
      }
    }
  }

  return `${lines.join("\n").trim()}\n`;
}

function renderMarkdownView(detail, state) {
  if (!mdView) return;
  if (!detail) {
    setText(mdView, "");
    return;
  }
  if (selectedJsonLang === "ko") {
    if (state.selected) {
      setText(mdView, renderMarkdownFromCanonical(state.selected));
    } else if (state.missing) {
      setText(mdView, "한국어 없음");
    } else {
      setText(mdView, "");
    }
    return;
  }
  setText(mdView, detail.latest_content_md || "");
}

function renderDetailOutput(detail) {
  if (!detail) {
    if (jsonEditor) jsonEditor.value = "";
    renderMarkdownView(null, { selected: null, missing: false });
    return;
  }
  const state = getDetailOutputState(detail);
  renderOverview(detail, state.selected, state.key, state.missing);
  if (state.key !== lastDetailOutputKey) {
    lastDetailOutputKey = state.key;
    renderPersonas(state.selected, state.missing);
    renderNormalized(state.selected, state.missing);
    renderDiagnostics(state.selected, state.missing);
  }
  renderMarkdownView(detail, state);
  syncJsonEditor(detail);
}

function setJsonLang(lang) {
  const prevKey = currentJsonLangKey();
  if (jsonEditor) jsonDraftByLang[prevKey] = jsonEditor.value;
  selectedJsonLang = lang === "ko" ? "ko" : "original";
  if (jsonLangOriginal) jsonLangOriginal.classList.toggle("active", selectedJsonLang === "original");
  if (jsonLangKorean) jsonLangKorean.classList.toggle("active", selectedJsonLang === "ko");
  renderDetailOutput(currentDetail);
}

function setRecsLang(lang) {
  selectedRecsLang = lang === "ko" ? "ko" : "original";
  if (recsLangOriginal) recsLangOriginal.classList.toggle("active", selectedRecsLang === "original");
  if (recsLangKorean) recsLangKorean.classList.toggle("active", selectedRecsLang === "ko");
  if (isRecsOpen()) renderRecs(latestRecs);
}

function isJsonDirty() {
  const key = currentJsonLangKey();
  return !!jsonDirtyByLang?.[key];
}

function folderName(folderId) {
  if (!folderId) return null;
  const f = folderById.get(folderId);
  return f && typeof f.name === "string" ? f.name : null;
}

function currentFolderForNewPaper() {
  if (selectedFolderMode === "folder" && selectedFolderId) return selectedFolderId;
  return null;
}

function setFolderSelection(mode, folderId = null) {
  selectedFolderMode = mode;
  selectedFolderId = folderId;
  renderFolders();
  applyPapersFilter();
}

function setPaperStatusFilter(mode) {
  selectedPaperStatusFilter = mode === "read" ? "read" : mode === "unread" ? "unread" : "all";
  if (paperStatusAll) paperStatusAll.classList.toggle("active", selectedPaperStatusFilter === "all");
  if (paperStatusUnread) paperStatusUnread.classList.toggle("active", selectedPaperStatusFilter === "unread");
  if (paperStatusRead) paperStatusRead.classList.toggle("active", selectedPaperStatusFilter === "read");
  applyPapersFilter();
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function setTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  if (next === "dark") document.documentElement.setAttribute("data-theme", "dark");
  else document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.setItem("theme", next);
  } catch {
    // ignore
  }
  if (themeToggle) themeToggle.textContent = next === "dark" ? "Light" : "Dark";
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem("theme");
  } catch {
    saved = null;
  }
  setTheme(saved === "dark" ? "dark" : "light");
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
    const ct = res.headers.get("content-type") || "";
    let msg = "";
    if (ct.includes("application/json")) {
      try {
        const j = await res.json();
        if (j && typeof j.detail === "string") msg = j.detail;
        else if (j && j.detail !== undefined) msg = JSON.stringify(j.detail);
        else msg = JSON.stringify(j);
      } catch {
        msg = "";
      }
    }
    if (!msg) {
      const text = await res.text().catch(() => "");
      msg = text || `${res.status} ${res.statusText}`;
    }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

function parseJsonLoose(rawText) {
  const raw = String(rawText || "").trim();
  if (!raw) throw new Error("Empty JSON.");

  const tryParse = (text) => JSON.parse(text);

  try {
    return tryParse(raw);
  } catch {
    // continue
  }

  let text = raw;
  if (text.startsWith("```")) {
    const lines = text.split(/\r?\n/);
    if (lines.length >= 1 && lines[0].trim().startsWith("```")) lines.shift();
    if (lines.length >= 1 && lines[lines.length - 1].trim().startsWith("```")) lines.pop();
    text = lines.join("\n").trim();
  }

  try {
    return tryParse(text);
  } catch {
    // continue
  }

  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    const sliced = text.slice(firstBrace, lastBrace + 1).trim();
    return tryParse(sliced);
  }

  return tryParse(text);
}

function normalizeTitle(p) {
  const t = p.paper?.title || p.paper?.doi || p.paper?.drive_file_id || p.paper?.id;
  return t || "(untitled)";
}

function paperLabel(paper) {
  if (!paper) return "(untitled)";
  return paper.title || paper.doi || paper.drive_file_id || paper.id || "(untitled)";
}

function paperReadLabel(status) {
  return status === "done" ? "읽음" : "아직 안 읽음";
}

function paperMetaLine(paper) {
  if (!paper) return "";
  const parts = [];
  if (paper.doi) parts.push(`doi: ${paper.doi}`);
  const fn = folderName(paper.folder_id);
  parts.push(fn ? `folder: ${fn}` : "unfiled");
  return parts.join(" | ");
}

function runBadgeText(run) {
  if (!run) return "run: -";
  return `run: ${run.status}`;
}

function runBadgeClass(run) {
  const status = run?.status || "";
  if (status === "succeeded") return "badge-ok";
  if (status === "failed") return "badge-bad";
  if (status === "queued" || status === "running") return "badge-warn";
  return "";
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function createEl(tag, opts = {}) {
  const node = document.createElement(tag);
  if (opts.className) node.className = opts.className;
  if (opts.text !== undefined && opts.text !== null) node.textContent = opts.text;
  if (opts.attrs) {
    for (const [k, v] of Object.entries(opts.attrs)) {
      if (v === undefined || v === null) continue;
      node.setAttribute(k, String(v));
    }
  }
  return node;
}

function toast(message, type = "info", timeoutMs = 3500) {
  const msg = String(message || "").trim();
  if (!msg) return;
  if (!toastHost) {
    if (type === "error") alert(msg);
    else console.log(msg);
    return;
  }

  const el = createEl("div", { className: `toast toast-${type}`, text: msg });
  toastHost.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  window.setTimeout(() => {
    el.classList.remove("show");
    window.setTimeout(() => el.remove(), 220);
  }, timeoutMs);
}

function ensurePaperMenu() {
  if (paperMenuEl) return paperMenuEl;
  paperMenuEl = createEl("div", { className: "menu hidden", attrs: { id: "paperMenu" } });
  document.body.appendChild(paperMenuEl);
  return paperMenuEl;
}

function closePaperMenu() {
  if (!paperMenuEl) return;
  paperMenuEl.classList.add("hidden");
  paperMenuEl.style.visibility = "";
  paperMenuEl.style.left = "";
  paperMenuEl.style.top = "";
  paperMenuEl.replaceChildren();
  paperMenuToken = null;
  document.removeEventListener("click", onPaperMenuOutsideClick, true);
  window.removeEventListener("resize", closePaperMenu);
  window.removeEventListener("scroll", closePaperMenu, true);
}

function onPaperMenuOutsideClick(e) {
  if (!paperMenuEl || paperMenuEl.classList.contains("hidden")) return;
  const t = e.target;
  if (t && paperMenuEl.contains(t)) return;
  closePaperMenu();
}

function openMenu(anchorEl, token, items) {
  const menu = ensurePaperMenu();
  menu.replaceChildren();
  menu.style.left = "0px";
  menu.style.top = "0px";
  menu.style.visibility = "hidden";
  menu.classList.remove("hidden");

  const addItem = (label, onClick, cls = "") => {
    const btn = createEl("button", {
      className: ["menu-item", cls].filter(Boolean).join(" "),
      text: label,
      attrs: { type: "button" },
    });
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      closePaperMenu();
      await onClick();
    });
    menu.appendChild(btn);
  };

  for (const it of items || []) {
    if (!it) continue;
    if (it.type === "sep") {
      menu.appendChild(createEl("div", { className: "menu-sep" }));
      continue;
    }
    addItem(it.label, it.onClick, it.danger ? "menu-item-danger" : "");
  }

  const rect = anchorEl.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const margin = 8;

  let left = rect.right - menuRect.width;
  let top = rect.bottom + 6;

  if (left < margin) left = margin;
  if (left + menuRect.width > window.innerWidth - margin) {
    left = window.innerWidth - margin - menuRect.width;
  }

  if (top + menuRect.height > window.innerHeight - margin) {
    top = rect.top - menuRect.height - 6;
  }
  if (top < margin) top = margin;

  menu.style.left = `${Math.round(left)}px`;
  menu.style.top = `${Math.round(top)}px`;
  menu.style.visibility = "visible";

  paperMenuToken = token;
  document.addEventListener("click", onPaperMenuOutsideClick, true);
  window.addEventListener("resize", closePaperMenu);
  window.addEventListener("scroll", closePaperMenu, true);
}

function toggleMenu(anchorEl, token, items) {
  if (paperMenuToken === token && paperMenuEl && !paperMenuEl.classList.contains("hidden")) {
    closePaperMenu();
    return;
  }
  openMenu(anchorEl, token, items);
}

function togglePaperMenu(anchorEl, paper) {
  toggleMenu(anchorEl, `paper:${paper.id}`, [
    { label: "Move...", onClick: () => movePaperPrompt(paper) },
    { label: "Rename...", onClick: () => renamePaper(paper) },
    { type: "sep" },
    { label: "Delete...", danger: true, onClick: () => deletePaper(paper) },
  ]);
}

function toggleFolderMenu(anchorEl, folder) {
  toggleMenu(anchorEl, `folder:${folder.id}`, [
    { label: "Rename...", onClick: () => renameFolder(folder) },
    { type: "sep" },
    { label: "Delete...", danger: true, onClick: () => deleteFolder(folder) },
  ]);
}

function pill(text, variant) {
  const cls = ["pill"];
  if (variant) cls.push(`pill-${variant}`);
  return createEl("span", { className: cls.join(" "), text });
}

function fmtPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function safeLink(url, label = null) {
  const raw = (url || "").trim();
  if (!raw) return createEl("span", { className: "muted", text: "-" });
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return createEl("a", {
      className: "link",
      text: label || raw,
      attrs: { href: raw, target: "_blank", rel: "noreferrer" },
    });
  }
  return createEl("span", { text: raw });
}

function doiLink(doi) {
  const raw = (doi || "").trim();
  if (!raw) return createEl("span", { className: "muted", text: "-" });
  const url = raw.startsWith("http://") || raw.startsWith("https://") ? raw : `https://doi.org/${raw}`;
  return safeLink(url, raw);
}

function kvRow(label, value) {
  const row = createEl("div", { className: "kv-row" });
  row.appendChild(createEl("div", { className: "kv-key", text: label }));
  const v = createEl("div", { className: "kv-val" });
  if (value instanceof Node) v.appendChild(value);
  else v.textContent = value ?? "";
  row.appendChild(v);
  return row;
}

function renderEvidenceBlock(evidence) {
  const items = asArray(evidence).filter((x) => x && (x.quote || x.why || x.page));
  if (!items.length) return null;

  const details = createEl("details", { className: "evidence" });
  details.appendChild(createEl("summary", { text: `Evidence (${items.length})` }));

  const list = createEl("div", { className: "evidence-list" });
  for (const ev of items) {
    const item = createEl("div", { className: "evidence-item" });
    const head = createEl("div", { className: "row evidence-head" });
    head.appendChild(pill(`p.${ev.page ?? "?"}`, "page"));
    item.appendChild(head);

    if (ev.quote) item.appendChild(createEl("div", { className: "evidence-quote", text: ev.quote }));
    if (ev.why) item.appendChild(createEl("div", { className: "muted evidence-why", text: ev.why }));
    list.appendChild(item);
  }
  details.appendChild(list);
  return details;
}

function renderBullets(items) {
  const ul = createEl("ul", { className: "bullets" });
  for (const x of asArray(items)) {
    ul.appendChild(createEl("li", { text: String(x) }));
  }
  return ul;
}

function renderAuthors(authors) {
  const items = asArray(authors)
    .map((a) => {
      if (!a || typeof a !== "object") return null;
      const name = String(a.name || "").trim();
      const affiliation = String(a.affiliation || "").trim();
      if (!name) return null;
      return { name, affiliation: affiliation || null };
    })
    .filter(Boolean);

  if (!items.length) return createEl("span", { className: "muted", text: "-" });

  const wrap = createEl("div", { className: "author-list" });
  for (const it of items) {
    const line = createEl("div", { className: "author-line" });
    if (it.affiliation) {
      const btn = createEl("button", {
        className: "author-name author-name-btn",
        text: it.name,
        attrs: { type: "button", "aria-expanded": "false" },
      });
      const aff = createEl("div", { className: "author-aff hidden", text: it.affiliation });
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const next = aff.classList.contains("hidden");
        aff.classList.toggle("hidden", !next);
        btn.setAttribute("aria-expanded", next ? "true" : "false");
      });
      line.appendChild(btn);
      line.appendChild(aff);
    } else {
      line.appendChild(createEl("span", { className: "author-name", text: it.name }));
    }
    wrap.appendChild(line);
  }
  return wrap;
}

function switchDetailTab(tab) {
  selectedDetailTab = tab;
  const views = {
    overview: overviewView,
    personas: personasView,
    normalized: normalizedView,
    diagnostics: diagnosticsView,
    md: mdView,
    json: jsonPanel || jsonEditor,
  };
  for (const [k, el] of Object.entries(views)) {
    if (!el) continue;
    if (k === tab) show(el);
    else hide(el);
  }
  const tabs = document.querySelectorAll("#detailTabs .tab");
  for (const t of tabs) t.classList.toggle("active", t.getAttribute("data-tab") === tab);
  if (detailTabsMoreBtn) {
    detailTabsMoreBtn.classList.toggle("active", ["diagnostics", "md", "json"].includes(tab));
  }

  const showJsonActions = tab === "json";
  if (jsonSaveBtn) jsonSaveBtn.classList.toggle("hidden", !showJsonActions);
  if (jsonCopyBtn) jsonCopyBtn.classList.toggle("hidden", !showJsonActions);
}

function initDetailTabs() {
  const tabs = document.querySelectorAll("#detailTabs .tab");
  for (const t of tabs) {
    const key = t.getAttribute("data-tab");
    if (!key) continue;
    t.addEventListener("click", () => {
      switchDetailTab(key);
    });
  }

  if (detailTabsMoreBtn) {
    detailTabsMoreBtn.addEventListener("click", (e) => {
      e.preventDefault();
      const extras = [
        { key: "json", label: "JSON" },
        { key: "md", label: "Markdown" },
        { key: "diagnostics", label: "Diagnostics" },
      ];
      toggleMenu(
        detailTabsMoreBtn,
        "detailTabs:more",
        extras.map((it) => ({
          label: `${selectedDetailTab === it.key ? "✓ " : ""}${it.label}`,
          onClick: () => switchDetailTab(it.key),
        })),
      );
    });
  }
  switchDetailTab(selectedDetailTab);
}

function renderOverview(detail, canonicalOut, outputKey, missingTranslation = false) {
  if (!overviewView) return;

  const paperOut = detail?.paper;
  const paperId = paperOut?.id;
  if (!paperId) {
    overviewView.replaceChildren();
    overviewCtx = null;
    overviewView.appendChild(createEl("div", { className: "muted", text: "Select a paper." }));
    return;
  }

  const buildSkeleton = () => {
    overviewView.replaceChildren();

    const titleEl = createEl("div", { className: "overview-title" });
    const kvEl = createEl("div", { className: "kv" });

    const memoCard = createEl("div", { className: "memo-card" });
    const memoHeader = createEl("div", { className: "memo-header" });
    memoHeader.appendChild(createEl("div", { className: "memo-title", text: "My memo" }));
    const memoStatus = createEl("div", { className: "memo-status muted", text: "Enter to save" });
    memoHeader.appendChild(memoStatus);
    memoCard.appendChild(memoHeader);
    memoCard.appendChild(
      createEl("div", { className: "memo-hint muted", text: "Enter: save | Shift+Enter: newline" }),
    );
    const memoTextarea = createEl("textarea", {
      className: "textarea memo-textarea",
      attrs: { rows: "4", spellcheck: "false", placeholder: "Leave a quick personal note..." },
    });
    memoCard.appendChild(memoTextarea);

    const connectionsCard = createEl("div", { className: "connections-card" });
    const connectionsHeader = createEl("div", { className: "connections-header" });
    connectionsHeader.appendChild(createEl("div", { className: "connections-title", text: "Connections" }));
    const connCount = pill("0", "muted");
    connectionsHeader.appendChild(connCount);
    connectionsCard.appendChild(connectionsHeader);

    const linksList = createEl("div", { className: "link-chips" });
    connectionsCard.appendChild(linksList);

    const searchWrap = createEl("div", { className: "link-search-wrap" });
    const searchInput = createEl("input", {
      attrs: { type: "text", placeholder: "Search papers to connect..." },
    });
    const results = createEl("div", { className: "link-results hidden" });
    searchWrap.appendChild(searchInput);
    searchWrap.appendChild(results);
    connectionsCard.appendChild(searchWrap);

    const absHost = createEl("div", { className: "section", attrs: { id: "overviewAbstract" } });
    const finalHost = createEl("div", { className: "section", attrs: { id: "overviewFinal" } });

    overviewView.appendChild(titleEl);
    overviewView.appendChild(kvEl);
    overviewView.appendChild(memoCard);
    overviewView.appendChild(connectionsCard);
    overviewView.appendChild(absHost);
    overviewView.appendChild(finalHost);

    const setMemoStatus = (text, cls = "muted") => {
      memoStatus.className = `memo-status ${cls}`;
      memoStatus.textContent = text;
    };

    const hideResults = () => {
      results.classList.add("hidden");
      results.replaceChildren();
    };

    const saveMemo = async () => {
      if (!overviewCtx || overviewCtx.paperId !== paperId) return;
      const raw = overviewCtx.memoTextarea.value || "";
      setMemoStatus("Saving...", "muted");
      try {
        const updated = await api(`/api/papers/${paperId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ memo: raw }),
        });
        const next = updated.memo ? String(updated.memo) : "";
        overviewCtx.memoDirty = false;
        overviewCtx.memoLastServer = next;
        overviewCtx.memoTextarea.value = next;
        setMemoStatus("Saved", "muted");
        if (currentDetail && currentDetail.paper && currentDetail.paper.id === paperId) {
          currentDetail.paper.memo = updated.memo || null;
        }
      } catch (e) {
        setMemoStatus("Save failed", "error");
        toast(String(e.message || e), "error", 6500);
      }
    };

    const renderSearchResults = () => {
      const qRaw = (searchInput.value || "").trim();
      const q = qRaw.toLowerCase();
      if (!q) {
        hideResults();
        return;
      }

      const linked = new Set(asArray(currentDetail?.links).map((l) => String(l.id)));
      linked.add(String(paperId));

      const matches = [];
      for (const [id, p] of paperById.entries()) {
        if (!id || !p) continue;
        if (linked.has(String(id))) continue;
        const title = paperLabel(p);
        const folder = folderName(p.folder_id) || "";
        const hay = `${title} ${p.doi || ""} ${p.id || ""} ${folder} ${p.memo || ""}`.toLowerCase();
        if (!hay.includes(q)) continue;
        matches.push(p);
      }
      matches.sort((a, b) => paperLabel(a).localeCompare(paperLabel(b)));
      const top = matches.slice(0, 10);

      results.replaceChildren();
      if (!top.length) {
        results.appendChild(createEl("div", { className: "muted", text: "No matches." }));
        results.classList.remove("hidden");
        return;
      }

      for (const p of top) {
        const btn = createEl("button", {
          className: "link-result",
          attrs: { type: "button" },
        });
        btn.appendChild(createEl("div", { className: "link-result-title", text: paperLabel(p) }));
        btn.appendChild(createEl("div", { className: "link-result-meta muted", text: paperMetaLine(p) }));
        btn.addEventListener("click", async () => {
          const otherId = p.id;
          hideResults();
          searchInput.value = "";
          try {
            await api(`/api/papers/${paperId}/links`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ other_paper_id: otherId }),
            });
            toast("Linked.", "success");
            if (currentDetail && currentDetail.paper && currentDetail.paper.id === paperId) {
              if (!Array.isArray(currentDetail.links)) currentDetail.links = [];
              if (!currentDetail.links.some((x) => x && x.id === otherId)) {
                currentDetail.links.push({
                  id: otherId,
                  title: p.title || null,
                  doi: p.doi || null,
                  folder_id: p.folder_id || null,
                });
                currentDetail.links.sort((x, y) =>
                  (x.title || "").toLowerCase().localeCompare((y.title || "").toLowerCase()),
                );
              }
              const state = getDetailOutputState(currentDetail);
              renderOverview(currentDetail, state.selected, state.key, state.missing);
            }
          } catch (e) {
            toast(String(e.message || e), "error", 6500);
          }
        });
        results.appendChild(btn);
      }
      results.classList.remove("hidden");
    };

    memoTextarea.addEventListener("input", () => {
      if (!overviewCtx) return;
      overviewCtx.memoDirty = true;
      setMemoStatus("Unsaved", "muted");
    });
    memoTextarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        saveMemo();
      }
    });

    searchInput.addEventListener("input", renderSearchResults);
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        searchInput.value = "";
        hideResults();
      }
    });
    searchInput.addEventListener("blur", () => {
      window.setTimeout(() => {
        const active = document.activeElement;
        if (!active || !searchWrap.contains(active)) hideResults();
      }, 120);
    });

    overviewCtx = {
      paperId,
      outputKey: null,
      kvKey: null,
      titleEl,
      kvEl,
      absHost,
      finalHost,
      memoTextarea,
      memoStatus,
      memoDirty: false,
      memoLastServer: null,
      linksList,
      connCount,
      linksKey: null,
    };
  };

  if (!overviewCtx || overviewCtx.paperId !== paperId) buildSkeleton();
  if (!overviewCtx) return;

  const emptyMsg = missingTranslation ? "한국어 없음" : "No analysis output yet.";
  const missingKv = missingTranslation ? "한국어 없음" : "-";
  const canonicalPaper = canonicalOut?.paper || {};
  const canonicalMeta = canonicalPaper.metadata || {};
  const displayTitle =
    selectedJsonLang === "ko"
      ? canonicalMeta.title || paperOut.title || paperOut.doi || paperOut.drive_file_id || paperOut.id || "(untitled)"
      : paperOut.title || canonicalMeta.title || paperOut.doi || paperOut.drive_file_id || paperOut.id || "(untitled)";
  if (overviewCtx.titleEl.textContent !== displayTitle) overviewCtx.titleEl.textContent = displayTitle;

  const doiValue = canonicalMeta.doi || paperOut.doi || "";
  const urlValue = canonicalMeta.url || "";
  const kvKey = JSON.stringify({
    authors: canonicalMeta.authors || null,
    year: canonicalMeta.year || null,
    venue: canonicalMeta.venue || "",
    doi: doiValue,
    url: urlValue,
  });
  if (kvKey !== overviewCtx.kvKey) {
    overviewCtx.kvKey = kvKey;
    overviewCtx.kvEl.replaceChildren();
    overviewCtx.kvEl.appendChild(
      kvRow("Authors", canonicalOut ? renderAuthors(canonicalMeta.authors) : missingKv),
    );
    overviewCtx.kvEl.appendChild(
      kvRow("Year", canonicalOut && canonicalMeta.year ? String(canonicalMeta.year) : missingKv),
    );
    overviewCtx.kvEl.appendChild(kvRow("Venue", canonicalOut ? canonicalMeta.venue || "-" : missingKv));
    overviewCtx.kvEl.appendChild(kvRow("DOI", doiLink(doiValue)));
    overviewCtx.kvEl.appendChild(kvRow("URL", safeLink(urlValue)));
  }

  if (outputKey !== overviewCtx.outputKey) {
    overviewCtx.outputKey = outputKey;

    overviewCtx.absHost.replaceChildren();
    if (canonicalOut && canonicalPaper.abstract) {
      overviewCtx.absHost.appendChild(createEl("div", { className: "section-title", text: "Abstract" }));
      overviewCtx.absHost.appendChild(createEl("div", { className: "prose", text: canonicalPaper.abstract }));
    } else if (!canonicalOut) {
      overviewCtx.absHost.appendChild(createEl("div", { className: "muted", text: emptyMsg }));
    }

    overviewCtx.finalHost.replaceChildren();
    if (canonicalOut) {
      const final = canonicalOut.final_synthesis || {};
      overviewCtx.finalHost.appendChild(createEl("div", { className: "section-title", text: "Final synthesis" }));

      if (final.one_liner) overviewCtx.finalHost.appendChild(createEl("div", { className: "one-liner", text: final.one_liner }));

      const rating = final.suggested_rating || {};
      const ratingRow = createEl("div", { className: "row" });
      ratingRow.appendChild(pill(`Overall ${rating.overall ?? "-"}/5`, "primary"));
      ratingRow.appendChild(pill(`Confidence ${fmtPercent(rating.confidence)}`, "muted"));
      overviewCtx.finalHost.appendChild(ratingRow);

      const strengths = asArray(final.strengths);
      if (strengths.length) {
        overviewCtx.finalHost.appendChild(createEl("div", { className: "section-subtitle", text: "Strengths" }));
        overviewCtx.finalHost.appendChild(renderBullets(strengths));
      }

      const weaknesses = asArray(final.weaknesses);
      if (weaknesses.length) {
        overviewCtx.finalHost.appendChild(createEl("div", { className: "section-subtitle", text: "Weaknesses" }));
        overviewCtx.finalHost.appendChild(renderBullets(weaknesses));
      }

      const who = asArray(final.who_should_read);
      if (who.length) {
        overviewCtx.finalHost.appendChild(createEl("div", { className: "section-subtitle", text: "Who should read" }));
        overviewCtx.finalHost.appendChild(renderBullets(who));
      }

      const ev = renderEvidenceBlock(final.evidence);
      if (ev) overviewCtx.finalHost.appendChild(ev);
    } else if (!canonicalOut) {
      overviewCtx.finalHost.appendChild(createEl("div", { className: "muted", text: emptyMsg }));
    }
  }

  const memoServer = paperOut.memo ? String(paperOut.memo) : "";
  const shouldUpdateMemo =
    !overviewCtx.memoDirty &&
    document.activeElement !== overviewCtx.memoTextarea &&
    overviewCtx.memoLastServer !== memoServer;
  if (shouldUpdateMemo) {
    overviewCtx.memoTextarea.value = memoServer;
    overviewCtx.memoLastServer = memoServer;
  }

  const links = asArray(detail.links);
  const linksKey = JSON.stringify(links.map((l) => ({ id: String(l.id), title: l.title || "" })).sort((a, b) => a.id.localeCompare(b.id)));
  if (linksKey !== overviewCtx.linksKey) {
    overviewCtx.linksKey = linksKey;
    overviewCtx.linksList.replaceChildren();
    overviewCtx.connCount.textContent = String(links.length);

    if (!links.length) {
      overviewCtx.linksList.appendChild(createEl("div", { className: "muted", text: "No connections yet." }));
      return;
    }

    for (const l of links) {
      const chip = createEl("div", { className: "link-chip" });
      const title = l.title || l.doi || l.id || "(untitled)";
      chip.appendChild(createEl("div", { className: "link-chip-title", text: title }));

      const metaLine = [];
      if (l.doi) metaLine.push(`doi: ${l.doi}`);
      const fn = folderName(l.folder_id);
      if (fn) metaLine.push(`folder: ${fn}`);
      if (metaLine.length) chip.setAttribute("title", metaLine.join(" | "));

      const removeBtn = createEl("button", {
        className: "link-chip-remove",
        text: "x",
        attrs: { type: "button", "aria-label": "Remove connection" },
      });
      removeBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await api(`/api/papers/${paperId}/links/${l.id}`, { method: "DELETE" });
          toast("Unlinked.", "info");
          if (currentDetail && currentDetail.paper && currentDetail.paper.id === paperId && Array.isArray(currentDetail.links)) {
            currentDetail.links = currentDetail.links.filter((x) => x && x.id !== l.id);
          }
          const state = getDetailOutputState(currentDetail);
          renderOverview(currentDetail, state.selected, state.key, state.missing);
        } catch (e2) {
          toast(String(e2.message || e2), "error", 6500);
        }
      });
      chip.appendChild(removeBtn);

      chip.addEventListener("click", async () => {
        selectedPaperId = l.id;
        applyPapersFilter();
        await loadDetails(l.id);
      });
      overviewCtx.linksList.appendChild(chip);
    }
  }
}

function renderPersonas(canonical, missingTranslation = false) {
  personaTabs.replaceChildren();
  personaContent.replaceChildren();
  if (!canonical) {
    const msg = missingTranslation ? "한국어 없음" : "No analysis output yet.";
    personaContent.appendChild(createEl("div", { className: "muted", text: msg }));
    return;
  }

  const personas = asArray(canonical.personas);
  if (!personas.length) {
    personaContent.appendChild(createEl("div", { className: "muted", text: "No personas found." }));
    return;
  }

  if (!selectedPersonaId || !personas.some((p) => p && p.id === selectedPersonaId)) {
    selectedPersonaId = personas[0].id;
  }

  for (const p of personas) {
    const btn = createEl("button", {
      className: `tab ${p.id === selectedPersonaId ? "active" : ""}`,
      text: p.title || p.id,
      attrs: { type: "button" },
    });
    btn.addEventListener("click", () => {
      selectedPersonaId = p.id;
      renderPersonas(canonical, missingTranslation);
    });
    personaTabs.appendChild(btn);
  }

  const persona = personas.find((p) => p && p.id === selectedPersonaId) || personas[0];
  const header = createEl("div", { className: "section-title", text: persona.title || persona.id });
  personaContent.appendChild(header);

  const highlights = asArray(persona.highlights);
  const hl = createEl("div", { className: "section" });
  hl.appendChild(createEl("div", { className: "section-subtitle", text: `Highlights (${highlights.length})` }));
  if (!highlights.length) {
    hl.appendChild(createEl("div", { className: "muted", text: "No highlights." }));
  } else {
    for (const h of highlights) {
      const item = createEl("div", { className: "item" });
      const row = createEl("div", { className: "row" });
      const sev = (h && h.severity) || "low";
      row.appendChild(pill(sev.toUpperCase(), `sev-${sev}`));
      row.appendChild(createEl("div", { className: "item-text", text: h.point || "" }));
      item.appendChild(row);
      const ev = renderEvidenceBlock(h.evidence);
      if (ev) item.appendChild(ev);
      hl.appendChild(item);
    }
  }
  personaContent.appendChild(hl);
}

function renderNormalized(canonical, missingTranslation = false) {
  normalizedTabs.replaceChildren();
  normalizedContent.replaceChildren();
  if (!canonical) {
    const msg = missingTranslation ? "한국어 없음" : "No analysis output yet.";
    normalizedContent.appendChild(createEl("div", { className: "muted", text: msg }));
    return;
  }

  const normalized = canonical.normalized;
  if (!normalized) {
    normalizedContent.appendChild(createEl("div", { className: "muted", text: "No normalized output found." }));
    return;
  }

  const tabs = [
    { id: "section_map", label: "Section map" },
    { id: "contributions", label: "Contributions" },
    { id: "claims", label: "Claims" },
    { id: "limitations", label: "Limitations" },
    { id: "figures", label: "Figures" },
    { id: "tables", label: "Tables" },
    { id: "summaries", label: "Summaries" },
    { id: "reproducibility", label: "Reproducibility" },
  ];

  if (!tabs.some((t) => t.id === selectedNormalizedTab)) selectedNormalizedTab = tabs[0].id;

  for (const t of tabs) {
    const btn = createEl("button", {
      className: `tab ${t.id === selectedNormalizedTab ? "active" : ""}`,
      text: t.label,
      attrs: { type: "button" },
    });
    btn.addEventListener("click", () => {
      selectedNormalizedTab = t.id;
      renderNormalized(canonical, missingTranslation);
    });
    normalizedTabs.appendChild(btn);
  }

  if (selectedNormalizedTab === "section_map") {
    const items = asArray(normalized.section_map);
    if (!items.length) {
      normalizedContent.appendChild(createEl("div", { className: "muted", text: "No section map." }));
      return;
    }
    const wrap = createEl("div", { className: "table-wrap" });
    const table = createEl("table", { className: "table" });
    const thead = createEl("thead");
    const trh = createEl("tr");
    for (const h of ["Section", "Pages", "Summary"]) trh.appendChild(createEl("th", { text: h }));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = createEl("tbody");
    for (const s of items) {
      const tr = createEl("tr");
      tr.appendChild(createEl("td", { text: s.name || "" }));
      const pages = s.page_start && s.page_end ? `p.${s.page_start}–${s.page_end}` : "";
      tr.appendChild(createEl("td", { className: "muted", text: pages }));
      tr.appendChild(createEl("td", { text: s.summary || "" }));
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    normalizedContent.appendChild(wrap);
    return;
  }

  if (selectedNormalizedTab === "contributions" || selectedNormalizedTab === "claims") {
    const items = asArray(normalized[selectedNormalizedTab]);
    if (!items.length) {
      normalizedContent.appendChild(createEl("div", { className: "muted", text: `No ${selectedNormalizedTab}.` }));
      return;
    }
    for (const x of items) {
      const item = createEl("div", { className: "item" });
      const row = createEl("div", { className: "row" });
      row.appendChild(pill(`Conf ${fmtPercent(x.confidence)}`, "muted"));
      row.appendChild(createEl("div", { className: "item-text", text: x.text || "" }));
      item.appendChild(row);
      const ev = renderEvidenceBlock(x.evidence);
      if (ev) item.appendChild(ev);
      normalizedContent.appendChild(item);
    }
    return;
  }

  if (selectedNormalizedTab === "limitations") {
    const items = asArray(normalized.limitations);
    if (!items.length) {
      normalizedContent.appendChild(createEl("div", { className: "muted", text: "No limitations." }));
      return;
    }
    for (const x of items) {
      const item = createEl("div", { className: "item" });
      const row = createEl("div", { className: "row" });
      row.appendChild(pill((x.status || "unknown").toUpperCase(), `lim-${x.status || "unknown"}`));
      row.appendChild(createEl("div", { className: "item-text", text: x.text || "" }));
      item.appendChild(row);
      const ev = renderEvidenceBlock(x.evidence);
      if (ev) item.appendChild(ev);
      normalizedContent.appendChild(item);
    }
    return;
  }

  if (selectedNormalizedTab === "figures" || selectedNormalizedTab === "tables") {
    const items = asArray(normalized[selectedNormalizedTab]);
    if (!items.length) {
      normalizedContent.appendChild(createEl("div", { className: "muted", text: `No ${selectedNormalizedTab}.` }));
      return;
    }
    for (const x of items) {
      const item = createEl("div", { className: "item" });
      const head = createEl("div", { className: "row" });
      head.appendChild(pill(x.id || "-", "muted"));
      head.appendChild(pill(`p.${x.page ?? "?"}`, "page"));
      item.appendChild(head);
      if (x.caption) item.appendChild(createEl("div", { className: "item-text", text: x.caption }));
      if (x.why_important) item.appendChild(createEl("div", { className: "muted", text: x.why_important }));
      normalizedContent.appendChild(item);
    }
    return;
  }

  if (selectedNormalizedTab === "summaries") {
    const sec = createEl("div", { className: "section" });
    sec.appendChild(createEl("div", { className: "section-subtitle", text: "Method summary" }));
    sec.appendChild(createEl("div", { className: "prose", text: normalized.method_summary || "" }));
    sec.appendChild(createEl("div", { className: "section-subtitle", text: "Experiments summary" }));
    sec.appendChild(createEl("div", { className: "prose", text: normalized.experiments_summary || "" }));
    normalizedContent.appendChild(sec);
    return;
  }

  if (selectedNormalizedTab === "reproducibility") {
    const r = normalized.reproducibility || {};
    const kv = createEl("div", { className: "kv" });
    kv.appendChild(kvRow("Code", pill(String(r.code_status || "unknown"), "muted")));
    kv.appendChild(kvRow("Data", pill(String(r.data_status || "unknown"), "muted")));
    normalizedContent.appendChild(kv);
    if (r.notes) normalizedContent.appendChild(createEl("div", { className: "prose", text: r.notes }));
    const ev = renderEvidenceBlock(r.evidence);
    if (ev) normalizedContent.appendChild(ev);
  }
}

function renderDiagnostics(canonical, missingTranslation = false) {
  diagnosticsView.replaceChildren();
  if (!canonical) {
    const msg = missingTranslation ? "한국어 없음" : "No analysis output yet.";
    diagnosticsView.appendChild(createEl("div", { className: "muted", text: msg }));
    return;
  }
  const d = canonical.diagnostics || {};
  const unknowns = asArray(d.unknowns);
  if (unknowns.length) {
    diagnosticsView.appendChild(createEl("div", { className: "section-title", text: "Unknowns" }));
    diagnosticsView.appendChild(renderBullets(unknowns));
  }
  if (d.notes) {
    diagnosticsView.appendChild(createEl("div", { className: "section-title", text: "Notes" }));
    diagnosticsView.appendChild(createEl("div", { className: "prose", text: d.notes }));
  }
}

function folderTreeRows() {
  const byParent = new Map();
  for (const f of folders) {
    const parentId = f.parent_id || null;
    if (!byParent.has(parentId)) byParent.set(parentId, []);
    byParent.get(parentId).push(f);
  }
  for (const arr of byParent.values()) arr.sort((a, b) => String(a.name).localeCompare(String(b.name)));

  const out = [];
  const walk = (parentId, depth) => {
    for (const f of byParent.get(parentId) || []) {
      out.push({ folder: f, depth });
      walk(f.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

function folderPaperCounts() {
  const counts = new Map();
  for (const item of paperSummaries) {
    const fid = item.paper?.folder_id || null;
    if (!fid) continue;
    counts.set(fid, (counts.get(fid) || 0) + 1);
  }
  return counts;
}

function renderFolders() {
  if (!foldersList) return;
  closePaperMenu();
  foldersList.innerHTML = "";

  const counts = folderPaperCounts();
  const total = paperSummaries.length;
  const unfiledCount = paperSummaries.filter((x) => !x.paper?.folder_id).length;

  const renderRow = (opts) => {
    const { id, label, depth = 0, count = null, kind = "folder", folder = null } = opts;
    const isActive =
      (kind === "all" && selectedFolderMode === "all") ||
      (kind === "unfiled" && selectedFolderMode === "unfiled") ||
      (kind === "folder" && selectedFolderMode === "folder" && selectedFolderId === id);

    const row = createEl("div", { className: `folder-item ${isActive ? "active" : ""}` });
    row.style.paddingLeft = `${8 + depth * 14}px`;

    const icon = createEl("div", { className: "folder-icon", text: kind === "folder" ? "▣" : "▦" });
    const name = createEl("div", { className: "folder-name", text: label });
    const c = createEl("div", { className: "folder-count", text: count === null ? "" : String(count) });

    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(c);

    if (kind === "folder" && folder) {
      const menuBtn = createEl("button", {
        className: "paper-menu-btn",
        text: "...",
        attrs: { type: "button", "aria-label": "Folder actions" },
      });
      menuBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleFolderMenu(menuBtn, folder);
      });
      menuBtn.addEventListener("mousedown", (e) => e.stopPropagation());
      menuBtn.addEventListener("dragstart", (e) => e.preventDefault());
      row.appendChild(menuBtn);
    }

    const dropFolderId = kind === "folder" ? id : kind === "unfiled" ? null : undefined;
    if (dropFolderId !== undefined) {
      row.addEventListener("dragover", (e) => {
        e.preventDefault();
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
      row.addEventListener("drop", async (e) => {
        e.preventDefault();
        row.classList.remove("drop-target");
        const paperId = e.dataTransfer ? e.dataTransfer.getData("text/paper-id") : "";
        if (!paperId) return;
        await setPaperFolder(paperId, dropFolderId);
      });
    }

    row.addEventListener("click", () => {
      closePaperMenu();
      if (kind === "all") setFolderSelection("all");
      else if (kind === "unfiled") setFolderSelection("unfiled");
      else setFolderSelection("folder", id);
    });

    foldersList.appendChild(row);
  };

  renderRow({ id: null, label: "All papers", kind: "all", count: total });
  renderRow({ id: null, label: "Unfiled", kind: "unfiled", count: unfiledCount });

  for (const { folder, depth } of folderTreeRows()) {
    renderRow({
      id: folder.id,
      label: folder.name,
      depth,
      kind: "folder",
      folder,
      count: counts.get(folder.id) || 0,
    });
  }
}

async function refreshFolders() {
  if (!foldersList) return;
  const items = await api("/api/folders");
  folders = items;
  folderById = new Map(items.map((f) => [f.id, f]));

  if (selectedFolderMode === "folder" && selectedFolderId && !folderById.has(selectedFolderId)) {
    selectedFolderMode = "all";
    selectedFolderId = null;
  }

  renderFolders();
}

async function createFolder() {
  const value = prompt("New folder name", "");
  if (value === null) return;
  const name = value.trim();
  if (!name) {
    toast("Folder name cannot be empty.", "error", 5000);
    return;
  }
  const parentId = selectedFolderMode === "folder" ? selectedFolderId : null;
  await api("/api/folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, parent_id: parentId }),
  });
  toast("Folder created.", "success");
  await refreshFolders();
}

async function renameFolder(folder) {
  const current = folder.name || "";
  const value = prompt("Rename folder", current);
  if (value === null) return;
  const name = value.trim();
  if (!name) {
    toast("Folder name cannot be empty.", "error", 5000);
    return;
  }
  await api(`/api/folders/${folder.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  toast("Renamed.", "success");
  await refreshFolders();
}

async function deleteFolder(folder) {
  const ok = confirm(`Delete this folder?\n\n${folder.name}`);
  if (!ok) return;
  await api(`/api/folders/${folder.id}`, { method: "DELETE" });
  toast("Folder deleted.", "success");
  if (selectedFolderMode === "folder" && selectedFolderId === folder.id) setFolderSelection("all");
  await refreshFolders();
  await refreshPapers();
}

async function setPaperFolder(paperId, folderId) {
  await api(`/api/papers/${paperId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_id: folderId }),
  });
  toast("Moved.", "success");
  await refreshPapers();
  await refreshFolders();
  if (selectedPaperId === paperId) await loadDetails(selectedPaperId);
}

async function setPaperReadStatus(paperId, status) {
  const next = status === "done" ? "done" : "to_read";
  await api(`/api/papers/${paperId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: next }),
  });
  toast(next === "done" ? "읽음으로 표시함." : "아직 안 읽음으로 표시함.", "success");
  await refreshPapers();
  if (selectedPaperId === paperId) await loadDetails(selectedPaperId);
}

async function movePaperPrompt(paper) {
  const current = folderName(paper.folder_id) || "Unfiled";
  const rows = folderTreeRows();
  const options = [{ label: "Unfiled", id: null }].concat(
    rows.map(({ folder, depth }) => ({
      label: `${"  ".repeat(depth)}${folder.name}`,
      id: folder.id,
    })),
  );
  const lines = options.map((o, i) => `${i}: ${o.label}`).join("\n");
  const value = prompt(`Move to which folder? (current: ${current})\n\n${lines}\n\nEnter number:`, "0");
  if (value === null) return;
  const idx = Number(value.trim());
  if (!Number.isInteger(idx) || idx < 0 || idx >= options.length) {
    toast("Invalid selection.", "error", 5000);
    return;
  }
  await setPaperFolder(paper.id, options[idx].id);
}

function renderPaperControls(paper) {
  if (!paperControls) return;
  paperControls.replaceChildren();
  if (!paper) return;

  const statusSelect = createEl("select", { className: "select", attrs: { "aria-label": "읽기 상태" } });
  statusSelect.appendChild(createEl("option", { text: "아직 안 읽음", attrs: { value: "to_read" } }));
  statusSelect.appendChild(createEl("option", { text: "읽음", attrs: { value: "done" } }));
  statusSelect.value = paper.status === "done" ? "done" : "to_read";

  let prevStatus = statusSelect.value;
  statusSelect.addEventListener("change", async (e) => {
    e.preventDefault();
    const next = statusSelect.value;
    if (next === prevStatus) return;
    statusSelect.disabled = true;
    try {
      await setPaperReadStatus(paper.id, next);
      prevStatus = next;
    } catch (err) {
      statusSelect.value = prevStatus;
      toast(String(err?.message || err), "error", 6500);
    } finally {
      statusSelect.disabled = false;
    }
  });

  paperControls.appendChild(statusSelect);

  const hasPdf =
    paper.drive_file_id &&
    !paper.drive_file_id.startsWith("doi_only:") &&
    !paper.drive_file_id.startsWith("import_json:");
  const isLocalPdf = hasPdf && paper.drive_file_id.startsWith("upload:");
  const isDrivePdf = hasPdf && !isLocalPdf;

  const pdfBtn = createEl("button", {
    className: "btn btn-secondary btn-small",
    text: "PDF ▾",
    attrs: { type: "button" },
  });
  const pdfUploadInput = createEl("input", {
    className: "hidden",
    attrs: { type: "file", accept: "application/pdf" },
  });

  const uploadPdf = async (file) => {
    if (!file) return;
    if (hasPdf) {
      const ok = confirm("기존 PDF를 삭제하고 새 PDF로 교체할까요?");
      if (!ok) return;
    }
    pdfBtn.disabled = true;
    const prevText = pdfBtn.textContent;
    pdfBtn.textContent = "업로드중...";
    try {
      const updated = await api(`/api/papers/${paper.id}/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/pdf" },
        body: file,
      });
      const dfid = updated && updated.drive_file_id ? String(updated.drive_file_id) : "";
      toast(dfid.startsWith("upload:") ? "PDF 서버에 저장됨." : "PDF Google Drive에 저장됨.", "success");
      await refreshPapers();
      if (selectedPaperId === paper.id) await loadDetails(selectedPaperId);
    } catch (err) {
      toast(String(err?.message || err), "error", 6500);
    } finally {
      pdfBtn.disabled = false;
      pdfBtn.textContent = prevText;
      pdfUploadInput.value = "";
    }
  };

  pdfUploadInput.addEventListener("change", async (e) => {
    e.preventDefault();
    const file = pdfUploadInput.files && pdfUploadInput.files[0] ? pdfUploadInput.files[0] : null;
    await uploadPdf(file);
  });

  pdfBtn.addEventListener("click", (e) => {
    e.preventDefault();
    toggleMenu(pdfBtn, `detail:pdf:${paper.id}`, [
      {
        label: hasPdf ? "보기/다운로드" : "보기/다운로드 (없음)",
        onClick: async () => {
          if (!hasPdf) {
            toast("PDF 없음", "info");
            return;
          }
          window.open(`/api/papers/${paper.id}/pdf`, "_blank", "noopener");
        },
      },
      ...(isDrivePdf
        ? [
            {
              label: "Drive에서 열기",
              onClick: async () => {
                const id = paper.drive_file_id;
                window.open(`https://drive.google.com/file/d/${id}/view`, "_blank", "noopener");
              },
            },
          ]
        : []),
      {
        label: hasPdf ? "교체 업로드..." : "업로드...",
        onClick: async () => {
          pdfUploadInput.click();
        },
      },
    ]);
  });

  const moreBtn = createEl("button", {
    className: "btn btn-secondary btn-small",
    text: "More ▾",
    attrs: { type: "button" },
  });
  moreBtn.addEventListener("click", (e) => {
    e.preventDefault();
    const langLabel = currentJsonLangKey() === "ko" ? "한국어" : "원문";
    toggleMenu(moreBtn, `detail:more:${paper.id}`, [
      { label: "폴더 이동...", onClick: () => movePaperPrompt(paper) },
      { label: "제목 변경...", onClick: () => renamePaper(paper) },
      { type: "sep" },
      { label: `JSON 저장 (${langLabel})`, onClick: () => saveCurrentJson() },
      {
        label: `JSON Copy (${langLabel})`,
        onClick: async () => {
          await copyToClipboard(jsonEditor ? jsonEditor.value : "");
          toast("Copied.", "success");
        },
      },
      { type: "sep" },
      { label: "삭제...", danger: true, onClick: () => deletePaper(paper) },
    ]);
  });

  paperControls.appendChild(pdfBtn);
  paperControls.appendChild(moreBtn);
  paperControls.appendChild(pdfUploadInput);

  /* DOI edit controls disabled for now.
  const doiWrap = createEl("div", { className: "doi-edit" });
  const doiField = createEl("input", {
    attrs: { type: "text", placeholder: "DOI" },
  });
  doiField.value = paper.doi || "";
  const doiSaveBtn = createEl("button", {
    className: "btn btn-secondary btn-small",
    text: "Save DOI",
    attrs: { type: "button" },
  });

  const saveDoi = async () => {
    const next = doiField.value.trim();
    const current = paper.doi || "";
    if (next === current) return;
    try {
      await api(`/api/papers/${paper.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doi: next || null }),
      });
      toast("DOI updated.", "success");
      await refreshPapers();
      if (selectedPaperId === paper.id) await loadDetails(selectedPaperId);
    } catch (e) {
      toast(String(e.message || e), "error", 6500);
    }
  };

  doiField.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveDoi();
    }
  });
  doiSaveBtn.addEventListener("click", (e) => {
    e.preventDefault();
    saveDoi();
  });

  doiWrap.appendChild(doiField);
  doiWrap.appendChild(doiSaveBtn);
  paperControls.appendChild(doiWrap);
  */
}

async function renamePaper(paper) {
  const current = paper.title || "";
  const value = prompt("Rename paper (title)", current);
  if (value === null) return;
  const next = value.trim();
  if (!next) {
    toast("Title cannot be empty.", "error", 5000);
    return;
  }
  await api(`/api/papers/${paper.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: next }),
  });
  toast("Renamed.", "success");
  await refreshPapers();
  if (selectedPaperId === paper.id) await loadDetails(selectedPaperId);
}

async function deletePaper(paper) {
  const label = paper.title || paper.doi || paper.id;
  const ok = confirm(`Delete this paper?\n\n${label}`);
  if (!ok) return;
  stopPolling();
  await api(`/api/papers/${paper.id}`, { method: "DELETE" });
  toast("Deleted.", "success");
  if (selectedPaperId === paper.id) selectedPaperId = null;
  await refreshPapers();
  await loadDetails(selectedPaperId);
}

function renderPapers(items) {
  papersList.innerHTML = "";
  closePaperMenu();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    const q = (paperSearch && paperSearch.value ? paperSearch.value : "").trim();
    empty.textContent = q ? "No matches." : "No papers yet.";
    papersList.appendChild(empty);
    return;
  }

  for (const item of items) {
    const div = document.createElement("div");
    div.className = "list-item";
    if (item.paper.id === selectedPaperId) div.classList.add("active");
    div.draggable = true;

    div.addEventListener("dragstart", (e) => {
      closePaperMenu();
      div.classList.add("dragging");
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/paper-id", item.paper.id);
      }
    });
    div.addEventListener("dragend", () => {
      div.classList.remove("dragging");
    });

    const main = createEl("div", { className: "paper-main" });
    main.appendChild(createEl("div", { className: "paper-title", text: normalizeTitle(item) }));

    const p = item.paper || {};
    const metaParts = [];
    if (p.doi) metaParts.push(`doi: ${p.doi}`);
    metaParts.push(`읽기: ${paperReadLabel(p.status)}`);
    if (selectedFolderMode === "all") {
      const fn = folderName(p.folder_id);
      metaParts.push(fn ? `folder: ${fn}` : "unfiled");
    }
    main.appendChild(createEl("div", { className: "paper-meta", text: metaParts.join(" | ") }));



    const menuBtn = createEl("button", {
      className: "paper-menu-btn",
      text: "...",
      attrs: { type: "button", "aria-label": "Actions" },
    });
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePaperMenu(menuBtn, item.paper);
    });
    menuBtn.addEventListener("mousedown", (e) => e.stopPropagation());
    menuBtn.addEventListener("dragstart", (e) => e.preventDefault());

    div.appendChild(main);
    div.appendChild(menuBtn);

    div.addEventListener("click", async () => {
      closePaperMenu();
      selectedPaperId = item.paper.id;
      applyPapersFilter();
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

function isGraphOpen() {
  return graphOverlay && !graphOverlay.classList.contains("hidden");
}

function closeGraph() {
  if (!graphOverlay) return;
  graphOverlay.classList.add("hidden");
  graphOverlay.classList.remove("dragging");
  document.body.classList.remove("graph-open");
  if (graphSearch) graphSearch.value = "";
  if (graphStatus) graphStatus.textContent = "";

  if (graphState && graphState.rafId) {
    cancelAnimationFrame(graphState.rafId);
    graphState.rafId = null;
  }
  if (graphState) {
    graphState.running = false;
    graphState.dragging = false;
    graphState.dragMode = null;
    graphState.dragPointerId = null;
    graphState.dragNode = null;
    if (graphState.pointers) graphState.pointers.clear();
    graphState.hoverId = null;
    if (graphState.canvas) graphState.canvas.style.cursor = "grab";
  }
  window.removeEventListener("resize", onGraphResize);
  window.removeEventListener("keydown", onGraphKeydown, true);
}

function isRecsOpen() {
  return recsOverlay && !recsOverlay.classList.contains("hidden");
}

function closeRecs() {
  if (!recsOverlay) return;
  stopRecsTaskPolling();
  recsOverlay.classList.add("hidden");
  document.body.classList.remove("graph-open");
  window.removeEventListener("keydown", onRecsKeydown, true);
}

function onRecsKeydown(e) {
  if (e.key === "Escape") {
    e.preventDefault();
    closeRecs();
  }
}

function setRecsBadge(count) {
  if (!recsBtn) return;
  const n = Math.max(0, Number(count || 0));
  show(recsBtn);
  if (!recsBadge) return;
  if (n <= 0) {
    hide(recsBadge);
    recsBadge.textContent = "";
    return;
  }
  show(recsBadge);
  recsBadge.textContent = String(n);
}

function renderRecs(run) {
  if (!recsContent) return;
  recsContent.innerHTML = "";
  if (!run || !Array.isArray(run.items) || run.items.length === 0) {
    if (recsMeta) recsMeta.textContent = "No recommendations.";
    return;
  }

  const createdAt = run.created_at ? String(run.created_at) : "";
  if (recsMeta) recsMeta.textContent = `Updated: ${createdAt}`;

  const groups = new Map();
  for (const item of run.items) {
    const kind = item?.kind || "folder";
    const fid = item?.folder_id || "";
    const key = `${kind}:${fid}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }

  const groupEntries = Array.from(groups.entries());
  groupEntries.sort((a, b) => {
    const [ka] = a;
    const [kb] = b;
    const aIsCross = ka.startsWith("cross_domain");
    const bIsCross = kb.startsWith("cross_domain");
    if (aIsCross !== bIsCross) return aIsCross ? 1 : -1;
    return ka.localeCompare(kb);
  });

  function clipText(t, n) {
    const s = String(t || "").trim();
    if (!s) return "";
    if (s.length <= n) return s;
    return `${s.slice(0, n).trim()}...`;
  }

  function resolveRecText(it, field) {
    const original = String(it?.[field] || "").trim();
    if (selectedRecsLang === "ko") {
      const key = `${field}_ko`;
      const translated = String(it?.[key] || "").trim();
      if (translated) return { text: translated, missing: false };
      if (original) return { text: "한국어 없음", missing: true };
      return { text: "", missing: false };
    }
    return { text: original, missing: false };
  }

  for (const [key, items] of groupEntries) {
    items.sort((x, y) => Number(x?.rank || 0) - Number(y?.rank || 0));
    const [kind, fid] = key.split(":", 2);
    const title =
      kind === "cross_domain"
        ? "Cross-domain"
        : folderName(fid) || (fid ? `Folder ${fid.slice(0, 8)}` : "Folder");

    const groupEl = createEl("div", { className: "recs-group" });
    groupEl.appendChild(createEl("div", { className: "recs-group-title", text: title }));

    for (const it of items) {
      const itemEl = createEl("div", { className: "recs-item" });
      const titleEl = createEl("div", { className: "recs-title" });
      const rank = Number(it?.rank || 0);
      const rankEl = rank > 0 ? createEl("span", { className: "badge recs-rank", text: `#${rank}` }) : null;
      if (rankEl) titleEl.appendChild(rankEl);
      const link = String(it?.url || "").trim();
      if (link) {
        titleEl.appendChild(
          createEl("a", {
            text: String(it?.title || "(untitled)"),
            attrs: { href: link, target: "_blank", rel: "noreferrer" },
          }),
        );
      } else {
        titleEl.appendChild(createEl("span", { text: String(it?.title || "(untitled)") }));
      }
      const excludeBtn = createEl("button", {
        className: "btn btn-ghost btn-small",
        text: "Exclude",
        attrs: { type: "button" },
      });
      excludeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        excludeRecommendation(it?.id);
      });
      titleEl.appendChild(excludeBtn);

      const metaParts = [];
      if (it?.year) metaParts.push(String(it.year));
      if (it?.venue) metaParts.push(String(it.venue));
      if (it?.doi) metaParts.push(`doi: ${it.doi}`);
      if (typeof it?.score === "number") metaParts.push(`score: ${it.score.toFixed(3)}`);

      const metaEl = createEl("div", { className: "recs-meta muted", text: metaParts.join(" | ") });

      const oneLiner = resolveRecText(it, "one_liner");
      const oneLinerEl = oneLiner.text
        ? createEl("div", {
            className: `recs-oneliner${oneLiner.missing ? " recs-missing" : ""}`,
            text: oneLiner.text,
          })
        : null;

      const summary = resolveRecText(it, "summary");
      const summaryEl = summary.text
        ? createEl("div", {
            className: `recs-summary${summary.missing ? " recs-missing" : ""}`,
            text: summary.text,
          })
        : null;

      const abstract = resolveRecText(it, "abstract");
      const abstractMax = 420;
      const abstractNeedsToggle = abstract.text && !abstract.missing && abstract.text.length > abstractMax;
      let abstractExpanded = false;
      const abstractBody = abstract.text
        ? createEl("div", {
            className: "recs-abstract-text",
            text: abstractNeedsToggle ? clipText(abstract.text, abstractMax) : abstract.text,
          })
        : null;
      const abstractBtn = abstractNeedsToggle
        ? createEl("button", { className: "btn btn-ghost btn-small", text: "???" })
        : null;
      const abstractEl = abstract.text
        ? createEl("div", { className: `recs-abstract${abstract.missing ? " recs-missing" : ""}` })
        : null;

      if (abstractEl && abstractBody) {
        abstractEl.appendChild(abstractBody);
        if (abstractBtn) {
          abstractBtn.addEventListener("click", (e) => {
            e.preventDefault();
            abstractExpanded = !abstractExpanded;
            abstractBody.textContent = abstractExpanded ? abstract.text : clipText(abstract.text, abstractMax);
            abstractBtn.textContent = abstractExpanded ? "??" : "???";
          });
          const actions = createEl("div", { className: "recs-abstract-actions" });
          actions.appendChild(abstractBtn);
          abstractEl.appendChild(actions);
        }
      }

      itemEl.appendChild(titleEl);
      if (metaParts.length) itemEl.appendChild(metaEl);
      if (oneLinerEl) itemEl.appendChild(oneLinerEl);
      if (summaryEl) itemEl.appendChild(summaryEl);
      if (abstractEl) itemEl.appendChild(abstractEl);
      groupEl.appendChild(itemEl);
    }

    recsContent.appendChild(groupEl);
  }
}

function stopRecsTaskPolling() {
  if (recsTaskPollHandle) {
    clearTimeout(recsTaskPollHandle);
    recsTaskPollHandle = null;
  }
}

function setRecsLogsVisible(visible) {
  recsLogsVisible = Boolean(visible);
  if (!recsLogsPanel) return;
  if (recsLogsVisible) {
    show(recsLogsPanel);
    recsLogsPanel.setAttribute("aria-hidden", "false");
  } else {
    hide(recsLogsPanel);
    recsLogsPanel.setAttribute("aria-hidden", "true");
  }
}

function toggleRecsLogs() {
  setRecsLogsVisible(!recsLogsVisible);
  if (recsLogsVisible) renderRecsTask(latestRecsTask);
}

function formatTaskLogs(logs) {
  if (!Array.isArray(logs) || logs.length === 0) return "";
  const recent = logs.slice(-250);
  return recent
    .map((l) => {
      const ts = l?.ts ? String(l.ts) : "";
      const level = l?.level ? String(l.level).toUpperCase() : "INFO";
      const msg = l?.message ? String(l.message) : "";
      return `${ts} [${level}] ${msg}`.trimEnd();
    })
    .join("\n")
    .trim();
}

function renderRecsTask(task) {
  latestRecsTask = task || null;

  const status = String(task?.status || "").trim() || null;
  const startedAt = task?.started_at ? String(task.started_at) : "";
  const finishedAt = task?.finished_at ? String(task.finished_at) : "";
  const error = task?.error ? String(task.error) : "";

  if (recsRunBtn) {
    const running = status === "running";
    recsRunBtn.disabled = running;
    recsRunBtn.textContent = running ? "Running…" : "Run";
  }

  if (recsTaskMeta) {
    if (!task) {
      recsTaskMeta.textContent = "";
    } else if (status === "running") {
      recsTaskMeta.textContent = startedAt ? `Recommender: running (started ${startedAt})` : "Recommender: running";
    } else if (status === "succeeded") {
      recsTaskMeta.textContent = finishedAt ? `Recommender: done (finished ${finishedAt})` : "Recommender: done";
    } else if (status === "failed") {
      recsTaskMeta.textContent = `Recommender: failed${error ? ` (${error})` : ""}`;
    } else {
      recsTaskMeta.textContent = `Recommender: ${status}`;
    }
  }

  if (recsLogs && recsLogsVisible) {
    recsLogs.textContent = formatTaskLogs(task?.logs || []);
    recsLogs.scrollTop = recsLogs.scrollHeight;
  }
}

async function pollRecsTask(taskId) {
  stopRecsTaskPolling();

  const id = String(taskId || "").trim();
  if (!id) return;

  const tick = async () => {
    if (!isRecsOpen()) return;
    try {
      const task = await api(`/api/recommendations/tasks/${id}`);
      renderRecsTask(task);

      const status = String(task?.status || "").trim();
      if (status === "running") {
        recsTaskPollHandle = setTimeout(tick, 1200);
        return;
      }

      if (status === "succeeded") {
        await refreshRecommendations({ silent: true });
        if (isRecsOpen()) renderRecs(latestRecs);
      }
    } catch (e) {
      console.warn("recs task poll failed:", e);
      recsTaskPollHandle = setTimeout(tick, 2500);
    }
  };

  recsTaskPollHandle = setTimeout(tick, 250);
}

async function refreshRecsTask({ silent = false } = {}) {
  try {
    const task = await api("/api/recommendations/tasks/latest");
    renderRecsTask(task);
    if (String(task?.status || "") === "running") await pollRecsTask(task.id);
  } catch (e) {
    if (e && e.status === 404) {
      renderRecsTask(null);
      return;
    }
    if (!silent) toast(String(e.message || e), "error", 6500);
  }
}

async function startRecsTask() {
  const ok = confirm("새로 추천을 생성할까요? (잠시 걸릴 수 있어요)");
  if (!ok) return;
  try {
    if (recsRunBtn) {
      recsRunBtn.disabled = true;
      recsRunBtn.textContent = "Starting…";
    }
    if (recsTaskMeta) recsTaskMeta.textContent = "Recommender: starting…";
    const task = await api("/api/recommendations/tasks", { method: "POST" });
    toast("Recommender started.", "info");
    renderRecsTask(task);
    await pollRecsTask(task.id);
  } catch (e) {
    toast(String(e.message || e), "error", 6500);
    await refreshRecsTask({ silent: true });
  }
}

async function refreshRecommendations({ silent = false } = {}) {
  try {
    latestRecs = await api("/api/recommendations/latest");
    setRecsBadge(latestRecs?.items?.length || 0);
    if (isRecsOpen()) renderRecs(latestRecs);
  } catch (e) {
    if (e && e.status === 404) {
      latestRecs = null;
      setRecsBadge(0);
      if (recsMeta) recsMeta.textContent = "No recommendations.";
      if (isRecsOpen()) renderRecs(null);
      return;
    }
    if (!silent) toast(String(e.message || e), "error", 6500);
  }
}

async function translateRecommendations() {
  const runId = latestRecs?.id;
  if (!runId) {
    toast("No recommendations to translate.", "error");
    return;
  }
  if (recsTranslateBtn) {
    recsTranslateBtn.disabled = true;
    recsTranslateBtn.textContent = "Translating...";
  }
  setLogPanel(recsTranslateLogsPanel, recsTranslateLogs, ["Translating recommendations..."]);
  try {
    const res = await api(`/api/recommendations/${runId}/translate`, { method: "POST" });
    const logs = res && Array.isArray(res.logs) ? res.logs : [];
    setLogPanel(recsTranslateLogsPanel, recsTranslateLogs, logs);
    if (res && res.ok === false) {
      toast(res.error || "Translation failed.", "error", 6500);
      return;
    }
    const count = typeof res?.translated === "number" ? res.translated : null;
    toast(count ? `Translated ${count} item(s).` : "Translated.", "success");
    await refreshRecommendations({ silent: true });
    if (isRecsOpen()) renderRecs(latestRecs);
  } catch (e) {
    setLogPanel(recsTranslateLogsPanel, recsTranslateLogs, [`Error: ${e.message || e}`]);
    toast(String(e.message || e), "error", 6500);
  } finally {
    if (recsTranslateBtn) {
      recsTranslateBtn.disabled = false;
      recsTranslateBtn.textContent = "번역하기";
    }
  }
}

async function excludeRecommendation(itemId) {
  const id = String(itemId || "").trim();
  if (!id) return;
  const ok = confirm("이 추천을 제외할까? (다음부터 목록에 안 나오게 할게)");
  if (!ok) return;
  try {
    await api("/api/recommendations/excludes", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ item_id: id }),
    });
    toast("Excluded.", "info");
    await refreshRecommendations({ silent: true });
    if (isRecsOpen()) renderRecs(latestRecs);
  } catch (e) {
    toast(String(e.message || e), "error", 6500);
  }
}

async function openRecs() {
  if (!recsOverlay) return;
  closePaperMenu();
  closeGraph();

  recsOverlay.classList.remove("hidden");
  document.body.classList.add("graph-open");
  window.addEventListener("keydown", onRecsKeydown, true);

  if (recsMeta) recsMeta.textContent = "Loading...";
  if (recsTaskMeta) recsTaskMeta.textContent = "";
  if (recsLogs) recsLogs.textContent = "";
  setRecsLogsVisible(false);
  setLogPanel(recsTranslateLogsPanel, recsTranslateLogs, null);
  await refreshRecsTask({ silent: true });
  await refreshRecommendations({ silent: true });
  renderRecs(latestRecs);
}

function graphCssColors() {
  const s = getComputedStyle(document.documentElement);
  return {
    text: s.getPropertyValue("--text").trim() || "#0f172a",
    muted: s.getPropertyValue("--muted").trim() || "#475569",
    border: s.getPropertyValue("--border").trim() || "rgba(15, 23, 42, 0.12)",
    primary: s.getPropertyValue("--primary").trim() || "#2563eb",
  };
}

function hashHue(text) {
  const raw = String(text || "");
  let h = 0;
  for (let i = 0; i < raw.length; i += 1) h = (h * 31 + raw.charCodeAt(i)) >>> 0;
  return h % 360;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function ensureGraphState() {
  if (!graphOverlay || !graphCanvas) return null;
  if (graphState) return graphState;

  const ctx = graphCanvas.getContext("2d");
  if (!ctx) return null;

  graphState = {
    canvas: graphCanvas,
    ctx,
    dpr: 1,
    width: 0,
    height: 0,
    panX: 0,
    panY: 0,
    scale: 1,
    nodes: [],
    edges: [],
    nodeById: new Map(),
    pointers: new Map(),
    dragging: false,
    dragMode: null,
    dragPointerId: null,
    dragNode: null,
    dragStartX: 0,
    dragStartY: 0,
    dragPanX: 0,
    dragPanY: 0,
    dragNodeOffsetX: 0,
    dragNodeOffsetY: 0,
    pinchStartDist: 0,
    pinchStartScale: 1,
    pinchWorldX: 0,
    pinchWorldY: 0,
    moved: false,
    hoverId: null,
    highlightId: null,
    rafId: null,
    running: false,
    userInteracted: false,
    lastFilterKey: null,
    filterLabel: "All papers",
    colors: graphCssColors(),
    theme: currentTheme(),
  };

  const screenToWorld = (sx, sy) => {
    const st = graphState;
    return { x: (sx - st.panX) / st.scale, y: (sy - st.panY) / st.scale };
  };

  const pickNode = (sx, sy, hitSlop = 0) => {
    const st = graphState;
    let best = null;
    let bestD2 = Infinity;
    for (const n of st.nodes) {
      const px = n.x * st.scale + st.panX;
      const py = n.y * st.scale + st.panY;
      const z = Math.sqrt(st.scale);
      const r = clamp((n.r + 2) * z, 6, 36) + hitSlop;
      const dx = px - sx;
      const dy = py - sy;
      const d2 = dx * dx + dy * dy;
      if (d2 <= r * r && d2 < bestD2) {
        best = n;
        bestD2 = d2;
      }
    }
    return best;
  };

  const localPos = (e) => {
    const st = graphState;
    const rect = st.canvas.getBoundingClientRect();
    return { sx: e.clientX - rect.left, sy: e.clientY - rect.top };
  };

  const startSingleDrag = (pointerId) => {
    const st = graphState;
    const p = st.pointers.get(pointerId);
    if (!p) return;

    const hitSlop = p.type === "touch" ? 14 : p.type === "pen" ? 8 : 0;
    const hit = pickNode(p.x, p.y, hitSlop);

    st.dragging = true;
    st.moved = false;
    st.dragMode = hit ? "node" : "pan";
    st.dragPointerId = pointerId;
    st.dragNode = hit || null;
    st.dragStartX = p.x;
    st.dragStartY = p.y;
    st.dragPanX = st.panX;
    st.dragPanY = st.panY;

    if (hit) {
      const w = screenToWorld(p.x, p.y);
      st.dragNodeOffsetX = hit.x - w.x;
      st.dragNodeOffsetY = hit.y - w.y;
    }

    graphOverlay.classList.add("dragging");
  };

  const startPinch = () => {
    const st = graphState;
    if (st.pointers.size < 2) return;
    const pts = Array.from(st.pointers.values());
    const a = pts[0];
    const b = pts[1];

    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.hypot(dx, dy) || 1;
    const midX = (a.x + b.x) / 2;
    const midY = (a.y + b.y) / 2;

    st.dragging = true;
    st.dragMode = "pinch";
    st.dragPointerId = null;
    st.dragNode = null;

    st.pinchStartDist = dist;
    st.pinchStartScale = st.scale;
    st.pinchWorldX = (midX - st.panX) / st.scale;
    st.pinchWorldY = (midY - st.panY) / st.scale;

    graphOverlay.classList.add("dragging");
  };

  const onPointerDown = (e) => {
    if (!isGraphOpen()) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const st = graphState;

    const { sx, sy } = localPos(e);
    st.pointers.set(e.pointerId, { id: e.pointerId, x: sx, y: sy, type: e.pointerType });

    try {
      st.canvas.setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }

    if (st.pointers.size === 1) startSingleDrag(e.pointerId);
    else if (st.pointers.size === 2) startPinch();

    e.preventDefault();
  };

  const onPointerMove = (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;
    const { sx, sy } = localPos(e);

    const tracked = st.pointers.get(e.pointerId) || null;
    if (tracked) {
      tracked.x = sx;
      tracked.y = sy;
    }

    if (!st.dragging) {
      if (e.pointerType === "mouse") {
        const hit = pickNode(sx, sy, 0);
        st.hoverId = hit ? hit.id : null;
        st.canvas.style.cursor = hit ? "pointer" : "grab";
      }
      return;
    }

    if (st.dragMode === "pinch") {
      if (st.pointers.size < 2) return;
      const pts = Array.from(st.pointers.values());
      const a = pts[0];
      const b = pts[1];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.hypot(dx, dy) || 1;
      const midX = (a.x + b.x) / 2;
      const midY = (a.y + b.y) / 2;

      const factor = dist / (st.pinchStartDist || 1);
      const nextScale = clamp(st.pinchStartScale * factor, 0.2, 3.5);
      st.scale = nextScale;
      st.panX = midX - st.pinchWorldX * nextScale;
      st.panY = midY - st.pinchWorldY * nextScale;
      st.userInteracted = true;
      st.moved = true;
      e.preventDefault();
      return;
    }

    if (!tracked || st.dragPointerId !== e.pointerId) return;

    const dx = sx - st.dragStartX;
    const dy = sy - st.dragStartY;
    if (Math.abs(dx) + Math.abs(dy) > 2) st.moved = true;

    if (st.dragMode === "pan") {
      st.panX = st.dragPanX + dx;
      st.panY = st.dragPanY + dy;
      st.userInteracted = true;
    } else if (st.dragMode === "node" && st.dragNode) {
      const w = screenToWorld(sx, sy);
      st.dragNode.x = w.x + st.dragNodeOffsetX;
      st.dragNode.y = w.y + st.dragNodeOffsetY;
      st.dragNode.vx = 0;
      st.dragNode.vy = 0;
      st.userInteracted = true;
    }

    e.preventDefault();
  };

  const onPointerUp = async (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;

    const clickedNode =
      st.dragMode === "node" && st.dragPointerId === e.pointerId && st.dragNode && !st.moved
        ? st.dragNode
        : null;

    st.pointers.delete(e.pointerId);
    try {
      st.canvas.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }

    if (st.pointers.size === 0) {
      st.dragging = false;
      st.dragMode = null;
      st.dragPointerId = null;
      st.dragNode = null;
      graphOverlay.classList.remove("dragging");
    } else if (st.pointers.size === 1) {
      const [remainingId] = st.pointers.keys();
      const p = st.pointers.get(remainingId);
      st.dragging = true;
      st.dragMode = "pan";
      st.dragPointerId = remainingId;
      st.dragNode = null;
      st.moved = false;
      st.dragStartX = p.x;
      st.dragStartY = p.y;
      st.dragPanX = st.panX;
      st.dragPanY = st.panY;
      graphOverlay.classList.add("dragging");
    } else if (st.pointers.size >= 2) {
      startPinch();
    }

    if (clickedNode && st.pointers.size === 0) {
      closeGraph();
      selectedPaperId = clickedNode.id;
      applyPapersFilter();
      await loadDetails(clickedNode.id);
    }

    e.preventDefault();
  };

  const onWheel = (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;
    const rect = st.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const delta = clamp(e.deltaY, -120, 120);
    const factor = delta < 0 ? 1.12 : 1 / 1.12;

    const wx = (sx - st.panX) / st.scale;
    const wy = (sy - st.panY) / st.scale;
    const nextScale = clamp(st.scale * factor, 0.2, 3.5);
    st.scale = nextScale;
    st.panX = sx - wx * st.scale;
    st.panY = sy - wy * st.scale;
    st.userInteracted = true;
    e.preventDefault();
  };

  graphCanvas.addEventListener("pointerdown", onPointerDown);
  graphCanvas.addEventListener("pointermove", onPointerMove);
  graphCanvas.addEventListener("pointerup", onPointerUp);
  graphCanvas.addEventListener("pointercancel", onPointerUp);
  graphCanvas.addEventListener("pointerleave", () => {
    const st = graphState;
    if (!st || st.dragging) return;
    st.hoverId = null;
    st.canvas.style.cursor = "grab";
  });
  graphCanvas.addEventListener("wheel", onWheel, { passive: false });

  return graphState;
}

function onGraphResize() {
  if (!graphState || !graphOverlay || graphOverlay.classList.contains("hidden")) return;
  const st = graphState;
  const rect = st.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  st.dpr = dpr;
  st.width = rect.width;
  st.height = rect.height;
  st.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  st.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  st.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  if (!st.userInteracted) {
    if (st.nodes && st.nodes.length) graphZoomToFit();
    else {
      st.scale = 1;
      st.panX = rect.width / 2;
      st.panY = rect.height / 2;
    }
  }
}

function onGraphKeydown(e) {
  if (!isGraphOpen()) return;
  if (e.key === "Escape") {
    e.preventDefault();
    closeGraph();
  }
}

function graphSetData(graph) {
  const st = graphState;
  if (!st) return;

  const nodesIn = asArray(graph?.nodes);
  const edgesIn = asArray(graph?.edges);

  const degree = new Map();
  for (const e of edgesIn) {
    const a = String(e.a_paper_id || "");
    const b = String(e.b_paper_id || "");
    if (!a || !b) continue;
    degree.set(a, (degree.get(a) || 0) + 1);
    degree.set(b, (degree.get(b) || 0) + 1);
  }

  const prev = st.nodeById || new Map();
  const nodeById = new Map();
  const nodes = [];

  for (const n of nodesIn) {
    const id = String(n.id || "");
    if (!id) continue;
    const old = prev.get(id) || null;
    const d = degree.get(id) || 0;
    const baseR = clamp(6 + Math.min(20, d) * 1.2, 6, 30);
    const hue = hashHue(n.folder_id || id);
    nodes.push({
      id,
      title: n.title || null,
      doi: n.doi || null,
      folder_id: n.folder_id || null,
      x: old ? old.x : (Math.random() - 0.5) * 500,
      y: old ? old.y : (Math.random() - 0.5) * 500,
      vx: old ? old.vx : 0,
      vy: old ? old.vy : 0,
      r: baseR,
      degree: d,
      hue,
    });
  }

  for (const n of nodes) nodeById.set(n.id, n);

  const edges = [];
  for (const e of edgesIn) {
    const aId = String(e.a_paper_id || "");
    const bId = String(e.b_paper_id || "");
    const a = nodeById.get(aId);
    const b = nodeById.get(bId);
    if (!a || !b) continue;
    edges.push({ id: String(e.id || ""), a, b, source: e.source || "user" });
  }

  st.nodes = nodes;
  st.edges = edges;
  st.nodeById = nodeById;
  st.highlightId = selectedPaperId ? String(selectedPaperId) : null;

  if (graphStatus) {
    const prefix = st.filterLabel ? `${st.filterLabel} | ` : "";
    graphStatus.textContent = `${prefix}${nodes.length} nodes | ${edges.length} edges`;
  }
}

function graphStep() {
  const st = graphState;
  if (!st || !st.running) return;

  const nodes = st.nodes;
  const edges = st.edges;
  const REPULSION = 9000;
  const SPRING = 0.012;
  const SPRING_LEN = 140;
  const CENTER = 0.0006;
  const DAMP = 0.86;
  const MAX_V = 7;

  for (let i = 0; i < nodes.length; i += 1) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j += 1) {
      const b = nodes[j];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d2 = dx * dx + dy * dy + 0.01;
      const invD = 1 / Math.sqrt(d2);
      const f = (REPULSION / d2) * 0.6;
      const fx = dx * invD * f;
      const fy = dy * invD * f;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
  }

  for (const e of edges) {
    const a = e.a;
    const b = e.b;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) + 0.001;
    const diff = d - SPRING_LEN;
    const f = diff * SPRING;
    const fx = (dx / d) * f;
    const fy = (dy / d) * f;
    a.vx += fx;
    a.vy += fy;
    b.vx -= fx;
    b.vy -= fy;
  }

  for (const n of nodes) {
    if (st.dragMode === "node" && st.dragNode && st.dragNode.id === n.id) continue;
    n.vx += -n.x * CENTER;
    n.vy += -n.y * CENTER;
    n.vx *= DAMP;
    n.vy *= DAMP;
    n.vx = Math.max(-MAX_V, Math.min(MAX_V, n.vx));
    n.vy = Math.max(-MAX_V, Math.min(MAX_V, n.vy));
    n.x += n.vx;
    n.y += n.vy;
  }
}

function graphRender() {
  const st = graphState;
  if (!st) return;

  const theme = currentTheme();
  if (theme !== st.theme) {
    st.theme = theme;
    st.colors = graphCssColors();
  }

  const ctx = st.ctx;
  ctx.clearRect(0, 0, st.width, st.height);

  ctx.lineWidth = 1;
  ctx.strokeStyle = st.colors.border;
  ctx.globalAlpha = 0.85;

  for (const e of st.edges) {
    const ax = e.a.x * st.scale + st.panX;
    const ay = e.a.y * st.scale + st.panY;
    const bx = e.b.x * st.scale + st.panX;
    const by = e.b.y * st.scale + st.panY;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
  }

  ctx.globalAlpha = 1;
  for (const n of st.nodes) {
    const x = n.x * st.scale + st.panX;
    const y = n.y * st.scale + st.panY;
    const z = Math.sqrt(st.scale);
    const r = clamp((n.r + 2) * z, 4, 32);
    const isHover = st.hoverId === n.id;
    const isHi = st.highlightId === n.id;

    const alpha = theme === "dark" ? 0.26 : 0.18;
    const fill = `hsla(${n.hue}, 82%, 55%, ${alpha})`;
    const stroke = isHi ? st.colors.primary : `hsla(${n.hue}, 82%, 45%, 0.6)`;

    ctx.beginPath();
    ctx.arc(x, y, r + (isHi ? 2 : 0), 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();

    ctx.lineWidth = isHover || isHi ? 2 : 1;
    ctx.strokeStyle = stroke;
    ctx.stroke();

    const showLabel = st.scale >= 0.85 || isHover || isHi;
    if (showLabel) {
      const label = n.title || n.doi || n.id;
      ctx.font = "12px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif";
      ctx.fillStyle = st.colors.text;
      ctx.fillText(label, x + r + 6, y + 4);
    }
  }
}

function graphLoop() {
  const st = graphState;
  if (!st) return;
  if (!st.running) {
    st.rafId = null;
    return;
  }
  graphStep();
  graphRender();
  if (st.running) st.rafId = requestAnimationFrame(graphLoop);
  else st.rafId = null;
}

function graphNodeLabel(node) {
  if (!node) return "";
  return String(node.title || node.doi || node.id || "");
}

function graphCenterOnNode(node) {
  const st = graphState;
  if (!st || !node) return;
  st.panX = st.width / 2 - node.x * st.scale;
  st.panY = st.height / 2 - node.y * st.scale;
}

function graphZoomToFit(padding = 56) {
  const st = graphState;
  if (!st || !st.nodes || !st.nodes.length) return;

  const pad = Math.max(16, Number(padding) || 0);
  const availW = Math.max(40, st.width - pad * 2);
  const availH = Math.max(40, st.height - pad * 2);

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const n of st.nodes) {
    const r = (n.r || 0) + 10;
    minX = Math.min(minX, n.x - r);
    maxX = Math.max(maxX, n.x + r);
    minY = Math.min(minY, n.y - r);
    maxY = Math.max(maxY, n.y + r);
  }

  const w = maxX - minX;
  const h = maxY - minY;
  if (!(w > 0) || !(h > 0)) return;

  const nextScale = clamp(Math.min(availW / w, availH / h), 0.2, 3.5);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;

  st.scale = nextScale;
  st.panX = st.width / 2 - cx * nextScale;
  st.panY = st.height / 2 - cy * nextScale;
}

function graphCurrentFilter() {
  if (selectedFolderMode === "folder" && selectedFolderId) {
    const name = folderName(selectedFolderId) || "Folder";
    return { key: `folder:${selectedFolderId}`, label: `Folder: ${name}`, kind: "folder", folderId: selectedFolderId };
  }
  if (selectedFolderMode === "unfiled") {
    return { key: "unfiled", label: "Unfiled", kind: "unfiled", folderId: null };
  }
  return { key: "all", label: "All papers", kind: "all", folderId: null };
}

function graphFilterGraph(graph, filter) {
  const nodesIn = asArray(graph?.nodes);
  const edgesIn = asArray(graph?.edges);

  let nodes = nodesIn;
  if (filter?.kind === "folder" && filter.folderId) {
    nodes = nodesIn.filter((n) => n && n.folder_id === filter.folderId);
  } else if (filter?.kind === "unfiled") {
    nodes = nodesIn.filter((n) => n && !n.folder_id);
  }

  const allowed = new Set(nodes.map((n) => String(n.id || "")).filter(Boolean));
  const edges = edgesIn.filter((e) => {
    const a = String(e?.a_paper_id || "");
    const b = String(e?.b_paper_id || "");
    return allowed.has(a) && allowed.has(b);
  });

  return { nodes, edges };
}

function graphApplySearch(query, opts = {}) {
  const st = graphState;
  if (!st) return;
  const center = !!opts.center;
  const q = String(query || "").trim().toLowerCase();
  const prefix = st.filterLabel ? `${st.filterLabel} | ` : "";

  if (!q) {
    st.highlightId = selectedPaperId ? String(selectedPaperId) : null;
    if (graphStatus) graphStatus.textContent = `${prefix}${st.nodes.length} nodes | ${st.edges.length} edges`;
    return;
  }

  const match = st.nodes.find((n) => graphNodeLabel(n).toLowerCase().includes(q)) || null;
  st.highlightId = match ? match.id : null;
  if (match && center) graphCenterOnNode(match);

  if (graphStatus) {
    graphStatus.textContent = match
      ? `${prefix}${st.nodes.length} nodes | ${st.edges.length} edges | 1 match`
      : `${prefix}${st.nodes.length} nodes | ${st.edges.length} edges | no match`;
  }
}

async function openGraph() {
  if (!graphOverlay) return;
  closePaperMenu();
  closeRecs();

  const st = ensureGraphState();
  if (!st) return;
  const filter = graphCurrentFilter();
  st.filterLabel = filter.label;
  if (st.lastFilterKey !== filter.key) st.userInteracted = false;
  st.lastFilterKey = filter.key;

  graphOverlay.classList.remove("hidden");
  document.body.classList.add("graph-open");
  window.addEventListener("resize", onGraphResize);
  window.addEventListener("keydown", onGraphKeydown, true);
  onGraphResize();

  if (graphStatus) graphStatus.textContent = "Loading...";
  try {
    const g = await api("/api/graph");
    const filtered = graphFilterGraph(g, filter);
    graphSetData(filtered);
    if (!st.userInteracted) graphZoomToFit();
    graphApplySearch(graphSearch ? graphSearch.value : "", { center: false });
  } catch (e) {
    toast(String(e.message || e), "error", 6500);
    if (graphStatus) graphStatus.textContent = "Failed to load graph.";
  }

  st.running = true;
  if (!st.rafId) st.rafId = requestAnimationFrame(graphLoop);
  if (graphSearch) graphSearch.focus();
}

async function refreshSession() {
  const s = await api("/api/session");
  authEnabled = !!s.auth_enabled;

  if (!authEnabled) {
    hide(loginSection);
    show(appSection);
    hide(logoutBtn);
    if (graphBtn) show(graphBtn);
    if (recsBtn && latestRecs) show(recsBtn);
    return;
  }

  if (!s.authenticated) {
    show(loginSection);
    hide(appSection);
    hide(logoutBtn);
    if (graphBtn) hide(graphBtn);
    if (recsBtn) hide(recsBtn);
    closeRecs();
    return;
  }

  hide(loginSection);
  show(appSection);
  show(logoutBtn);
  if (graphBtn) show(graphBtn);
  if (recsBtn && latestRecs) show(recsBtn);
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
    await refreshFolders();
    await refreshPapers();
  } catch (e) {
    setText(loginError, String(e.message || e));
  }
}

async function logout() {
  closeGraph();
  closeRecs();
  stopPolling();
  await api("/api/session", { method: "DELETE" });
  selectedPaperId = null;
  await refreshSession();
}

function paperFilterKey(q) {
  const folderKey =
    selectedFolderMode === "folder" && selectedFolderId ? `folder:${selectedFolderId}` : selectedFolderMode;
  return `${folderKey}|${selectedPaperStatusFilter}|${q || ""}`;
}

function renderPaperPager(startIndex, endIndexExclusive, total) {
  if (!paperPrevBtn || !paperNextBtn || !paperPageInfo) return;

  const pages = total ? Math.ceil(total / PAPER_PAGE_SIZE) : 0;
  const page = pages ? paperPageIndex + 1 : 0;

  paperPrevBtn.disabled = !pages || paperPageIndex <= 0;
  paperNextBtn.disabled = !pages || paperPageIndex >= pages - 1;

  if (!total) {
    paperPageInfo.textContent = "";
    return;
  }

  const from = startIndex + 1;
  const to = Math.min(total, endIndexExclusive);
  paperPageInfo.textContent = `${from}-${to} / ${total} (page ${page}/${pages})`;
}

function renderPapersPaged(items) {
  paperFilteredCache = items;
  const total = items.length;
  const pages = total ? Math.ceil(total / PAPER_PAGE_SIZE) : 0;

  if (!pages) {
    paperPageIndex = 0;
    renderPaperPager(0, 0, 0);
    renderPapers([]);
    return;
  }

  paperPageIndex = clamp(paperPageIndex, 0, pages - 1);
  const start = paperPageIndex * PAPER_PAGE_SIZE;
  const end = start + PAPER_PAGE_SIZE;

  renderPaperPager(start, end, total);
  renderPapers(items.slice(start, end));
}

function applyPapersFilter() {
  const q = (paperSearch && paperSearch.value ? paperSearch.value : "").trim().toLowerCase();
  const key = paperFilterKey(q);
  if (key !== lastPaperFilterKey) {
    paperPageIndex = 0;
    lastPaperFilterKey = key;
  }

  const folderScoped =
    selectedFolderMode === "unfiled"
      ? paperSummaries.filter((x) => !x.paper?.folder_id)
      : selectedFolderMode === "folder" && selectedFolderId
        ? paperSummaries.filter((x) => x.paper?.folder_id === selectedFolderId)
        : paperSummaries;

  const scoped =
    selectedPaperStatusFilter === "read"
      ? folderScoped.filter((x) => (x.paper?.status || "to_read") === "done")
      : selectedPaperStatusFilter === "unread"
        ? folderScoped.filter((x) => (x.paper?.status || "to_read") !== "done")
        : folderScoped;

  const filtered = !q
    ? scoped
    : scoped.filter((item) => {
        const p = item.paper || {};
        const title = normalizeTitle(item);
        const folder = folderName(p.folder_id) || "";
        const hay = `${title} ${p.doi || ""} ${p.drive_file_id || ""} ${p.id || ""} ${folder} ${p.memo || ""}`.toLowerCase();
        return hay.includes(q);
      });

  if (selectedPaperId !== lastPagerSelectedPaperId) {
    lastPagerSelectedPaperId = selectedPaperId;
    if (selectedPaperId) {
      const idx = filtered.findIndex((x) => x && x.paper && x.paper.id === selectedPaperId);
      if (idx >= 0) paperPageIndex = Math.floor(idx / PAPER_PAGE_SIZE);
    }
  }

  if (paperCount) {
    const scopeLabel =
      selectedFolderMode === "all"
        ? "All papers"
        : selectedFolderMode === "unfiled"
          ? "Unfiled"
          : folderName(selectedFolderId) || "Folder";
    const statusLabel =
      selectedPaperStatusFilter === "read"
        ? "읽음"
        : selectedPaperStatusFilter === "unread"
          ? "아직 안 읽음"
          : null;
    const text = q ? `${filtered.length} / ${scoped.length}` : `${scoped.length}`;
    paperCount.textContent = `${text} papers • ${scopeLabel}${statusLabel ? ` • ${statusLabel}` : ""}`;
  }
  renderPapersPaged(filtered);
}

async function refreshPapers() {
  const items = await api("/api/papers/summary");
  paperSummaries = items;
  paperById = new Map(items.map((x) => [x.paper?.id, x.paper]).filter((kv) => kv[0]));
  renderFolders();
  applyPapersFilter();
}

function clearStructuredViews() {
  overviewView.replaceChildren();
  personaTabs.replaceChildren();
  personaContent.replaceChildren();
  normalizedTabs.replaceChildren();
  normalizedContent.replaceChildren();
  diagnosticsView.replaceChildren();
  if (jsonEditor) jsonEditor.value = "";
  setLogPanel(jsonLogsPanel, jsonLogs, null);
  overviewCtx = null;
}

function applyDetailPayload(d, paperId) {
  currentDetail = d;
  if (jsonDraftPaperId !== paperId) resetJsonDrafts(paperId);
  const run = d.latest_run;
  const runStatus = run?.status || "-";

  const paper = d.paper;
  const title = (paper?.title || "").trim() || (paper?.doi || "").trim() || "Details";
  setText(detailTitle, title);

  const metaParts = [];
  if (paper?.doi && paper?.title) metaParts.push(`doi: ${paper.doi}`);
  const folder = folderName(paper?.folder_id);
  metaParts.push(folder ? `folder: ${folder}` : "unfiled");
  setText(detailMeta, metaParts.join(" • "));

  renderPaperControls(d.paper);
  setText(detailError, run?.error || "");

  const busy = runStatus === "queued" || runStatus === "running";
  if (analyzeBtn && selectedPaperId === paperId) {
    analyzeBtn.textContent = busy ? "Analyzing..." : "Analyze";
    analyzeBtn.disabled = busy;
  }

  renderDetailOutput(d);

  return runStatus;
}

async function loadDetails(paperId) {
  stopPolling();
  setText(detailError, "");
  setText(mdView, "");
  if (jsonEditor) jsonEditor.value = "";
  setLogPanel(jsonLogsPanel, jsonLogs, null);
  clearStructuredViews();
  if (analyzeBtn) analyzeBtn.disabled = !paperId;
  lastDetailOutputKey = null;

  if (!paperId) {
    currentDetail = null;
    resetJsonDrafts(null);
    setText(detailTitle, "Details");
    setText(detailMeta, "");
    if (paperControls) paperControls.replaceChildren();
    if (analyzeBtn) analyzeBtn.textContent = "Analyze";
    switchDetailTab("overview");
    return;
  }

  const d = await api(`/api/papers/${paperId}`);
  applyDetailPayload(d, paperId);
}

async function saveCurrentJson() {
  const paperId = currentDetail?.paper?.id;
  if (!paperId) {
    toast("Select a paper first.", "error");
    return;
  }
  const langKey = currentJsonLangKey();
  switchDetailTab("json");

  const raw = (jsonEditor?.value || "").trim();
  if (!raw) {
    setLogPanel(jsonLogsPanel, jsonLogs, ["JSON is empty."]);
    toast("JSON is empty.", "error");
    return;
  }

  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    setLogPanel(jsonLogsPanel, jsonLogs, [`Invalid JSON: ${e.message || e}`]);
    toast("Invalid JSON.", "error", 6500);
    return;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    setLogPanel(jsonLogsPanel, jsonLogs, ["JSON must be an object."]);
    toast("JSON must be an object.", "error");
    return;
  }

  if (jsonSaveBtn) {
    jsonSaveBtn.disabled = true;
    jsonSaveBtn.textContent = "Saving...";
  }
  setLogPanel(jsonLogsPanel, jsonLogs, [`Saving ${langKey} JSON...`]);

  try {
    const res = await api(`/api/papers/${paperId}/analysis-json`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang: langKey, json: parsed }),
    });
    const logs = res && Array.isArray(res.logs) ? res.logs : [];
    if (res && res.ok === false) {
      setLogPanel(jsonLogsPanel, jsonLogs, logs.length ? logs : [res.error || "Save failed."]);
      toast(res.error || "Save failed.", "error", 6500);
      return;
    }

    jsonDirtyByLang[langKey] = false;
    jsonDraftByLang[langKey] = JSON.stringify(parsed, null, 2);

    toast("Saved.", "success");
    await loadDetails(paperId);
    setLogPanel(jsonLogsPanel, jsonLogs, logs);
  } catch (e) {
    setLogPanel(jsonLogsPanel, jsonLogs, [`Error: ${e.message || e}`]);
    toast(String(e.message || e), "error", 6500);
  } finally {
    if (jsonSaveBtn) {
      jsonSaveBtn.disabled = false;
      jsonSaveBtn.textContent = "저장";
    }
  }
}

async function startPolling(paperId) {
  stopPolling();
  show(stopPollBtn);
  pollHandle = setInterval(async () => {
    try {
      const d = await api(`/api/papers/${paperId}`);
      const runStatus = applyDetailPayload(d, paperId);
      if (runStatus !== "queued" && runStatus !== "running") stopPolling();
      await refreshPapers();
    } catch (e) {
      console.warn("poll failed:", e);
    }
  }, 3000);
}

async function enqueueAnalyze() {
  if (!selectedPaperId) return;
  const ok = confirm("Analyze this paper now?");
  if (!ok) return;
  setText(detailError, "");
  if (analyzeBtn) {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyzing...";
  }
  await api(`/api/papers/${selectedPaperId}/analyze`, { method: "POST" });
  toast("Queued analysis.", "info");
  await loadDetails(selectedPaperId);
  await startPolling(selectedPaperId);
}

async function createPaper() {
  createBtn.disabled = true;
  setText(createStatus, "Working...");
  const jsonText = (analysisJsonText && analysisJsonText.value ? analysisJsonText.value : "").trim();
  const jsonFile =
    analysisJsonFileInput.files && analysisJsonFileInput.files[0] ? analysisJsonFileInput.files[0] : null;
  try {
    const doi = doiInput ? doiInput.value.trim() || null : null;
    const title = titleInput ? titleInput.value.trim() || null : null;
    const driveFileId = driveFileIdInput ? driveFileIdInput.value.trim() || null : null;
    const file =
      pdfFileInput && pdfFileInput.files && pdfFileInput.files[0] ? pdfFileInput.files[0] : null;
    const folderId = currentFolderForNewPaper();

    if (!jsonText && !jsonFile && !file && !driveFileId && !doi) {
      toast("Provide PDF, Drive file id, DOI, or analysis JSON.", "error", 5000);
      setText(createStatus, "Error: missing input");
      return;
    }

    let paper = null;
    if (jsonText) {
      const parsed = parseJsonLoose(jsonText);
      const params = new URLSearchParams({
        drive_file_id: driveFileId || "",
        doi: doi || "",
        title: title || "",
      });
      if (folderId) params.set("folder_id", folderId);
      paper = await api(
        `/api/papers/import-json?${params.toString()}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed),
        },
      );
    } else if (jsonFile) {
      const parsed = parseJsonLoose(await jsonFile.text());
      const params = new URLSearchParams({
        drive_file_id: driveFileId || "",
        doi: doi || "",
        title: title || "",
      });
      if (folderId) params.set("folder_id", folderId);
      paper = await api(
        `/api/papers/import-json?${params.toString()}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed),
        },
      );
    } else if (file) {
      const params = new URLSearchParams({ doi: doi || "", title: title || "" });
      if (folderId) params.set("folder_id", folderId);
      paper = await api(
        `/api/papers/upload?${params.toString()}`,
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
        body: JSON.stringify({ drive_file_id: driveFileId, doi, title, folder_id: folderId }),
      });
    }

    selectedPaperId = paper.id;
    if (pdfFileInput) pdfFileInput.value = "";
    if (driveFileIdInput) driveFileIdInput.value = "";
    if (doiInput) doiInput.value = "";
    if (titleInput) titleInput.value = "";
    analysisJsonFileInput.value = "";
    if (analysisJsonText) analysisJsonText.value = "";
    setText(createStatus, "OK");
    toast("Created.", "success");
    closeNewPaperDrawer();
    await refreshPapers();
    await loadDetails(selectedPaperId);
  } catch (e) {
    const msg = String(e.message || e);
    setText(createStatus, `Error: ${msg}`);
    toast(msg, "error", 6500);
  } finally {
    createBtn.disabled = false;
    setTimeout(() => setText(createStatus, ""), 3000);
  }
}

async function main() {
  initTheme();
  initDetailTabs();
  setJsonLang(selectedJsonLang);
  setRecsLang(selectedRecsLang);
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      setTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

  loginBtn.addEventListener("click", login);
  usernameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") login();
  });
  passwordInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") login();
  });
  logoutBtn.addEventListener("click", logout);
  if (recsBtn) recsBtn.addEventListener("click", openRecs);
  if (recsCloseBtn) recsCloseBtn.addEventListener("click", closeRecs);
  if (recsRunBtn) recsRunBtn.addEventListener("click", startRecsTask);
  if (recsLogsBtn) recsLogsBtn.addEventListener("click", toggleRecsLogs);
  if (recsRefreshBtn) recsRefreshBtn.addEventListener("click", () => refreshRecommendations());
  if (recsLangOriginal) recsLangOriginal.addEventListener("click", () => setRecsLang("original"));
  if (recsLangKorean) recsLangKorean.addEventListener("click", () => setRecsLang("ko"));
  if (recsTranslateBtn) recsTranslateBtn.addEventListener("click", translateRecommendations);
  if (graphBtn) graphBtn.addEventListener("click", openGraph);
  if (graphCloseBtn) graphCloseBtn.addEventListener("click", closeGraph);
  if (graphSearch) {
    graphSearch.addEventListener("input", () => {
      graphApplySearch(graphSearch.value, { center: false });
    });
    graphSearch.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        graphApplySearch(graphSearch.value, { center: true });
      }
    });
  }

  if (analysisJsonClearBtn) {
    analysisJsonClearBtn.addEventListener("click", () => {
      if (analysisJsonText) analysisJsonText.value = "";
      toast("Cleared.", "info");
    });
  }

  if (newPaperBtn) newPaperBtn.addEventListener("click", openNewPaperDrawer);
  if (newPaperCloseBtn) newPaperCloseBtn.addEventListener("click", closeNewPaperDrawer);
  if (newPaperDrawer) {
    newPaperDrawer.addEventListener("click", (e) => {
      if (e.target === newPaperDrawer) closeNewPaperDrawer();
    });
  }

  if (jsonLangOriginal) jsonLangOriginal.addEventListener("click", () => setJsonLang("original"));
  if (jsonLangKorean) jsonLangKorean.addEventListener("click", () => setJsonLang("ko"));
  if (jsonEditor) {
    jsonEditor.addEventListener("input", () => {
      const key = currentJsonLangKey();
      jsonDraftByLang[key] = jsonEditor.value;
      jsonDirtyByLang[key] = true;
    });
  }
  if (jsonSaveBtn) {
    jsonSaveBtn.addEventListener("click", (e) => {
      e.preventDefault();
      saveCurrentJson();
    });
  }
  if (jsonCopyBtn) {
    jsonCopyBtn.addEventListener("click", async () => {
      try {
        await copyToClipboard(jsonEditor ? jsonEditor.value : "");
        toast("Copied.", "success");
      } catch (e) {
        toast(String(e.message || e), "error", 6500);
      }
    });
  }

  createBtn.addEventListener("click", createPaper);
  if (newFolderBtn) newFolderBtn.addEventListener("click", createFolder);
  refreshBtn.addEventListener("click", async () => {
    await refreshFolders();
    await refreshPapers();
    if (selectedPaperId) await loadDetails(selectedPaperId);
    await refreshRecommendations({ silent: true });
  });
  if (paperSearch) paperSearch.addEventListener("input", applyPapersFilter);
  if (paperStatusAll) paperStatusAll.addEventListener("click", () => setPaperStatusFilter("all"));
  if (paperStatusUnread) paperStatusUnread.addEventListener("click", () => setPaperStatusFilter("unread"));
  if (paperStatusRead) paperStatusRead.addEventListener("click", () => setPaperStatusFilter("read"));
  if (paperPrevBtn) {
    paperPrevBtn.addEventListener("click", () => {
      paperPageIndex -= 1;
      renderPapersPaged(paperFilteredCache);
    });
  }
  if (paperNextBtn) {
    paperNextBtn.addEventListener("click", () => {
      paperPageIndex += 1;
      renderPapersPaged(paperFilteredCache);
    });
  }
  if (analyzeBtn) analyzeBtn.addEventListener("click", enqueueAnalyze);
  stopPollBtn.addEventListener("click", stopPolling);

  await refreshSession();
  if (authEnabled && !loginSection.classList.contains("hidden")) return;
  await refreshFolders();
  await refreshPapers();
  await refreshRecommendations({ silent: true });
}

main().catch((e) => {
  console.error(e);
});
