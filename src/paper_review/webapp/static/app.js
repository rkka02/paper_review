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
const paperSearch = $("paperSearch");
const paperCount = $("paperCount");
const foldersList = $("foldersList");
const papersList = $("papersList");

const analyzeBtn = $("analyzeBtn");
const stopPollBtn = $("stopPollBtn");
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
const jsonView = $("jsonView");

const graphBtn = $("graphBtn");
const graphOverlay = $("graphOverlay");
const graphCanvas = $("graphCanvas");
const graphCloseBtn = $("graphCloseBtn");
const graphSearch = $("graphSearch");
const graphStatus = $("graphStatus");

let selectedPaperId = null;
let pollHandle = null;
let authEnabled = false;
let paperSummaries = [];
let paperById = new Map();
let folders = [];
let folderById = new Map();
let selectedFolderMode = "all"; // all | unfiled | folder
let selectedFolderId = null;
let selectedDetailTab = "overview";
let selectedPersonaId = null;
let selectedNormalizedTab = "section_map";
let lastDetailOutputKey = null;
let currentDetail = null;
let overviewCtx = null;
let paperMenuEl = null;
let paperMenuToken = null;
let graphState = null;

function show(el) {
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function setText(el, text) {
  el.textContent = text ?? "";
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
    line.appendChild(createEl("span", { className: "author-name", text: it.name }));
    if (it.affiliation) line.appendChild(createEl("span", { className: "author-aff", text: it.affiliation }));
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
    json: jsonView,
  };
  for (const [k, el] of Object.entries(views)) {
    if (!el) continue;
    if (k === tab) show(el);
    else hide(el);
  }
  const tabs = document.querySelectorAll("#detailTabs .tab");
  for (const t of tabs) t.classList.toggle("active", t.getAttribute("data-tab") === tab);
}

function initDetailTabs() {
  const tabs = document.querySelectorAll("#detailTabs .tab");
  for (const t of tabs) {
    t.addEventListener("click", () => {
      switchDetailTab(t.getAttribute("data-tab"));
    });
  }
  switchDetailTab(selectedDetailTab);
}

function renderOverview(detail, outputKey) {
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
        const hay = `${title} ${p.doi || ""} ${p.id || ""} ${folder}`.toLowerCase();
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
              renderOverview(currentDetail, overviewCtx.outputKey || "");
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

  const canonicalOut = detail.latest_output;
  const canonicalPaper = canonicalOut?.paper || {};
  const canonicalMeta = canonicalPaper.metadata || {};
  const displayTitle =
    paperOut.title || canonicalMeta.title || paperOut.doi || paperOut.drive_file_id || paperOut.id || "(untitled)";
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
    overviewCtx.kvEl.appendChild(kvRow("Authors", canonicalOut ? renderAuthors(canonicalMeta.authors) : "-"));
    overviewCtx.kvEl.appendChild(kvRow("Year", canonicalOut && canonicalMeta.year ? String(canonicalMeta.year) : "-"));
    overviewCtx.kvEl.appendChild(kvRow("Venue", canonicalOut ? canonicalMeta.venue || "-" : "-"));
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
      overviewCtx.absHost.appendChild(createEl("div", { className: "muted", text: "No analysis output yet." }));
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
          renderOverview(currentDetail, overviewCtx.outputKey || "");
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

function renderPersonas(canonical) {
  personaTabs.replaceChildren();
  personaContent.replaceChildren();
  if (!canonical) {
    personaContent.appendChild(createEl("div", { className: "muted", text: "No analysis output yet." }));
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
      renderPersonas(canonical);
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

function renderNormalized(canonical) {
  normalizedTabs.replaceChildren();
  normalizedContent.replaceChildren();
  if (!canonical) {
    normalizedContent.appendChild(createEl("div", { className: "muted", text: "No analysis output yet." }));
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
      renderNormalized(canonical);
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

function renderDiagnostics(canonical) {
  diagnosticsView.replaceChildren();
  if (!canonical) {
    diagnosticsView.appendChild(createEl("div", { className: "muted", text: "No analysis output yet." }));
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

  const folderSelect = createEl("select", { className: "select", attrs: { "aria-label": "Folder" } });
  folderSelect.appendChild(createEl("option", { text: "Unfiled", attrs: { value: "" } }));
  for (const { folder, depth } of folderTreeRows()) {
    const indent = depth ? `${"  ".repeat(depth)}` : "";
    folderSelect.appendChild(
      createEl("option", { text: `${indent}${folder.name}`, attrs: { value: folder.id } }),
    );
  }
  folderSelect.value = paper.folder_id || "";
  folderSelect.addEventListener("change", async (e) => {
    e.preventDefault();
    const next = folderSelect.value || null;
    await setPaperFolder(paper.id, next);
  });

  paperControls.appendChild(folderSelect);
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
    metaParts.push(`status: ${p.status || "-"}`);
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
  if (graphState) graphState.running = false;
  window.removeEventListener("resize", onGraphResize);
  window.removeEventListener("keydown", onGraphKeydown, true);
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
    dragging: false,
    dragMode: null,
    dragNode: null,
    dragStartX: 0,
    dragStartY: 0,
    dragPanX: 0,
    dragPanY: 0,
    dragNodeOffsetX: 0,
    dragNodeOffsetY: 0,
    moved: false,
    hoverId: null,
    highlightId: null,
    rafId: null,
    running: false,
    colors: graphCssColors(),
    theme: currentTheme(),
  };

  const screenToWorld = (sx, sy) => {
    const st = graphState;
    return { x: (sx - st.panX) / st.scale, y: (sy - st.panY) / st.scale };
  };

  const pickNode = (sx, sy) => {
    const st = graphState;
    let best = null;
    let bestD2 = Infinity;
    for (const n of st.nodes) {
      const px = n.x * st.scale + st.panX;
      const py = n.y * st.scale + st.panY;
      const r = Math.max(6, Math.min(26, n.r * st.scale));
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

  const onDown = (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;
    const rect = st.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const hit = pickNode(sx, sy);
    st.dragging = true;
    st.moved = false;
    st.dragStartX = sx;
    st.dragStartY = sy;
    st.dragPanX = st.panX;
    st.dragPanY = st.panY;
    if (hit) {
      st.dragMode = "node";
      st.dragNode = hit;
      const w = screenToWorld(sx, sy);
      st.dragNodeOffsetX = hit.x - w.x;
      st.dragNodeOffsetY = hit.y - w.y;
    } else {
      st.dragMode = "pan";
      st.dragNode = null;
      graphOverlay.classList.add("dragging");
    }
    e.preventDefault();
  };

  const onMove = (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;
    const rect = st.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (st.dragging) {
      const dx = sx - st.dragStartX;
      const dy = sy - st.dragStartY;
      if (Math.abs(dx) + Math.abs(dy) > 2) st.moved = true;

      if (st.dragMode === "pan") {
        st.panX = st.dragPanX + dx;
        st.panY = st.dragPanY + dy;
      } else if (st.dragMode === "node" && st.dragNode) {
        const w = screenToWorld(sx, sy);
        st.dragNode.x = w.x + st.dragNodeOffsetX;
        st.dragNode.y = w.y + st.dragNodeOffsetY;
        st.dragNode.vx = 0;
        st.dragNode.vy = 0;
      }
      return;
    }

    const hit = pickNode(sx, sy);
    st.hoverId = hit ? hit.id : null;
    st.canvas.style.cursor = hit ? "pointer" : "grab";
  };

  const onUp = async (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;
    const wasDraggingNode = st.dragMode === "node" && st.dragNode;
    const clickedNode = wasDraggingNode && !st.moved ? st.dragNode : null;

    st.dragging = false;
    st.dragMode = null;
    st.dragNode = null;
    graphOverlay.classList.remove("dragging");

    if (clickedNode) {
      closeGraph();
      selectedPaperId = clickedNode.id;
      applyPapersFilter();
      await loadDetails(clickedNode.id);
    }
  };

  const onWheel = (e) => {
    if (!isGraphOpen()) return;
    const st = graphState;
    const rect = st.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const delta = Math.max(-120, Math.min(120, e.deltaY));
    const factor = delta < 0 ? 1.12 : 1 / 1.12;

    const wx = (sx - st.panX) / st.scale;
    const wy = (sy - st.panY) / st.scale;
    const nextScale = Math.max(0.2, Math.min(3.5, st.scale * factor));
    st.scale = nextScale;
    st.panX = sx - wx * st.scale;
    st.panY = sy - wy * st.scale;
    e.preventDefault();
  };

  graphCanvas.addEventListener("mousedown", onDown);
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
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

  if (!st.panX && !st.panY) {
    st.panX = rect.width / 2;
    st.panY = rect.height / 2;
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
    const baseR = 6 + Math.sqrt(d) * 2.2;
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

  if (graphStatus) graphStatus.textContent = `${nodes.length} nodes · ${edges.length} edges`;
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
    const r = Math.max(5, Math.min(22, n.r * st.scale));
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

function graphApplySearch(query, opts = {}) {
  const st = graphState;
  if (!st) return;
  const center = !!opts.center;
  const q = String(query || "").trim().toLowerCase();

  if (!q) {
    st.highlightId = selectedPaperId ? String(selectedPaperId) : null;
    if (graphStatus) graphStatus.textContent = `${st.nodes.length} nodes · ${st.edges.length} edges`;
    return;
  }

  const match = st.nodes.find((n) => graphNodeLabel(n).toLowerCase().includes(q)) || null;
  st.highlightId = match ? match.id : null;
  if (match && center) graphCenterOnNode(match);

  if (graphStatus) {
    graphStatus.textContent = match
      ? `${st.nodes.length} nodes · ${st.edges.length} edges · 1 match`
      : `${st.nodes.length} nodes · ${st.edges.length} edges · no match`;
  }
}

async function openGraph() {
  if (!graphOverlay) return;
  closePaperMenu();

  const st = ensureGraphState();
  if (!st) return;

  graphOverlay.classList.remove("hidden");
  document.body.classList.add("graph-open");
  window.addEventListener("resize", onGraphResize);
  window.addEventListener("keydown", onGraphKeydown, true);
  onGraphResize();

  if (graphStatus) graphStatus.textContent = "Loading...";
  try {
    const g = await api("/api/graph");
    graphSetData(g);
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
    return;
  }

  if (!s.authenticated) {
    show(loginSection);
    hide(appSection);
    hide(logoutBtn);
    if (graphBtn) hide(graphBtn);
    return;
  }

  hide(loginSection);
  show(appSection);
  show(logoutBtn);
  if (graphBtn) show(graphBtn);
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
  stopPolling();
  await api("/api/session", { method: "DELETE" });
  selectedPaperId = null;
  await refreshSession();
}

function applyPapersFilter() {
  const q = (paperSearch && paperSearch.value ? paperSearch.value : "").trim().toLowerCase();

  const scoped =
    selectedFolderMode === "unfiled"
      ? paperSummaries.filter((x) => !x.paper?.folder_id)
      : selectedFolderMode === "folder" && selectedFolderId
        ? paperSummaries.filter((x) => x.paper?.folder_id === selectedFolderId)
        : paperSummaries;

  const filtered = !q
    ? scoped
    : scoped.filter((item) => {
        const p = item.paper || {};
        const title = normalizeTitle(item);
        const folder = folderName(p.folder_id) || "";
        const hay = `${title} ${p.doi || ""} ${p.drive_file_id || ""} ${p.id || ""} ${folder}`.toLowerCase();
        return hay.includes(q);
      });

  if (paperCount) {
    const scopeLabel =
      selectedFolderMode === "all"
        ? "All papers"
        : selectedFolderMode === "unfiled"
          ? "Unfiled"
          : folderName(selectedFolderId) || "Folder";
    const text = q ? `${filtered.length} / ${scoped.length}` : `${scoped.length}`;
    paperCount.textContent = `${text} papers • ${scopeLabel}`;
  }
  renderPapers(filtered);
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
  overviewCtx = null;
}

function applyDetailPayload(d, paperId) {
  currentDetail = d;
  const run = d.latest_run;
  const runStatus = run?.status || "-";
  const title = d.paper?.title || d.paper?.doi || "";
  const head = title ? `${title}  •  ` : "";
  setText(detailMeta, `${head}paper_id=${paperId}  •  run=${runStatus}`);
  renderPaperControls(d.paper);
  setText(detailError, run?.error || "");
  setText(mdView, d.latest_content_md || "");

  const busy = runStatus === "queued" || runStatus === "running";
  if (analyzeBtn && selectedPaperId === paperId) {
    analyzeBtn.textContent = busy ? "Analyzing..." : "Analyze";
    analyzeBtn.disabled = busy;
  }

  const outKey = d.latest_output ? JSON.stringify(d.latest_output) : "";
  renderOverview(d, outKey);
  if (outKey !== lastDetailOutputKey) {
    lastDetailOutputKey = outKey;
    setText(jsonView, d.latest_output ? JSON.stringify(d.latest_output, null, 2) : "");
    renderPersonas(d.latest_output);
    renderNormalized(d.latest_output);
    renderDiagnostics(d.latest_output);
  }

  return runStatus;
}

async function loadDetails(paperId) {
  stopPolling();
  setText(detailError, "");
  setText(mdView, "");
  setText(jsonView, "");
  clearStructuredViews();
  if (analyzeBtn) analyzeBtn.disabled = !paperId;
  lastDetailOutputKey = null;

  if (!paperId) {
    setText(detailMeta, "");
    if (paperControls) paperControls.replaceChildren();
    if (analyzeBtn) analyzeBtn.textContent = "Analyze";
    switchDetailTab("overview");
    return;
  }

  const d = await api(`/api/papers/${paperId}`);
  applyDetailPayload(d, paperId);
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

  createBtn.addEventListener("click", createPaper);
  if (newFolderBtn) newFolderBtn.addEventListener("click", createFolder);
  refreshBtn.addEventListener("click", async () => {
    await refreshFolders();
    await refreshPapers();
    if (selectedPaperId) await loadDetails(selectedPaperId);
  });
  if (paperSearch) paperSearch.addEventListener("input", applyPapersFilter);
  if (analyzeBtn) analyzeBtn.addEventListener("click", enqueueAnalyze);
  stopPollBtn.addEventListener("click", stopPolling);

  await refreshSession();
  if (authEnabled && !loginSection.classList.contains("hidden")) return;
  await refreshFolders();
  await refreshPapers();
}

main().catch((e) => {
  console.error(e);
});
