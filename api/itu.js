// Vercel serverless function: proxy to the public ITU Space Explorer API (no login needed).
// POST /api/itu  {"names": ["NUSANTARA-BR1-E", "JMCS-1", ...]}
// -> {"data": {name: {found, long_nom, ntc_type, notices: [{ntc_id, ntf_rsn, prov, d_rcv, plan, tx, rx}], pubs: [...]}},
//     "fetched_at": ISO time}
// The browser cannot call itu.int directly (CORS), so the app goes through this function.

const BASE = "https://www.itu.int/itu-r/space/apps/ep/spaceexplorer/v1/";
const HEADERS = { "Content-Type": "application/json", Accept: "application/json",
  "User-Agent": "Mozilla/5.0 (sumrec-gen)" };
const MAX_NAMES = 200;

function queryBody(names) {
  return {
    general: { network: "active", adm: [], networkOrgCode: [], satelliteName: names, serviceType: "all" },
    satNetworkTypes: { geo: true, geoFrom: null, geoTo: null, nonGeo: true, apogeeFrom: null, apogeeTo: null,
      perigeeFrom: null, perigeeTo: null, minAltitudeFrom: null, minAltitudeTo: null, referenceBody: null,
      constelattion: false, shortDurationMission: false },
    frequencies: [],
    regProcess: {
      SuppressionStatus: "All", masterReg: false, nonPlanBand: false, bssPlanBand: false, fssPlanBand: false, esimPlanBand: false,
      nonPlan: { advancePublications: true, coordination: true, dueDiligence: true, notification: true, planNon: true, res35: true, res8: true },
      bssPlan: { downRegion1and3: true, feederRegion1and3: true, overallRegion2: true, planBssAll: true, pendingArt4: true,
        listArt4: true, dueDiligence: true, notificationArt5: true, sofArt2aCoordination: true, sofArt2aNotification: true, planBss: true },
      fssPlan: { planFssAll: true, planFss: true, pendingArt6: true, listArt6: true, dueDiligence: true, notificationArt8: true },
      esimPlan: { planEsimAll: true, pending: true, list: true, notification: true },
    },
    publications: { latestBrIfic: false, brIficNumberFrom: null, brIficNumberTo: null, brIficDateFrom: null,
      brIficDateTo: null, specialSection: [], specialSectionNumber: null },
    regDates: { brNoticeDateReceiptFrom: null, brNoticeDateReceiptTo: null, networkProtectionDateFrom: null,
      networkProtectionDateTo: null, useDateFrom: null, useDateTo: null, useLimitDateFrom: null, useLimitDateTo: null },
    orderBy: "", skip: 0, take: 1000,
  };
}

function ranges(tooltip) {
  if (!tooltip) return [];
  try { return (JSON.parse(tooltip).ranges || []).map((x) => [Number(x.f), Number(x.t)]); } catch { return []; }
}

async function getJson(url, init = {}) {
  const r = await fetch(url, { ...init, headers: HEADERS, signal: AbortSignal.timeout(25000) });
  if (!r.ok) throw new Error(`ITU ${r.status} for ${url}`);
  return r.json();
}

async function pool(items, size, fn) {
  const out = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(size, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k]); }
  }));
  return out;
}

export async function fetchNetworks(names) {
  names = [...new Set(names.map((n) => String(n).trim()).filter(Boolean))];
  const out = Object.fromEntries(names.map((n) => [n, { found: false, long_nom: null, ntc_type: null, notices: [], pubs: [] }]));
  if (!names.length) return out;
  const q = await getJson(BASE + "queries", { method: "POST", body: JSON.stringify(queryBody(names)) });
  for (const x of q.table || []) {
    const d = out[x.sat_name];
    if (!d) continue;
    d.found = true; d.long_nom = x.long_nom; d.ntc_type = x.ntc_type;
    d.notices.push({ ntc_id: x.ntc_id, ntf_rsn: x.ntf_rsn, prov: x.prov, d_rcv: x.d_rcv, plan: !!x.f_plan,
      tx: ranges(x.freq_tooltip_emi), rx: ranges(x.freq_tooltip_rcp) });
  }
  const jobs = Object.entries(out).flatMap(([n, d]) => d.notices.map((nt) => [n, nt]));
  const lists = await pool(jobs, 8, async ([n, nt]) => {
    const url = `${BASE}dashboard/space-stations/publications/${nt.plan ? "plans" : "non-plans"}/` +
      `${encodeURIComponent(n)}/${nt.ntc_id}/publications`;
    try { return (await getJson(url)).publications?.list || []; } catch { return []; }
  });
  const seen = Object.fromEntries(names.map((n) => [n, new Set()]));
  jobs.forEach(([n], k) => {
    for (const p of lists[k]) {
      const key = [p.ssn_ref, p.ssn_no, p.ssn_rev, p.ssn_rev_no, p.wic_no].join("|");
      if (seen[n].has(key)) continue;
      seen[n].add(key);
      out[n].pubs.push({ ssn_ref: p.ssn_ref, ssn_no: p.ssn_no, ssn_rev: p.ssn_rev, ssn_rev_no: p.ssn_rev_no,
        d_rcv: p.d_rcv, wic_no: p.wic_no, d_wic: p.d_wic });
    }
  });
  for (const d of Object.values(out)) d.pubs.sort((a, b) => (a.wic_no || 0) - (b.wic_no || 0));
  return out;
}

export default async function handler(req, res) {
  try {
    let names = [];
    if (req.method === "POST") {
      const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
      names = body.names || [];
    } else if (req.method === "GET") {
      names = String(req.query?.names || "").split(",");
    } else {
      res.status(405).json({ error: "Use POST with {names: [...]}" });
      return;
    }
    if (!Array.isArray(names) || names.length > MAX_NAMES) {
      res.status(400).json({ error: `names must be a list of at most ${MAX_NAMES} satellite network names` });
      return;
    }
    const data = await fetchNetworks(names);
    res.setHeader("Cache-Control", "s-maxage=3600, stale-while-revalidate=86400");
    res.status(200).json({ data, fetched_at: new Date().toISOString() });
  } catch (e) {
    res.status(502).json({ error: String(e.message || e) });
  }
}
