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

let selectedPaperId = null;
let pollHandle = null;
let authEnabled = false;
let selectedDetailTab = "overview";
let selectedPersonaId = null;
let selectedNormalizedTab = "section_map";
let lastDetailOutputKey = null;

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

function renderOverview(canonical) {
  overviewView.replaceChildren();
  if (!canonical) {
    overviewView.appendChild(createEl("div", { className: "muted", text: "No analysis output yet." }));
    return;
  }

  const paper = canonical.paper || {};
  const meta = paper.metadata || {};

  const title = meta.title || "(untitled)";
  overviewView.appendChild(createEl("div", { className: "overview-title", text: title }));

  const kv = createEl("div", { className: "kv" });
  const authors = asArray(meta.authors)
    .map((a) => {
      const name = (a && a.name) || "";
      const aff = (a && a.affiliation) || "";
      if (!name) return null;
      return aff ? `${name} (${aff})` : name;
    })
    .filter(Boolean)
    .join(", ");

  kv.appendChild(kvRow("Authors", authors || "-"));
  kv.appendChild(kvRow("Year", meta.year ? String(meta.year) : "-"));
  kv.appendChild(kvRow("Venue", meta.venue || "-"));
  kv.appendChild(kvRow("DOI", doiLink(meta.doi || "")));
  kv.appendChild(kvRow("URL", safeLink(meta.url || "")));
  overviewView.appendChild(kv);

  if (paper.abstract) {
    const abs = createEl("div", { className: "section" });
    abs.appendChild(createEl("div", { className: "section-title", text: "Abstract" }));
    abs.appendChild(createEl("div", { className: "prose", text: paper.abstract }));
    overviewView.appendChild(abs);
  }

  const final = canonical.final_synthesis || {};
  const sec = createEl("div", { className: "section" });
  sec.appendChild(createEl("div", { className: "section-title", text: "Final synthesis" }));

  if (final.one_liner) sec.appendChild(createEl("div", { className: "one-liner", text: final.one_liner }));

  const rating = final.suggested_rating || {};
  const ratingRow = createEl("div", { className: "row" });
  ratingRow.appendChild(pill(`Overall ${rating.overall ?? "-"}/5`, "primary"));
  ratingRow.appendChild(pill(`Confidence ${fmtPercent(rating.confidence)}`, "muted"));
  sec.appendChild(ratingRow);

  const strengths = asArray(final.strengths);
  if (strengths.length) {
    sec.appendChild(createEl("div", { className: "section-subtitle", text: "Strengths" }));
    sec.appendChild(renderBullets(strengths));
  }

  const weaknesses = asArray(final.weaknesses);
  if (weaknesses.length) {
    sec.appendChild(createEl("div", { className: "section-subtitle", text: "Weaknesses" }));
    sec.appendChild(renderBullets(weaknesses));
  }

  const who = asArray(final.who_should_read);
  if (who.length) {
    sec.appendChild(createEl("div", { className: "section-subtitle", text: "Who should read" }));
    sec.appendChild(renderBullets(who));
  }

  const ev = renderEvidenceBlock(final.evidence);
  if (ev) sec.appendChild(ev);
  overviewView.appendChild(sec);
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

  const questions = asArray(persona.questions_to_ask);
  const qs = createEl("div", { className: "section" });
  qs.appendChild(
    createEl("div", { className: "section-subtitle", text: `Questions to ask (${questions.length})` }),
  );
  if (!questions.length) {
    qs.appendChild(createEl("div", { className: "muted", text: "No questions." }));
  } else {
    for (const q of questions) {
      const item = createEl("div", { className: "item" });
      item.appendChild(createEl("div", { className: "item-text", text: q.q || "" }));
      const ev = renderEvidenceBlock(q.evidence);
      if (ev) item.appendChild(ev);
      qs.appendChild(item);
    }
  }
  personaContent.appendChild(qs);
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

async function renamePaper(paper) {
  const current = paper.title || "";
  const value = prompt("Rename paper (title)", current);
  if (value === null) return;
  const next = value.trim();
  if (!next) {
    alert("Title cannot be empty.");
    return;
  }
  await api(`/api/papers/${paper.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: next }),
  });
  await refreshPapers();
  if (selectedPaperId === paper.id) await loadDetails(selectedPaperId);
}

async function deletePaper(paper) {
  const label = paper.title || paper.doi || paper.id;
  const ok = confirm(`Delete this paper?\n\n${label}`);
  if (!ok) return;
  stopPolling();
  await api(`/api/papers/${paper.id}`, { method: "DELETE" });
  if (selectedPaperId === paper.id) selectedPaperId = null;
  await refreshPapers();
  await loadDetails(selectedPaperId);
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

    const actions = document.createElement("div");
    actions.className = "row";
    actions.style.marginTop = "6px";

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.className = "btn btn-secondary btn-small";
    renameBtn.textContent = "Rename";
    renameBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await renamePaper(item.paper);
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn btn-danger btn-small";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await deletePaper(item.paper);
    });

    actions.appendChild(renameBtn);
    actions.appendChild(deleteBtn);

    div.appendChild(title);
    div.appendChild(meta);
    div.appendChild(badge);
    div.appendChild(actions);

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

function clearStructuredViews() {
  overviewView.replaceChildren();
  personaTabs.replaceChildren();
  personaContent.replaceChildren();
  normalizedTabs.replaceChildren();
  normalizedContent.replaceChildren();
  diagnosticsView.replaceChildren();
}

function applyDetailPayload(d, paperId) {
  const run = d.latest_run;
  const runStatus = run?.status || "-";
  const title = d.paper?.title || d.paper?.doi || "";
  const head = title ? `${title}  •  ` : "";
  setText(detailMeta, `${head}paper_id=${paperId}  •  run=${runStatus}`);
  setText(detailError, run?.error || "");
  setText(mdView, d.latest_content_md || "");

  const outKey = d.latest_output ? JSON.stringify(d.latest_output) : "";
  if (outKey !== lastDetailOutputKey) {
    lastDetailOutputKey = outKey;
    setText(jsonView, d.latest_output ? JSON.stringify(d.latest_output, null, 2) : "");
    renderOverview(d.latest_output);
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
  analyzeBtn.disabled = !paperId;
  lastDetailOutputKey = null;

  if (!paperId) {
    setText(detailMeta, "");
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

async function main() {
  initDetailTabs();
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
