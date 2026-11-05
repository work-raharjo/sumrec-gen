// Writes one summary-record section into the INS-J template (.docx) with JSZip, keeping the template's styles,
// page setup and footer. Text inside [[...]] is highlighted yellow. Port of docx_builder.py.

const FONT = '<w:rFonts w:ascii="Arial" w:eastAsia="Arial" w:hAnsi="Arial" w:cs="Arial"/>';
const BORDER = "<w:tblBorders>" + ["top", "left", "bottom", "right", "insideH", "insideV"]
  .map((s) => `<w:${s} w:val="single" w:sz="4" w:space="0" w:color="000000"/>`).join("") + "</w:tblBorders>";

export const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function rpr({ b = false, u = false, hl = false, sz = 24, color = null, iOff = false } = {}) {
  let s = FONT;
  if (b) s += "<w:b/><w:bCs/>";
  if (iOff) s += '<w:i w:val="0"/><w:iCs w:val="0"/>';
  if (color) s += `<w:color w:val="${color}"/>`;
  s += `<w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/>`;
  if (hl) s += '<w:highlight w:val="yellow"/>';
  if (u) s += '<w:u w:val="single"/>';
  return "<w:rPr>" + s + "</w:rPr>";
}

function runs(text, kw = {}) {
  let out = "";
  for (const part of String(text).split(/(\[\[.*?\]\])/)) {
    if (!part) continue;
    const hl = part.startsWith("[[");
    const t = hl ? part.slice(2, -2) : part;
    out += "<w:r>" + rpr({ ...kw, hl }) + '<w:t xml:space="preserve">' + esc(t) + "</w:t></w:r>";
  }
  return out;
}

function para(text, { jc = "both", spacing = null, b = false, u = false, sz = 24, keep = false } = {}) {
  let ppr = keep ? "<w:keepNext/>" : "";
  if (spacing) ppr += `<w:spacing w:before="${spacing[0]}" w:after="${spacing[1]}"/>`;
  ppr += `<w:jc w:val="${jc}"/>` + rpr({ b, u, sz });
  return "<w:p><w:pPr>" + ppr + "</w:pPr>" + runs(text, { b, u, sz }) + "</w:p>";
}
const empty = () => '<w:p><w:pPr><w:jc w:val="both"/>' + rpr() + "</w:pPr></w:p>";

function h3(num, text) {
  const rp = rpr({ color: "000000" });
  return '<w:p><w:pPr><w:pStyle w:val="Heading3"/><w:ind w:left="1134" w:hanging="1134"/><w:jc w:val="both"/>' +
    rp + "</w:pPr><w:r>" + rp + `<w:t>${esc(num)}</w:t><w:tab/><w:t xml:space="preserve">${esc(text)}</w:t></w:r></w:p>`;
}
function h4(text) {
  const rp = rpr({ iOff: true, color: "000000", u: true });
  return '<w:p><w:pPr><w:pStyle w:val="Heading4"/><w:jc w:val="both"/>' + rp + "</w:pPr><w:r>" + rp +
    `<w:t xml:space="preserve">${esc(text)}</w:t></w:r></w:p>`;
}
const caption = (text) => para(text, { jc: "center", b: true, u: true, keep: true });

function cell(text, w, { sz = 24, jc = "center", vmerge = null } = {}) {
  let tcpr = `<w:tcW w:w="${w}" w:type="dxa"/>`;
  if (vmerge === "restart") tcpr += '<w:vMerge w:val="restart"/>';
  else if (vmerge === "cont") tcpr += "<w:vMerge/>";
  tcpr += '<w:vAlign w:val="center"/>';
  const ps = (text ? String(text).split("\n") : [""]).map((ln) =>
    `<w:p><w:pPr><w:spacing w:before="20" w:after="20"/><w:jc w:val="${jc}"/>` + rpr({ sz }) + "</w:pPr>" +
    (ln ? runs(ln, { sz }) : "") + "</w:p>").join("");
  return "<w:tc><w:tcPr>" + tcpr + "</w:tcPr>" + ps + "</w:tc>";
}

function table(widths, header, rows, { mergeCols = [], sz = 24 } = {}) {
  const tw = widths.reduce((a, b) => a + b, 0);
  let x = `<w:tbl><w:tblPr><w:tblW w:w="${tw}" w:type="dxa"/><w:jc w:val="center"/>` + BORDER +
    '<w:tblLayout w:type="fixed"/><w:tblLook w:val="0400" w:firstRow="0" w:lastRow="0" w:firstColumn="0" ' +
    'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>' +
    widths.map((w) => `<w:gridCol w:w="${w}"/>`).join("") + "</w:tblGrid>";
  x += "<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>" + header.map((h, i) => cell(h, widths[i], { sz })).join("") + "</w:tr>";
  rows.forEach((r, ri) => {
    x += "<w:tr><w:trPr><w:cantSplit/></w:trPr>";
    r.forEach((v, ci) => {
      let vm = null;
      if (mergeCols.includes(ci)) {
        const keys = mergeCols.filter((k) => k <= ci);
        const same = ri > 0 && keys.every((k) => rows[ri - 1][k] === r[k]);
        const nxt = ri + 1 < rows.length && keys.every((k) => rows[ri + 1][k] === r[k]);
        if (same) { vm = "cont"; v = ""; } else if (nxt) vm = "restart";
      }
      x += cell(v, widths[ci], { sz, vmerge: vm });
    });
    x += "</w:tr>";
  });
  return x + "</w:tbl>";
}

function listPara(text, spacing = [0, 60]) {
  const [lead, rest] = text.includes("\t") ? text.split(/\t(.*)/s) : [text, null];
  return "<w:p><w:pPr>" + `<w:spacing w:before="${spacing[0]}" w:after="${spacing[1]}"/>` +
    '<w:ind w:left="720" w:hanging="360"/><w:jc w:val="both"/>' + rpr() + "</w:pPr>" + runs(lead) +
    (rest !== null ? "<w:r>" + rpr() + "<w:tab/></w:r>" + runs(rest) : "") + "</w:p>";
}

function subheading(text) {
  let [num, ...rest] = text.split("\t");
  let title = rest.join("\t");
  if (!title) { const i = text.indexOf(" "); num = text.slice(0, i); title = text.slice(i + 1); }
  const rp = rpr({ b: true });
  return '<w:p><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:ind w:left="1134" w:hanging="1134"/>' +
    '<w:jc w:val="both"/>' + rp + "</w:pPr><w:r>" + rp + `<w:t>${esc(num.trim())}</w:t><w:tab/>` +
    `<w:t xml:space="preserve">${esc(title.trim())}</w:t></w:r></w:p>`;
}

// collapse ordinary whitespace only, keep non-breaking spaces
const squash = (t) => t.replace(/[ \t\r\n]+/g, " ").trim();

export function richText(text) {
  let out = "";
  for (const p of String(text || "").split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean)) {
    if (p.startsWith("## ")) out += subheading(p.slice(3).trim());
    else if (/^[a-z]\)[\t ]/.test(p)) out += listPara(p.slice(0, 2) + "\t" + squash(p.slice(3)), [0, 80]);
    else out += para(squash(p), { spacing: [0, 200] });
  }
  return out;
}

function bandBlock(label, rows) {
  const nb = "<w:tblBorders>" + ["top", "left", "bottom", "right", "insideH", "insideV"]
    .map((x) => `<w:${x} w:val="none" w:sz="0" w:space="0" w:color="auto"/>`).join("") + "</w:tblBorders>";
  const tc = (w, ps) => `<w:tc><w:tcPr><w:tcW w:w="${w}" w:type="dxa"/></w:tcPr>` + ps.map((t) =>
    '<w:p><w:pPr><w:spacing w:before="120" w:after="120"/><w:jc w:val="both"/>' + rpr() + "</w:pPr>" + runs(t) + "</w:p>").join("") + "</w:tc>";
  return '<w:tbl><w:tblPr><w:tblW w:w="9006" w:type="dxa"/>' + nb + '<w:tblLayout w:type="fixed"/>' +
    '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>' +
    '</w:tblPr><w:tblGrid><w:gridCol w:w="1526"/><w:gridCol w:w="567"/><w:gridCol w:w="6913"/></w:tblGrid><w:tr>' +
    tc(1526, [label]) + tc(567, [":"]) + tc(6913, rows) + "</w:tr></w:tbl>";
}

export function sectionXml(c) {
  const W5 = [2450, 1150, 1700, 1550, 1775];
  let body = h3(c.section_no, c.section_title) + h3(c.item_no, c.item_title);
  body += h4("ITU Publications");
  body += para("The coordination between the satellite networks of the Administrations of Indonesia and Japan was " +
    "considered based on the following ITU publications.", { spacing: [240, 240] });
  body += caption("Table 1. The Indonesian satellite network(s)");
  body += table(W5, ["Network Name", "Orbital Location", "Special Section No.", "Date of Receipt by BR", "WIC/IFIC date"],
    c.t1, { mergeCols: [0, 1], sz: 22 });
  body += empty();
  body += caption("Table 2. The Japanese satellite network(s)");
  body += table(W5, ["Network Name", "Orbital Position", "Special Section No.", "Date of Receipt by BR", "Published Date"],
    c.t2, { mergeCols: [0, 1], sz: 22 });
  body += empty();
  body += h4("Orbital Separation");
  body += para("The following table presents the geocentric orbital separations between the Indonesian and " +
    "Japanese satellite networks under consideration.", { spacing: [240, 240] });
  body += caption("Table 3. Orbital Separation");
  body += table([3394, 3296, 1950], ["Indonesian satellite network(s)", "Japanese satellite network(s)",
    "Orbital separation (°)"], c.t3);
  body += empty();
  body += h4("Frequency Overlap");
  const band = c.band_label;
  if (c.freq_rows.length) {
    body += para(`Both delegations agreed that the frequency overlap between the ${c.ins_label} satellite network ` +
      `and the ${c.j_list} satellite networks in the ${band} band occurred in these following bands:`, { spacing: [240, 120] });
    body += bandBlock(band ? `${band}-Band` : "", c.freq_rows);
  } else {
    body += para(`Both delegations agreed that there is no frequency overlap between the ${c.ins_label} satellite ` +
      `network and the ${c.j_list} satellite networks in the ${band} band.`, { spacing: [240, 240] });
  }
  body += h4("Discussion") + richText(c.discussion);
  body += h4("Conclusion") + richText(c.conclusion);
  return body;
}

/** templateData: ArrayBuffer/Uint8Array of the template; returns a Blob (browser) or Uint8Array (Node). */
export async function buildDocx(JSZip, templateData, content, { type = "blob" } = {}) {
  const zip = await JSZip.loadAsync(templateData);
  let d = await zip.file("word/document.xml").async("string");
  const b0 = d.indexOf("<w:body>") + "<w:body>".length;
  const s0 = d.lastIndexOf("<w:sectPr");
  d = d.slice(0, b0) + sectionXml(content) + d.slice(s0);
  zip.file("word/document.xml", d);
  for (const name of Object.keys(zip.files).filter((n) => /^word\/footer\d*\.xml$/.test(n))) {
    let f = await zip.file(name).async("string");
    // template footer label "2.[x].1 - Page" -> "<item no> - Page"
    f = f.replace(/<w:t>2\.\[x<\/w:t>([\s\S]*?)<w:t>\]<\/w:t>([\s\S]*?)<w:t xml:space="preserve">\.1 - Page <\/w:t>/,
      (_, g1, g2) => `<w:t>${esc(content.item_no)}</w:t>${g1}<w:t></w:t>${g2}<w:t xml:space="preserve"> - Page </w:t>`);
    zip.file(name, f);
  }
  return zip.generateAsync({ type, compression: "DEFLATE",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
}
