"""Client for the public ITU Space Explorer API (Space Network Systems data).

Only public endpoints are used (no TIES login needed):
  POST v1/queries                                   -> notices per satellite network name
  GET  v1/dashboard/space-stations/publications/... -> BR IFIC publication history per notice
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://www.itu.int/itu-r/space/apps/ep/spaceexplorer/v1/"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (summary-record-generator)",
}
TIMEOUT = 60

REV_LABEL = {"M": "MOD", "A": "ADD", "C": "CORR", "S": "SUP"}


def _query_body(names: list[str]) -> dict:
    return {
        "general": {"network": "active", "adm": [], "networkOrgCode": [], "satelliteName": names, "serviceType": "all"},
        "satNetworkTypes": {"geo": True, "geoFrom": None, "geoTo": None, "nonGeo": True, "apogeeFrom": None,
                            "apogeeTo": None, "perigeeFrom": None, "perigeeTo": None, "minAltitudeFrom": None,
                            "minAltitudeTo": None, "referenceBody": None, "constelattion": False,
                            "shortDurationMission": False},
        "frequencies": [],
        "regProcess": {
            "SuppressionStatus": "All", "masterReg": False, "nonPlanBand": False, "bssPlanBand": False,
            "fssPlanBand": False, "esimPlanBand": False,
            "nonPlan": {"advancePublications": True, "coordination": True, "dueDiligence": True,
                        "notification": True, "planNon": True, "res35": True, "res8": True},
            "bssPlan": {"downRegion1and3": True, "feederRegion1and3": True, "overallRegion2": True,
                        "planBssAll": True, "pendingArt4": True, "listArt4": True, "dueDiligence": True,
                        "notificationArt5": True, "sofArt2aCoordination": True, "sofArt2aNotification": True,
                        "planBss": True},
            "fssPlan": {"planFssAll": True, "planFss": True, "pendingArt6": True, "listArt6": True,
                        "dueDiligence": True, "notificationArt8": True},
            "esimPlan": {"planEsimAll": True, "pending": True, "list": True, "notification": True},
        },
        "publications": {"latestBrIfic": False, "brIficNumberFrom": None, "brIficNumberTo": None,
                         "brIficDateFrom": None, "brIficDateTo": None, "specialSection": [],
                         "specialSectionNumber": None},
        "regDates": {"brNoticeDateReceiptFrom": None, "brNoticeDateReceiptTo": None,
                     "networkProtectionDateFrom": None, "networkProtectionDateTo": None, "useDateFrom": None,
                     "useDateTo": None, "useLimitDateFrom": None, "useLimitDateTo": None},
        "orderBy": "", "skip": 0, "take": 1000,
    }


def query_notices(names: list[str], session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.post(BASE + "queries", data=json.dumps(_query_body(names)), headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("table", [])


def get_publications(sat_name: str, ntc_id, plan: bool = False, session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    kind = "plans" if plan else "non-plans"
    url = f"{BASE}dashboard/space-stations/publications/{kind}/{requests.utils.quote(sat_name, safe='')}/{ntc_id}/publications"
    r = s.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return (r.json().get("publications") or {}).get("list") or []


def _ranges(tooltip) -> list[tuple[float, float]]:
    if not tooltip:
        return []
    try:
        return [(float(x["f"]), float(x["t"])) for x in json.loads(tooltip).get("ranges", [])]
    except Exception:
        return []


def fetch_networks(names: list[str]) -> dict:
    """Return {sat_name: {"found": bool, "long_nom", "ntc_type", "notices": [...], "pubs": [...]}}."""
    names = [n for n in dict.fromkeys(n.strip() for n in names) if n]
    out = {n: {"found": False, "long_nom": None, "ntc_type": None, "notices": [], "pubs": []} for n in names}
    if not names:
        return out
    s = requests.Session()
    rows = query_notices(names, s)
    for x in rows:
        n = x.get("sat_name")
        if n not in out:
            continue
        d = out[n]
        d["found"] = True
        d["long_nom"] = x.get("long_nom")
        d["ntc_type"] = x.get("ntc_type")
        d["notices"].append({
            "ntc_id": x.get("ntc_id"),
            "ntf_rsn": x.get("ntf_rsn"),
            "prov": x.get("prov"),
            "d_rcv": x.get("d_rcv"),
            "plan": bool(x.get("f_plan")),
            "tx": _ranges(x.get("freq_tooltip_emi")),
            "rx": _ranges(x.get("freq_tooltip_rcp")),
        })

    jobs = [(n, nt) for n, d in out.items() for nt in d["notices"]]

    def work(job):
        n, nt = job
        try:
            return n, get_publications(n, nt["ntc_id"], nt["plan"], s)
        except Exception:
            return n, []

    seen = {n: set() for n in out}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for n, plist in ex.map(work, jobs):
            for p in plist:
                key = (p.get("ssn_ref"), p.get("ssn_no"), p.get("ssn_rev"), p.get("ssn_rev_no"), p.get("wic_no"))
                if key in seen[n]:
                    continue
                seen[n].add(key)
                out[n]["pubs"].append({
                    "ssn_ref": p.get("ssn_ref"), "ssn_no": p.get("ssn_no"), "ssn_rev": p.get("ssn_rev"),
                    "ssn_rev_no": p.get("ssn_rev_no"), "d_rcv": p.get("d_rcv"), "wic_no": p.get("wic_no"),
                    "d_wic": p.get("d_wic"),
                })
    for d in out.values():
        d["pubs"].sort(key=lambda p: (p["wic_no"] or 0))
    return out


def ss_label(p: dict) -> str:
    ref = (p.get("ssn_ref") or "").strip()
    no = p.get("ssn_no")
    s = f"{ref}/{no}" if no not in (None, "") else ref
    rev = (p.get("ssn_rev") or "").strip()
    if rev:
        s += f" {REV_LABEL.get(rev, rev)}-{p.get('ssn_rev_no') or 1}"
    return s
