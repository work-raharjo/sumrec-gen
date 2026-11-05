// Summary record logic (port of the Python core): ITU data + agenda input -> section content and draft text.
// Works in the browser and in Node (ES module, no dependencies).

export const BANDS = {
  L: [[1000, 2000]], S: [[2000, 2700]], C: [[3400, 7075]], X: [[7075, 8500]],
  Ku: [[10700, 15400]], Ka: [[17300, 31000]], "Q/V": [[37500, 52400]], V: [[42500, 52400]],
};
export const DEFAULT_SS_TYPES = ["AR11/C", "CR/C"];
export const SS_CHOICES = ["AR11/C", "CR/C", "AR11/A", "API/A", "API/C", "CR/D", "CR/E", "RES49", "PART I-S", "PART II-S"];
// RR Appendix 5, Table 5-1 coordination arcs (GSO/GSO, No. 9.7) for the common FSS bands
export const COORD_ARC = { C: 7, Ku: 6, Ka: 8 };
const REV_LABEL = { M: "MOD", A: "ADD", C: "CORR", S: "SUP" };
const NBSP = " ";
const LETTERS = "abcdefghijklmnopqrstuvwxyz";

// ---------- formatting ----------
export function fmtNum(v) {
  let s = Number(v).toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  let [ip, dp] = s.split(".");
  const neg = ip.startsWith("-");
  ip = ip.replace("-", "");
  const groups = [];
  while (ip.length > 3) { groups.unshift(ip.slice(-3)); ip = ip.slice(0, -3); }
  groups.unshift(ip);
  return (neg ? "-" : "") + groups.join(NBSP) + (dp ? "." + dp : ""); // non-breaking thousands separator
}
export const fmtRange = (r) => `${fmtNum(r[0])}${NBSP}– ${fmtNum(r[1])}`;
export function fmtPos(lon) {
  if (lon === null || lon === undefined || Number.isNaN(lon)) return "NGSO";
  return g(Math.abs(lon)) + (lon >= 0 ? "E" : "W");
}
// like Python's "{:g}"
export const g = (x) => String(Number(Number(x).toPrecision(6)));

export function joinAnd(xs) {
  xs = [...xs];
  if (!xs.length) return "";
  return xs.length === 1 ? xs[0] : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1];
}
export const rangesTxt = (rs) => (rs.length ? joinAnd(rs.map(fmtRange)) + " MHz" : "");

export function ssLabel(p) {
  const ref = (p.ssn_ref || "").trim();
  let s = p.ssn_no !== null && p.ssn_no !== undefined && p.ssn_no !== "" ? `${ref}/${p.ssn_no}` : ref;
  const rev = (p.ssn_rev || "").trim();
  if (rev) s += ` ${REV_LABEL[rev] || rev}-${p.ssn_rev_no || 1}`;
  return s;
}

// ---------- ranges ----------
export function merge(ranges) {
  const out = [];
  for (const [a, b] of [...ranges].sort((x, y) => x[0] - y[0] || x[1] - y[1])) {
    if (out.length && a <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b);
    else out.push([a, b]);
  }
  return out;
}
export function intersect(r1, r2) {
  const out = [];
  for (const [a, b] of r1) for (const [c, d] of r2) {
    const lo = Math.max(a, c), hi = Math.min(b, d);
    if (hi > lo) out.push([lo, hi]);
  }
  return merge(out);
}
export function windowsFor(bands = [], custom = []) {
  let w = [];
  for (const b of bands) w = w.concat(BANDS[b] || []);
  w = w.concat(custom);
  return w.length ? merge(w) : [[0, 1e9]];
}
export function netRanges(d) {
  let ns = d.notices.filter((n) => n.ntf_rsn === "C" || n.ntf_rsn === "N");
  if (!ns.length) ns = d.notices;
  return [merge(ns.flatMap((n) => n.tx)), merge(ns.flatMap((n) => n.rx))];
}
export function separation(a, b) {
  if (a === null || b === null || a === undefined || b === undefined) return null;
  const v = Math.abs(a - b) % 360;
  return Math.min(v, 360 - v);
}
export function dateKey(s) {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(s || "");
  return m ? Number(m[3] + m[2] + m[1]) : Number.MAX_SAFE_INTEGER;
}

// ---------- agenda ----------
const NET_RE = /([A-Z0-9][A-Z0-9\-._/]*)\s*\(([^)]+)\)/g;
export function parseNetworks(text) {
  if (!text) return [];
  const t = String(text).replace(/\[[^\]]*\]/g, " ");
  const out = [], seen = new Set();
  for (const m of t.matchAll(NET_RE)) {
    if (!seen.has(m[1])) { seen.add(m[1]); out.push([m[1], m[2].trim()]); }
  }
  return out;
}
export function parsePos(pos) {
  const m = /^\s*([\d.]+)\s*([EW])\s*$/i.exec(pos || "");
  if (!m) return null;
  const v = parseFloat(m[1]);
  return m[2].toUpperCase() === "W" ? -v : v;
}
/** sheets: {name: rows[][]} where rows[r][c] is the cell value of column c (0 = A). */
export function readAgendaRows(sheets) {
  const result = {};
  for (const [title, rows] of Object.entries(sheets)) {
    const headers = {}, items = [];
    for (const r of rows) {
      const cells = [...(r || [])];
      while (cells.length < 14) cells.push(null);
      for (let ci = 6; ci < 14; ci++) {
        const v = cells[ci];
        if (typeof v === "string" && v.toLowerCase().includes("comment")) headers[ci] = v.split(/\s+/).join(" ").trim();
      }
      const a = cells[0] === null || cells[0] === undefined ? "" : String(cells[0]).trim();
      if (!/^\d+\.\d+\.\d+$/.test(a)) continue;
      const comments = [];
      for (let ci = 6; ci < 14; ci++) {
        const v = cells[ci];
        if (v !== null && v !== undefined && String(v).trim() !== "" && String(v).trim() !== "-")
          comments.push([headers[ci] || `Column ${ci + 1}`, String(v).trim()]);
      }
      items.push({
        item: a,
        ins_operator: String(cells[1] || "").trim(),
        ins_networks: parseNetworks(cells[2]),
        band: String(cells[3] || "").split(/\s+/).join(" ").trim(),
        j_operator: String(cells[4] || "").trim(),
        j_networks: parseNetworks(cells[5]),
        comments,
      });
    }
    if (items.length) result[title] = items;
  }
  return result;
}

// ---------- analysis ----------
export function pubRows(name, posLabel, d, ssTypes, listMods = false) {
  let cand = (d ? d.pubs : []).filter((p) => ssTypes.includes((p.ssn_ref || "").trim()));
  if (!listMods && cand.length) {
    let base = cand.filter((p) => !(p.ssn_rev || "").trim());
    if (!base.length) base = cand;
    base = [...base].sort((x, y) => dateKey(x.d_rcv) - dateKey(y.d_rcv) || (x.wic_no || 0) - (y.wic_no || 0));
    cand = [base[0]];
  }
  const rows = cand.map((p) => [name, posLabel, ssLabel(p), p.d_rcv || "-", `IFIC${p.wic_no}\n${p.d_wic}`]);
  if (!rows.length)
    rows.push([name, posLabel, d && d.found ? "No matching special section" : "Not yet received by the BR", "-", "-"]);
  return rows;
}
export function protectionDate(d, ssTypes) {
  let ds = d.pubs.filter((p) => ssTypes.includes((p.ssn_ref || "").trim()) && p.d_rcv).map((p) => p.d_rcv);
  if (!ds.length) ds = d.notices.filter((n) => n.d_rcv).map((n) => n.d_rcv);
  return ds.length ? ds.reduce((m, x) => (dateKey(x) < dateKey(m) ? x : m)) : null;
}
export function netLon(name, posTxt, data) {
  const d = data[name];
  if (d && d.found && d.long_nom !== null && d.long_nom !== undefined && d.ntc_type === "G") return Number(d.long_nom);
  return parsePos(posTxt);
}
export const netList = (nets, data) => nets.map(([n, p]) => `${n} (${fmtPos(netLon(n, p, data))})`).join(", ");
export const sn = (nets) => (nets.length > 1 ? "satellite networks" : "satellite network");
const hasOv = (gr) => gr.se.length || gr.es.length || gr.opp.length;

export function analyse(inp, data) {
  const win = windowsFor(inp.bands || [], inp.custom_ranges || []);
  const ex = new Set(inp.exclude || []);
  const ins = inp.ins_nets;
  const js = inp.j_nets.filter(([n]) => !ex.has(n));
  const insTx = merge(ins.filter(([n]) => data[n]).flatMap(([n]) => netRanges(data[n])[0]));
  const insRx = merge(ins.filter(([n]) => data[n]).flatMap(([n]) => netRanges(data[n])[1]));
  const insTxW = intersect(insTx, win), insRxW = intersect(insRx, win);
  const groups = new Map(), missing = [];
  let uSe = [], uEs = [], uOpp = [];
  for (const [n, p] of js) {
    const d = data[n];
    if (!d || !d.found) { missing.push(n); continue; }
    const [tx, rx] = netRanges(d);
    const se = intersect(tx, insTxW), es = intersect(rx, insRxW);
    const opp = merge(intersect(tx, insRxW).concat(intersect(rx, insTxW)));
    uSe = uSe.concat(se); uEs = uEs.concat(es); uOpp = uOpp.concat(opp);
    const key = JSON.stringify([se, es, opp]);
    if (!groups.has(key)) groups.set(key, { nets: [], se, es, opp });
    groups.get(key).nets.push([n, p]);
  }
  const width = (gr) => [...gr.se, ...gr.es, ...gr.opp].reduce((s, [a, b]) => s + b - a, 0);
  // widest overlap first, networks without any overlap last (stable sort)
  const glist = [...groups.values()].sort((x, y) => (hasOv(x) ? 0 : 1) - (hasOv(y) ? 0 : 1) || width(y) - width(x));
  return { ins_tx: insTxW, ins_rx: insRxW, groups: glist, missing,
    union: { se: merge(uSe), es: merge(uEs), opp: merge(uOpp) } };
}

export function buildContent(inp, data) {
  const ssTypes = inp.ss_types && inp.ss_types.length ? inp.ss_types : DEFAULT_SS_TYPES;
  const ex = new Set(inp.exclude || []);
  const ins = inp.ins_nets;
  const js = inp.j_nets.filter(([n]) => !ex.has(n));
  const lon = (n, p) => netLon(n, p, data);
  const t1 = ins.flatMap(([n, p]) => pubRows(n, fmtPos(lon(n, p)), data[n], ssTypes, !!inp.list_mods));
  const t2 = js.flatMap(([n, p]) => pubRows(n, fmtPos(lon(n, p)), data[n], ssTypes, !!inp.list_mods));
  const t3 = [];
  for (const [ni, pi] of ins) {
    const li = lon(ni, pi);
    for (const [n, p] of js) {
      const sep = separation(li, lon(n, p));
      t3.push([ni, n, sep === null ? "-" : g(sep)]);
    }
  }
  const u = analyse(inp, data).union;
  const freqRows = [];
  for (const [rs, dir] of [[u.se, "space-to-Earth"], [u.es, "Earth-to-space"], [u.opp, "opposite"]])
    for (const r of rs) freqRows.push(`${fmtRange(r)} MHz in the ${dir} direction, as appropriate;`);
  return {
    section_no: inp.section_no, section_title: inp.section_title,
    item_no: inp.item_no, item_title: inp.item_title,
    t1, t2, t3, freq_rows: freqRows, j_list: netList(js, data),
    ins_label: netList(ins, data), band_label: inp.band_label || "",
    discussion: inp.discussion || "", conclusion: inp.conclusion || "",
  };
}

// ---------- draft text ----------
// '## ' starts a numbered subsection, 'a)<TAB>' a lettered line, [[...]] marks text still to be completed.
export function draftDiscussion(inp, data) {
  const ex = new Set(inp.exclude || []);
  const a = analyse(inp, data);
  const insNames = inp.ins_nets.map(([n]) => n);
  const ins = netList(inp.ins_nets, data);
  const band = inp.band_label || "";
  const bandB = band ? `${band}-Band` : "band";
  const me = inp.ins_short || "BRI";
  const them = inp.j_operator || "the J delegation";
  const paras = [];
  if (ex.size) {
    const exn = inp.j_nets.filter(([n]) => ex.has(n));
    paras.push(`The ${netList(exn, data)} satellite networks [[reason, e.g. have exceeded the regulatory time limit ` +
      `and were moved to Other Business]]. These satellite networks are not considered under this agenda item.`);
  }
  if (a.missing.length)
    paras.push(`As of ${inp.ific_label || "[[BR IFIC No.]]"}, no special section has been published for the ` +
      `${a.missing.join(", ")} satellite network${a.missing.length > 1 ? "s" : ""}.`);
  const groups = a.groups.filter(hasOv);
  const noOv = a.groups.filter((gr) => !hasOv(gr)).flatMap((gr) => gr.nets);
  if (groups.length + (noOv.length ? 1 : 0) > 1) {
    paras.push(`Since the overlapping frequency ranges differ between the ${them} satellite networks, the ` +
      `coordination between ${ins} Satellite Network and the ${them} satellite networks in the ${bandB} ` +
      `will be divided as below:`);
    const items = groups.map((gr, i) => {
      const ov = [];
      if (gr.se.length) ov.push(`${rangesTxt(gr.se)} (space-to-Earth)`);
      if (gr.es.length) ov.push(`${rangesTxt(gr.es)} (Earth-to-space)`);
      if (gr.opp.length) ov.push(`${rangesTxt(gr.opp)} (opposite direction)`);
      return `Section ${inp.item_no}.${i + 1}: coordination with the ${netList(gr.nets, data)} ${sn(gr.nets)}, ` +
        `with the frequency overlap in ${joinAnd(ov)}`;
    });
    if (noOv.length)
      items.push(`Section ${inp.item_no}.${groups.length + 1}: the ${netList(noOv, data)} ${sn(noOv)}, ` +
        `with no frequency overlap`);
    items.forEach((t, i) => paras.push(`${LETTERS[i]})\t${t}${i < items.length - 1 ? ";" : "."}`));
  }
  const li = insNames.length ? netLon(insNames[0], inp.ins_nets[0][1], data) : null;
  const arc = COORD_ARC[band];
  groups.forEach((gr, i) => {
    const k = i + 1;
    const lst = netList(gr.nets, data);
    const many = gr.nets.length > 1;
    const SN = many ? "Satellite Networks" : "Satellite Network";
    const sn_ = many ? "satellite networks" : "satellite network";
    paras.push(`## ${inp.item_no}.${k}\tCoordination between ${ins} Satellite Network and the ${lst} ${SN} in the ${bandB}`);
    const ov = [];
    if (gr.se.length) ov.push(`${rangesTxt(gr.se)} in the space-to-Earth direction`);
    if (gr.es.length) ov.push(`${rangesTxt(gr.es)} in the Earth-to-space direction`);
    if (gr.opp.length) ov.push(`${rangesTxt(gr.opp)} in the opposite direction`);
    paras.push(`Both parties confirmed that the frequency overlap between ${ins} Satellite Network and the ${lst} ` +
      `${sn_} in the ${bandB} occurred in ${joinAnd(ov)}.`);
    const seps = gr.nets.map(([n, p]) => separation(li, netLon(n, p, data))).filter((x) => x !== null);
    const minSep = seps.length ? Math.min(...seps) : null;
    if (minSep !== null) {
      paras.push(many
        ? `Both parties confirmed that the minimal orbital separations between ${ins} Satellite Network and the ` +
          `${lst} satellite networks are greater than and equal to ${g(minSep)}°.`
        : `Both parties confirmed that the orbital separation between ${ins} Satellite Network and the ${lst} ` +
          `satellite network is ${g(minSep)}°.`);
    }
    paras.push(`[[${me} believed that the unacceptable interference between those satellite networks is minimal and ` +
      `the orbital separations are considered adequate to avoid any harmful interference between those satellite ` +
      `networks in the ${bandB}.]]`);
    if (arc && minSep !== null && minSep >= arc)
      paras.push(`[[${me} also believed that the condition is also met in accordance with the threshold of arc ` +
        `coordination as governed in ITU Radio Regulations, Appendix 5, Table 5-1 for the ${bandB} frequency ` +
        `spectrum coordination ± ${arc}°. Therefore, the coordination between these satellite networks ` +
        `could be considered as complete coordination.]]`);
    paras.push(`${them} [[agreed with the proposal that coordination between the ${me} and ${them} satellite ` +
      `networks can be considered complete / response of ${them}]].`);
    paras.push(`[[${me} agreed to complete the satellite coordination between ${ins} Satellite Network and the ` +
      `${lst} ${SN} in the ${bandB}.]]`);
    paras.push(`[Conclusion: Based on the above, coordination between ${ins} Satellite Network and the ${lst} ` +
      `${sn_} in the ${bandB} [[can be considered complete / will be continued via correspondence or at the ` +
      `future satellite coordination meeting]]]`);
  });
  if (noOv.length) {
    const k = groups.length + 1, s = noOv.length > 1 ? "s" : "";
    paras.push(`## ${inp.item_no}.${k}\tCoordination between ${ins} Satellite Network and the ` +
      `${netList(noOv, data)} Satellite Network${s} in the ${bandB}`);
    paras.push(`Both parties confirmed that there is no frequency overlap between ${ins} Satellite Network and the ` +
      `${netList(noOv, data)} satellite network${s} in the ${bandB}. Therefore, coordination is not required.`);
  }
  return paras.join("\n\n");
}

export function draftConclusion(inp, data) {
  data = data || {};
  const ins = netList(inp.ins_nets, data);
  const band = inp.band_label || "";
  const outcome = "[[was completed/was not completed and will be continued via correspondence or at the future " +
    "satellite coordination meeting]]";
  const groups = Object.keys(data).length ? analyse(inp, data).groups.filter(hasOv) : [];
  if (groups.length <= 1) {
    const ex = new Set(inp.exclude || []);
    const js = inp.j_nets.filter(([n]) => !ex.has(n));
    return `Based on the above, both delegations agreed that coordination between the ${ins} satellite network ` +
      `and the ${netList(js, data)} ${sn(js)} in the ${band} band ${outcome}.`;
  }
  const lines = [`Based on the above, both delegations agreed that coordination between the ${ins} satellite network ` +
    `and the following satellite networks in the ${band} band:`];
  groups.forEach((gr, i) => {
    const who = gr.nets.length <= 6 ? `the ${netList(gr.nets, data)} ${sn(gr.nets)}` : "the satellite networks";
    lines.push(`${LETTERS[i]})\t${who} in Section ${inp.item_no}.${i + 1} ${outcome}${i < groups.length - 1 ? ";" : "."}`);
  });
  return lines.join("\n\n");
}
