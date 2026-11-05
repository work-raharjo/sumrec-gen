"""Turn ITU data plus agenda input into the content of one summary-record section."""
from __future__ import annotations

from datetime import datetime

from itu import ss_label

BANDS = {  # MHz windows used to keep the overlap to the band(s) of the agenda item
    "L": [(1000, 2000)],
    "S": [(2000, 2700)],
    "C": [(3400, 7075)],
    "X": [(7075, 8500)],
    "Ku": [(10700, 15400)],
    "Ka": [(17300, 31000)],
    "Q/V": [(37500, 52400)],
    "V": [(42500, 52400)],
}

DEFAULT_SS_TYPES = ["AR11/C", "CR/C"]


def fmt_num(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    ip, _, dp = s.partition(".")
    neg = ip.startswith("-")
    ip = ip.lstrip("-")
    groups = []
    while len(ip) > 3:
        groups.insert(0, ip[-3:])
        ip = ip[:-3]
    groups.insert(0, ip)
    out = ("-" if neg else "") + " ".join(groups)
    return out + ("." + dp if dp else "")


def fmt_range(r) -> str:
    return f"{fmt_num(r[0])} – {fmt_num(r[1])}"


def fmt_pos(lon) -> str:
    if lon is None:
        return "NGSO"
    s = f"{abs(lon):g}"
    return s + ("E" if lon >= 0 else "W")


def merge(ranges):
    out = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def intersect(r1, r2):
    out = []
    for a, b in r1:
        for c, d in r2:
            lo, hi = max(a, c), min(b, d)
            if hi > lo:
                out.append((lo, hi))
    return merge(out)


def windows_for(bands: list[str], custom: list[tuple[float, float]]):
    w = []
    for b in bands:
        w += BANDS.get(b, [])
    w += custom
    return merge(w) if w else [(0, 1e9)]


def net_ranges(d: dict):
    """Union of Tx and Rx ranges over coordination (C) and notification (N) notices; falls back to all notices."""
    ns = [n for n in d["notices"] if n["ntf_rsn"] in ("C", "N")] or d["notices"]
    tx = merge([r for n in ns for r in n["tx"]])
    rx = merge([r for n in ns for r in n["rx"]])
    return tx, rx


def separation(a, b):
    if a is None or b is None:
        return None
    v = abs(a - b) % 360
    return min(v, 360 - v)


def date_key(s):
    try:
        return datetime.strptime(s, "%d.%m.%Y")
    except Exception:
        return datetime.max


def ific_txt(p):
    return f"IFIC{p['wic_no']}\n{p['d_wic']}"


def pub_rows(name, pos_label, d, ss_types, missing_label="Not yet received by the BR", list_mods=False):
    """One row per network with its base coordination special section (earliest date of receipt);
    with list_mods=True every special section of the selected types (incl. modifications) is listed."""
    rows = []
    cand = [p for p in (d["pubs"] if d else []) if (p["ssn_ref"] or "").strip() in ss_types]
    if not list_mods and cand:
        base = [p for p in cand if not (p.get("ssn_rev") or "").strip()] or cand
        cand = [min(base, key=lambda p: (date_key(p["d_rcv"]), p["wic_no"] or 0))]
    for p in cand:
        rows.append((name, pos_label, ss_label(p), p["d_rcv"] or "-", ific_txt(p)))
    if not rows:
        rows.append((name, pos_label, missing_label if not (d and d["found"]) else "No matching special section", "-", "-"))
    return rows


def protection_date(d, ss_types):
    """Earliest date of receipt among the selected coordination special sections."""
    ds = [p["d_rcv"] for p in d["pubs"] if (p["ssn_ref"] or "").strip() in ss_types and p["d_rcv"]]
    if not ds:
        ds = [n["d_rcv"] for n in d["notices"] if n["d_rcv"]]
    return min(ds, key=date_key) if ds else None


def net_lon(name, pos_txt, data):
    d = data.get(name)
    if d and d["found"] and d["long_nom"] is not None and d["ntc_type"] == "G":
        return float(d["long_nom"])
    from agenda import parse_pos
    return parse_pos(pos_txt)


def join_and(xs):
    xs = list(xs)
    if not xs:
        return ""
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def ranges_txt(rs):
    return join_and([fmt_range(r) for r in rs]) + " MHz" if rs else ""


def analyse(inp: dict, data: dict) -> dict:
    """Overlap per Japanese network, grouped by identical overlap, plus the union over all networks."""
    win = windows_for(inp.get("bands", []), inp.get("custom_ranges", []))
    ins = list(inp["ins_nets"])
    js = [(n, p) for n, p in inp["j_nets"] if n not in set(inp.get("exclude", []))]
    ins_tx = merge([r for n, _ in ins if data.get(n) for r in net_ranges(data[n])[0]])
    ins_rx = merge([r for n, _ in ins if data.get(n) for r in net_ranges(data[n])[1]])
    ins_tx_w, ins_rx_w = intersect(ins_tx, win), intersect(ins_rx, win)
    groups, missing = {}, []
    u_se, u_es, u_opp = [], [], []
    for n, p in js:
        d = data.get(n)
        if not d or not d["found"]:
            missing.append(n)
            continue
        tx, rx = net_ranges(d)
        se, es = intersect(tx, ins_tx_w), intersect(rx, ins_rx_w)
        opp = merge(intersect(tx, ins_rx_w) + intersect(rx, ins_tx_w))
        u_se += se; u_es += es; u_opp += opp
        groups.setdefault((tuple(se), tuple(es), tuple(opp)), []).append((n, p))
    glist = [{"nets": v, "se": list(k[0]), "es": list(k[1]), "opp": list(k[2])} for k, v in groups.items()]
    # widest overlap first, then networks without any overlap last
    glist.sort(key=lambda g: (not (g["se"] or g["es"] or g["opp"]),
                              -sum(b - a for a, b in g["se"] + g["es"] + g["opp"])))
    return {"ins_tx": ins_tx_w, "ins_rx": ins_rx_w, "groups": glist, "missing": missing,
            "union": {"se": merge(u_se), "es": merge(u_es), "opp": merge(u_opp)}}


def build_content(inp: dict, data: dict) -> dict:
    """inp keys: section_no, section_title, item_no, item_title, ins_nets [(name,pos)], j_nets [(name,pos)],
    exclude [names], bands [..], custom_ranges [(lo,hi)], ss_types [..], ific_label, discussion, conclusion."""
    ss_types = inp.get("ss_types") or DEFAULT_SS_TYPES
    ins = list(inp["ins_nets"])
    js = [(n, p) for n, p in inp["j_nets"] if n not in set(inp.get("exclude", []))]
    lon = lambda n, p: net_lon(n, p, data)

    t1 = []
    for n, p in ins:
        t1 += pub_rows(n, fmt_pos(lon(n, p)), data.get(n), ss_types, list_mods=inp.get("list_mods", False))
    t2 = []
    for n, p in js:
        t2 += pub_rows(n, fmt_pos(lon(n, p)), data.get(n), ss_types, list_mods=inp.get("list_mods", False))

    t3 = []
    for n_i, p_i in ins:
        li = lon(n_i, p_i)
        for n, p in js:
            sep = separation(li, lon(n, p))
            t3.append((n_i, n, "-" if sep is None else f"{sep:g}"))

    a = analyse(inp, data)
    u = a["union"]
    lab = inp.get("band_label", "")
    freq_rows = []
    for rs, direction in ((u["se"], "space-to-Earth"), (u["es"], "Earth-to-space"), (u["opp"], "opposite")):
        for r in rs:
            freq_rows.append(f"{fmt_range(r)} MHz in the {direction} direction, as appropriate;")
    j_list = ", ".join(f"{n} ({fmt_pos(lon(n, p))})" for n, p in js)
    return {
        "section_no": inp["section_no"], "section_title": inp["section_title"],
        "item_no": inp["item_no"], "item_title": inp["item_title"],
        "t1": t1, "t2": t2, "t3": t3, "freq_rows": freq_rows, "j_list": j_list,
        "ins_label": ", ".join(f"{n} ({fmt_pos(lon(n, p))})" for n, p in ins),
        "band_label": lab,
        "source_note": f"Source: ITU Space Explorer (SNS){', up to ' + inp['ific_label'] if inp.get('ific_label') else ''}.",
        "ss_types": ss_types,
        "discussion": inp.get("discussion", ""),
        "conclusion": inp.get("conclusion", ""),
    }


def net_list(nets, data):
    """'A (144E), B (158E), C (162E)' as in the INS-J summary records."""
    return ", ".join(f"{n} ({fmt_pos(net_lon(n, p, data))})" for n, p in nets)


def sn(nets):
    return "satellite networks" if len(nets) > 1 else "satellite network"


def _group_title(g, inp, data):
    ins = net_list(inp["ins_nets"], data)
    if len(g["nets"]) <= 6:
        return f"Coordination between the {ins} satellite network and the {net_list(g['nets'], data)} {sn(g['nets'])}"
    parts = [ranges_txt(g["se"]), ranges_txt(g["es"])]
    return (f"Coordination between the {ins} satellite network and the satellite networks overlapping in "
            f"{join_and([x for x in parts if x])}")


# RR Appendix 5, Table 5-1 coordination arcs (GSO/GSO, No. 9.7) for the common FSS bands
COORD_ARC = {"C": 7, "Ku": 6, "Ka": 8}


def draft_discussion(inp: dict, data: dict, comments=None) -> str:
    """Suggested Discussion (editable). '## ' starts a numbered subsection, [[...]] marks text to complete.
    Subsection wording follows the BRI coordination agreements (e.g. BRI-ADoD)."""
    ex = set(inp.get("exclude", []))
    a = analyse(inp, data)
    ins_names = [n for n, _ in inp["ins_nets"]]
    ins = net_list(inp["ins_nets"], data)
    band = inp.get("band_label", "")
    bandB = f"{band}-Band" if band else "band"
    me = inp.get("ins_short") or "BRI"
    them = inp.get("j_operator") or "the J delegation"
    paras = []
    if ex:
        exn = [(n, p) for n, p in inp["j_nets"] if n in ex]
        paras.append(f"The {net_list(exn, data)} satellite networks [[reason, e.g. have exceeded the regulatory time "
                     f"limit and were moved to Other Business]]. These satellite networks are not considered under "
                     f"this agenda item.")
    if a["missing"]:
        paras.append(f"As of {inp.get('ific_label') or '[[BR IFIC No.]]'}, no special section has been published for "
                     f"the {', '.join(a['missing'])} satellite network{'s' if len(a['missing']) > 1 else ''}.")
    groups = [g for g in a["groups"] if g["se"] or g["es"] or g["opp"]]
    if len(groups) > 1:
        paras.append(f"Since the frequency overlap differs between the {them} satellite networks, the coordination is "
                     f"discussed in the following subsections.")

    li = net_lon(ins_names[0], inp["ins_nets"][0][1], data) if ins_names else None
    arc = COORD_ARC.get(band)
    for k, g in enumerate(groups, 1):
        lst = net_list(g["nets"], data)
        many = len(g["nets"]) > 1
        SN = "Satellite Networks" if many else "Satellite Network"
        sn_ = "satellite networks" if many else "satellite network"
        paras.append(f"## {inp['item_no']}.{k}\tCoordination between {ins} Satellite Network and the {lst} {SN} "
                     f"in the {bandB}")
        ov = []
        if g["se"]:
            ov.append(f"{ranges_txt(g['se'])} in the space-to-Earth direction")
        if g["es"]:
            ov.append(f"{ranges_txt(g['es'])} in the Earth-to-space direction")
        if g["opp"]:
            ov.append(f"{ranges_txt(g['opp'])} in the opposite direction")
        paras.append(f"Both parties confirmed that the frequency overlap between {ins} Satellite Network and the {lst} "
                     f"{sn_} in the {bandB} occurred in {join_and(ov)}.")
        seps = [separation(li, net_lon(n, p, data)) for n, p in g["nets"]]
        seps = [x for x in seps if x is not None]
        min_sep = min(seps) if seps else None
        if min_sep is not None:
            if many:
                paras.append(f"Both parties confirmed that the minimal orbital separations between {ins} Satellite "
                             f"Network and the {lst} satellite networks are greater than and equal to {min_sep:g}°.")
            else:
                paras.append(f"Both parties confirmed that the orbital separation between {ins} Satellite Network and "
                             f"the {lst} satellite network is {min_sep:g}°.")
        paras.append(f"[[{me} believed that the unacceptable interference between those satellite networks is minimal "
                     f"and the orbital separations are considered adequate to avoid any harmful interference between "
                     f"those satellite networks in the {bandB}.]]")
        if arc and min_sep is not None and min_sep >= arc:
            paras.append(f"[[{me} also believed that the condition is also met in accordance with the threshold of arc "
                         f"coordination as governed in ITU Radio Regulations, Appendix 5, Table 5-1 for the {bandB} "
                         f"frequency spectrum coordination ± {arc}°. Therefore, the coordination between these "
                         f"satellite networks could be considered as complete coordination.]]")
        paras.append(f"{them} [[agreed with the proposal that coordination between the {me} and {them} satellite "
                     f"networks can be considered complete / response of {them}]].")
        paras.append(f"[[{me} agreed to complete the satellite coordination between {ins} Satellite Network and the "
                     f"{lst} {SN} in the {bandB}.]]")
        paras.append(f"[Conclusion: Based on the above, coordination between {ins} Satellite Network and the {lst} "
                     f"{sn_} in the {bandB} [[can be considered complete / will be continued via correspondence or at "
                     f"the future satellite coordination meeting]]]")
    no_ov = [(n, p) for g in a["groups"] if not (g["se"] or g["es"] or g["opp"]) for n, p in g["nets"]]
    if no_ov:
        k = len(groups) + 1
        paras.append(f"## {inp['item_no']}.{k}\tCoordination between {ins} Satellite Network and the "
                     f"{net_list(no_ov, data)} Satellite Network{'s' if len(no_ov) > 1 else ''} in the {bandB}")
        paras.append(f"Both parties confirmed that there is no frequency overlap between {ins} Satellite Network and "
                     f"the {net_list(no_ov, data)} satellite network{'s' if len(no_ov) > 1 else ''} in the {bandB}. "
                     f"Therefore, coordination is not required.")
    return "\n\n".join(paras)


def draft_conclusion(inp: dict, data: dict | None = None) -> str:
    data = data or {}
    ins = net_list(inp["ins_nets"], data)
    band = inp.get("band_label", "")
    outcome = ("[[was completed/was not completed and will be continued via correspondence or at the future "
               "satellite coordination meeting]]")
    a = analyse(inp, data) if data else {"groups": []}
    groups = [g for g in a["groups"] if g["se"] or g["es"] or g["opp"]]
    if len(groups) <= 1:
        js = [(n, p) for n, p in inp["j_nets"] if n not in set(inp.get("exclude", []))]
        return (f"Based on the above, both delegations agreed that coordination between the {ins} satellite network "
                f"and the {net_list(js, data)} {sn(js)} in the {band} band {outcome}.")
    lines = [f"Based on the above, both delegations agreed that coordination between the {ins} satellite network and "
             f"the following satellite networks in the {band} band:"]
    for k, g in enumerate(groups, 1):
        letter = "abcdefghijklmnopqrstuvwxyz"[k - 1]
        who = (f"the {net_list(g['nets'], data)} {sn(g['nets'])}" if len(g["nets"]) <= 6
               else "the satellite networks")
        end = ";" if k < len(groups) else "."
        lines.append(f"{letter})\t{who} in Section {inp['item_no']}.{k} {outcome}{end}")
    return "\n\n".join(lines)
