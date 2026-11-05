// Summary Record Generator: browser app. Builds the .docx in the browser (JSZip) and previews it (docx-preview).
// ITU Space Explorer data comes through the Vercel function /api/itu.
import {
  BANDS, DEFAULT_SS_TYPES, SS_CHOICES, buildContent, draftConclusion, draftDiscussion, fmtPos, netLon,
  parseNetworks, readAgendaRows,
} from "./core.js";
import { buildDocx } from "./docx.js";

const TEMPLATE_URL = "templates/Template_summary_record_INS-J_2026.docx";
const OPERATOR_NAMES = { BRI: "PT Bank Rakyat Indonesia (Persero), Tbk." };
const STORE_KEY = "sumrec-gen:v1";
const $ = (id) => document.getElementById(id);
const FIELDS = ["item_no", "ins_op", "ins_short", "j_op", "band_label", "ins_nets", "j_nets", "custom", "ific_label",
  "section_title", "item_title", "discussion", "conclusion"];

const state = {
  tpl: null, tplName: "", agenda: {}, itu: {}, excluded: new Set(),
  autoSection: true, autoItem: true, discEdited: false, blob: null, fileName: "summary-record.docx",
};

// ---------- small helpers ----------
const store = {
  load() { try { return JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch { return null; } },
  save(v) { try { localStorage.setItem(STORE_KEY, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};
const netsOf = (id) => parseNetworks($(id).value.replace(/\n/g, ", "));
const netsToText = (nets) => nets.map(([n, p]) => `${n} (${p})`).join("\n");
function status(msg, kind = "ok") { const el = $("ituStatus"); el.textContent = msg; el.className = "status " + kind; }
function chip(container, value, checked, onChange) {
  const l = document.createElement("label");
  l.className = "chip";
  const cb = document.createElement("input");
  cb.type = "checkbox"; cb.value = value; cb.checked = checked;
  cb.addEventListener("change", onChange);
  l.append(cb, document.createTextNode(value));
  container.append(l);
  return cb;
}
const checked = (id) => [...$(id).querySelectorAll("input:checked")].map((x) => x.value);
function customRanges() {
  return [...$("custom").value.matchAll(/([\d.]+)\s*-\s*([\d.]+)/g)].map((m) => [parseFloat(m[1]), parseFloat(m[2])]);
}

// ---------- input model ----------
function getInp() {
  const ins = netsOf("ins_nets"), js = netsOf("j_nets");
  const itemNo = $("item_no").value.trim();
  return {
    section_no: itemNo.split(".").slice(0, 2).join("."),
    section_title: $("section_title").value, item_no: itemNo, item_title: $("item_title").value,
    ins_nets: ins, j_nets: js, exclude: [...state.excluded].filter((n) => js.some(([x]) => x === n)),
    bands: checked("bands"), custom_ranges: customRanges(), ss_types: checked("ss"), list_mods: $("list_mods").checked,
    ific_label: $("ific_label").value.trim(), band_label: $("band_label").value.trim(),
    j_operator: $("j_op").value.trim(), ins_short: $("ins_short").value.trim(),
    discussion: $("discussion").value, conclusion: $("conclusion").value,
  };
}

function autoHeadings() {
  const inp = getInp();
  $("secLbl").textContent = `Heading ${inp.section_no || "2.x"}`;
  $("itemLbl").textContent = `Heading ${inp.item_no || "2.x.y"}`;
  const pos = (n, p) => fmtPos(netLon(n, p, state.itu));
  if (state.autoSection)
    $("section_title").value = `Coordination between ${$("ins_op").value.trim()} satellite network(s) and ${inp.j_operator} satellite network(s)`;
  if (state.autoItem) {
    const ex = new Set(inp.exclude);
    $("item_title").value = `Coordination between the ${inp.ins_nets.map(([n, p]) => `${n} (${pos(n, p)})`).join(", ")} ` +
      `satellite network and the ${inp.j_nets.filter(([n]) => !ex.has(n)).map(([n, p]) => `${n} (${pos(n, p)})`).join(", ")} ` +
      `satellite networks in the ${inp.band_label} band`;
  }
}

function redraft() {
  const inp = getInp();
  $("discussion").value = draftDiscussion(inp, state.itu);
  $("conclusion").value = draftConclusion(inp, state.itu);
  state.discEdited = false;
}

function renderExclusions() {
  const box = $("excl");
  box.innerHTML = "";
  const js = netsOf("j_nets");
  if (!js.length) { box.innerHTML = '<span class="hint">No Japanese networks yet.</span>'; return; }
  for (const [n] of js) chip(box, n, state.excluded.has(n), (e) => {
    e.target.checked ? state.excluded.add(n) : state.excluded.delete(n);
    autoHeadings(); schedule();
  });
}

function ituSummary() {
  const names = [...netsOf("ins_nets"), ...netsOf("j_nets")].map(([n]) => n);
  if (!names.length) { status(""); return; }
  const have = names.filter((n) => n in state.itu);
  const found = have.filter((n) => state.itu[n].found);
  const notFetched = names.filter((n) => !(n in state.itu));
  const notFound = have.filter((n) => !state.itu[n].found);
  if (!have.length) { status("No ITU data yet. Click Fetch from ITU Space Explorer.", "warn"); return; }
  let msg = `${found.length} of ${names.length} networks found in SNS.`;
  if (notFound.length) msg += ` Not in SNS: ${notFound.join(", ")}.`;
  if (notFetched.length) msg += ` Not fetched yet: ${notFetched.join(", ")}.`;
  status(msg, notFetched.length || notFound.length ? "warn" : "ok");
  $("saveItu").disabled = false;
}

// ---------- preview ----------
let timer = null, renderSeq = 0;
function schedule(delay = 450) { clearTimeout(timer); timer = setTimeout(render, delay); persist(); }

async function render() {
  const inp = getInp();
  const pane = $("previewPane"), msg = $("previewMsg");
  if (!state.tpl || !inp.ins_nets.length || !inp.j_nets.length) {
    msg.style.display = "grid"; $("preview").innerHTML = ""; $("download").disabled = true; return;
  }
  const seq = ++renderSeq;
  $("busy").style.display = "block";
  try {
    const content = buildContent(inp, state.itu);
    const blob = await buildDocx(window.JSZip, state.tpl, content);
    if (seq !== renderSeq) return;
    state.blob = blob;
    state.fileName = `Summary Record ${inp.item_no} ${inp.ins_nets.map(([n]) => n).join("-")} vs ` +
      `${inp.j_operator.replace(/\//g, "-")} ${inp.band_label}-band.docx`.replace(/\s+/g, " ");
    const top = pane.scrollTop;
    const holder = document.createElement("div");
    await window.docx.renderAsync(blob, holder, null, {
      inWrapper: true, ignoreLastRenderedPageBreak: true, breakPages: true, renderHeaders: true, renderFooters: true,
      experimental: true,
    });
    if (seq !== renderSeq) return;
    $("preview").replaceChildren(...holder.childNodes);
    pane.scrollTop = top;
    msg.style.display = "none";
    $("download").disabled = false;
  } catch (e) {
    console.error(e);
    msg.style.display = "grid"; msg.textContent = "Preview failed: " + e.message;
  } finally {
    if (seq === renderSeq) $("busy").style.display = "none";
  }
}

// ---------- persistence ----------
function persist() {
  const v = Object.fromEntries(FIELDS.map((f) => [f, $(f).value]));
  store.save({ ...v, bands: checked("bands"), ss: checked("ss"), list_mods: $("list_mods").checked,
    excluded: [...state.excluded], autoSection: state.autoSection, autoItem: state.autoItem, itu: state.itu });
}
function restore() {
  const v = store.load();
  if (!v) return false;
  for (const f of FIELDS) if (typeof v[f] === "string") $(f).value = v[f];
  for (const cb of $("bands").querySelectorAll("input")) cb.checked = (v.bands || []).includes(cb.value);
  if (v.ss) for (const cb of $("ss").querySelectorAll("input")) cb.checked = v.ss.includes(cb.value);
  $("list_mods").checked = !!v.list_mods;
  state.excluded = new Set(v.excluded || []);
  state.autoSection = v.autoSection !== false; state.autoItem = v.autoItem !== false;
  state.itu = v.itu || {};
  return true;
}

// ---------- template and agenda ----------
async function loadDefaultTemplate() {
  try {
    const r = await fetch(TEMPLATE_URL);
    if (!r.ok) throw new Error(r.status);
    state.tpl = await r.arrayBuffer();
    state.tplName = "Template_summary_record_INS-J_2026.docx";
  } catch {
    state.tplName = "not found, please upload one";
  }
  $("tplName").textContent = state.tplName;
}

function readWorkbook(buf) {
  const wb = window.XLSX.read(buf, { type: "array" });
  const sheets = {};
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    if (!ws["!ref"]) continue;
    const rg = window.XLSX.utils.decode_range(ws["!ref"]);
    const rows = [];
    for (let r = rg.s.r; r <= rg.e.r; r++) {
      const row = [];
      for (let c = 0; c <= Math.max(rg.e.c, 13); c++) {
        const cl = ws[window.XLSX.utils.encode_cell({ r, c })];
        row.push(cl ? cl.v : null);
      }
      rows.push(row);
    }
    sheets[name] = rows;
  }
  return readAgendaRows(sheets);
}

function fillSheets() {
  const sel = $("sheet");
  sel.innerHTML = "";
  for (const s of Object.keys(state.agenda)) sel.add(new Option(s, s));
  $("pickRow").hidden = !sel.options.length;
  fillItems();
}
function fillItems() {
  const items = state.agenda[$("sheet").value] || [];
  const sel = $("item");
  sel.innerHTML = "";
  items.forEach((x, i) => sel.add(new Option(
    `${x.item} | ${x.ins_operator} | ${x.ins_networks.map(([n]) => n).join(", ")} | ${x.band} | ${x.j_operator}`, i)));
}
function loadItem() {
  const it = (state.agenda[$("sheet").value] || [])[$("item").value];
  if (!it) return;
  $("item_no").value = it.item;
  $("ins_op").value = OPERATOR_NAMES[it.ins_operator] || it.ins_operator;
  $("ins_short").value = it.ins_operator;
  $("j_op").value = it.j_operator;
  $("band_label").value = it.band;
  $("ins_nets").value = netsToText(it.ins_networks);
  $("j_nets").value = netsToText(it.j_networks);
  for (const cb of $("bands").querySelectorAll("input"))
    cb.checked = new RegExp(`(^|[ ,])${cb.value.replace("/", "\\/")}($|[ ,])`).test(it.band);
  state.excluded = new Set();
  state.autoSection = state.autoItem = true;
  const dl = $("comments");
  dl.innerHTML = "";
  for (const [h, v] of it.comments) {
    const dt = document.createElement("dt"); dt.textContent = h;
    const dd = document.createElement("dd"); dd.textContent = v;
    dl.append(dt, dd);
  }
  $("commentsBox").hidden = !it.comments.length;
  renderExclusions(); autoHeadings(); redraft(); ituSummary(); schedule(0);
}

// ---------- ITU ----------
async function fetchItu() {
  const names = [...new Set([...netsOf("ins_nets"), ...netsOf("j_nets")].map(([n]) => n))];
  if (!names.length) return;
  if (state.discEdited && !confirm("Fetching will redraft the Discussion and Conclusion. Your edits there will be replaced. Continue?")) return;
  $("fetch").disabled = true;
  status(`Querying ${names.length} networks from ITU Space Explorer...`, "warn");
  try {
    const r = await fetch("api/itu", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    Object.assign(state.itu, j.data);
    autoHeadings(); redraft(); ituSummary(); schedule(0);
  } catch (e) {
    status(`ITU request failed: ${e.message}. You can load saved data (.json) instead.`, "err");
  } finally {
    $("fetch").disabled = false;
  }
}

// ---------- wiring ----------
function init() {
  for (const b of Object.keys(BANDS)) chip($("bands"), b, false, () => schedule());
  for (const s of SS_CHOICES) chip($("ss"), s, DEFAULT_SS_TYPES.includes(s), () => schedule());
  const restored = restore();
  renderExclusions(); autoHeadings(); ituSummary();

  for (const f of ["item_no", "ins_op", "j_op", "band_label", "ins_short", "custom", "ific_label"])
    $(f).addEventListener("input", () => { autoHeadings(); schedule(); });
  for (const f of ["ins_nets", "j_nets"])
    $(f).addEventListener("input", () => { renderExclusions(); autoHeadings(); ituSummary(); schedule(); });
  $("section_title").addEventListener("input", () => { state.autoSection = false; schedule(); });
  $("item_title").addEventListener("input", () => { state.autoItem = false; schedule(); });
  for (const f of ["discussion", "conclusion"]) $(f).addEventListener("input", () => { state.discEdited = true; schedule(); });
  $("list_mods").addEventListener("change", () => schedule());
  $("redraft").addEventListener("click", () => {
    if (state.discEdited && !confirm("Replace your edits in Discussion and Conclusion with a fresh draft?")) return;
    state.autoSection = state.autoItem = true; autoHeadings(); redraft(); schedule(0);
  });
  $("fetch").addEventListener("click", fetchItu);
  $("saveItu").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(state.itu, null, 1)], { type: "application/json" }));
    a.download = "itu_data.json"; a.click();
  });
  $("loadItu").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { Object.assign(state.itu, JSON.parse(await f.text())); autoHeadings(); redraft(); ituSummary(); schedule(0); }
    catch (err) { status("Could not read that JSON file: " + err.message, "err"); }
    e.target.value = "";
  });
  $("tplFile").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    state.tpl = await f.arrayBuffer(); state.tplName = f.name; $("tplName").textContent = f.name; schedule(0);
  });
  $("agendaFile").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { state.agenda = readWorkbook(await f.arrayBuffer()); fillSheets(); loadItem(); }
    catch (err) { status("Could not read the agenda: " + err.message, "err"); }
  });
  $("sheet").addEventListener("change", () => { fillItems(); loadItem(); });
  $("item").addEventListener("change", loadItem);
  $("download").addEventListener("click", () => {
    if (!state.blob) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(state.blob); a.download = state.fileName; a.click();
  });
  loadDefaultTemplate().then(() => schedule(0));
  if (!restored) $("ins_short").value = "BRI";
}
init();
