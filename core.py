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


def pub_rows(name, pos_label, d, ss_types, missing_label="Not yet received by the BR"):
    rows = []
    for p in d["pubs"] if d else []:
        if (p["ssn_ref"] or "").strip() in ss_types:
            rows.append((name, pos_label, ss_label(p), p["d_rcv"] or "-", f"IFIC {p['wic_no']}, {p['d_wic']}"))
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
        t1 += pub_rows(n, fmt_pos(lon(n, p)), data.get(n), ss_types)
    t2 = []
    for n, p in js:
        t2 += pub_rows(n, fmt_pos(lon(n, p)), data.get(n), ss_types)

    t3 = []
    for n_i, p_i in ins:
        li = lon(n_i, p_i)
        groups = {}
        for n, p in js:
            groups.setdefault(lon(n, p), []).append(n)
        for lj, names in sorted(groups.items(), key=lambda kv: (separation(li, kv[0]) is None, separation(li, kv[0]) or 0)):
            sep = separation(li, lj)
            t3.append((f"{n_i} ({fmt_pos(li)})", "\n".join(f"{x} ({fmt_pos(lj)})" for x in names),
                       "-" if sep is None else f"{sep:.1f}"))

    a = analyse(inp, data)
    u = a["union"]
    overlap_lines = []
    lab = inp.get("band_label", "")
    for rs, direction in ((u["se"], "space-to-Earth"), (u["es"], "Earth-to-space"), (u["opp"], "opposite direction")):
        if rs:
            overlap_lines.append(f"{lab + ' band: ' if lab else ''}{join_and([fmt_range(r) for r in rs])} MHz ({direction})")
    ins_band_txt = join_and([x for x in (ranges_txt(a["ins_tx"]) + " (space-to-Earth)" if a["ins_tx"] else "",
                                         ranges_txt(a["ins_rx"]) + " (Earth-to-space)" if a["ins_rx"] else "") if x])
    return {
        "section_no": inp["section_no"], "section_title": inp["section_title"],
        "item_no": inp["item_no"], "item_title": inp["item_title"],
        "t1": t1, "t2": t2, "t3": t3, "overlap_lines": overlap_lines,
        "ins_label": ", ".join(f"{n} ({fmt_pos(lon(n, p))})" for n, p in ins),
        "ins_band_txt": ins_band_txt,
        "band_label": lab,
        "source_note": f"Source: ITU Space Explorer (SNS){', up to ' + inp['ific_label'] if inp.get('ific_label') else ''}.",
        "ss_types": ss_types,
        "discussion": inp.get("discussion", ""),
        "conclusion": inp.get("conclusion", ""),
    }


def _group_title(g, inp):
    names = [n for n, _ in g["nets"]]
    if len(names) <= 4:
        return f"Coordination with {join_and(names)}"
    parts = [ranges_txt(g["se"]), ranges_txt(g["es"])]
    return f"Coordination in the bands {join_and([x for x in parts if x])}"


def draft_discussion(inp: dict, data: dict, comments=None) -> str:
    """Suggested Discussion (editable). '## ' starts a numbered subsection, [[...]] marks text to complete."""
    ss_types = inp.get("ss_types") or DEFAULT_SS_TYPES
    ex = set(inp.get("exclude", []))
    a = analyse(inp, data)
    ins_names = [n for n, _ in inp["ins_nets"]]
    ins_lbl = join_and(ins_names)
    d0 = None
    for n in ins_names:
        if data.get(n) and data[n]["found"]:
            d0 = protection_date(data[n], ss_types)
            break
    paras = []
    if ex:
        paras.append(f"{join_and(sorted(ex))} [[reason, e.g. have exceeded the regulatory time limit and were moved "
                     f"to Other Business]]. These networks are not considered under this agenda item.")
    if a["missing"]:
        paras.append(f"As of {inp.get('ific_label') or '[[BR IFIC No.]]'}, no special section has been published for "
                     f"{join_and(a['missing'])}.")
    paras.append(f"The frequency overlap differs between the {inp.get('j_operator', '')} satellite networks. The "
                 f"coordination is therefore discussed in the following subsections.")
    paras.append("The INS delegation [[general position of the INS delegation]].")

    li = net_lon(ins_names[0], inp["ins_nets"][0][1], data) if ins_names else None
    k = 0
    for g in a["groups"]:
        if not (g["se"] or g["es"] or g["opp"]):
            continue
        k += 1
        names = [n for n, _ in g["nets"]]
        paras.append(f"## {inp['item_no']}.{k}\t{_group_title(g, inp)}")
        ov = []
        if g["se"]:
            ov.append(f"{ranges_txt(g['se'])} (space-to-Earth)")
        if g["es"]:
            ov.append(f"{ranges_txt(g['es'])} (Earth-to-space)")
        if g["opp"]:
            ov.append(f"{ranges_txt(g['opp'])} (opposite direction)")
        txt = f"The frequency assignments of {ins_lbl} overlap with those of {join_and(names)} in {join_and(ov)}."
        if not g["es"] and g["se"]:
            txt += " There is no overlap in the Earth-to-space direction."
        if not g["se"] and g["es"]:
            txt += " There is no overlap in the space-to-Earth direction."
        paras.append(txt)
        by_pos = {}
        for n, p in g["nets"]:
            by_pos.setdefault(net_lon(n, p, data), []).append(n)
        seps = []
        for lj, ns in sorted(by_pos.items(), key=lambda kv: separation(li, kv[0]) or 0):
            sp = separation(li, lj)
            seps.append(f"{sp:.1f}° with {join_and(ns)} ({fmt_pos(lj)})" if sp is not None
                        else f"{join_and(ns)} (NGSO)")
        paras.append(f"The orbital separation{'s are' if len(seps) > 1 else ' is'} {join_and(seps)}.")
        if d0:
            later = [n for n in names if date_key(protection_date(data[n], ss_types)) > date_key(d0)]
            earlier = [n for n in names if n not in later]
            if later and not earlier:
                paras.append(f"{ins_lbl} has an earlier date of receipt ({d0}) than "
                             f"{'all of these networks' if len(later) > 1 else later[0]}.")
            elif earlier and not later:
                paras.append(f"{'All of these networks have' if len(earlier) > 1 else earlier[0] + ' has'} an "
                             f"earlier date of receipt than {ins_lbl} ({d0}).")
            else:
                paras.append(f"{ins_lbl} ({d0}) has an earlier date of receipt than {join_and(later)}, while "
                             f"{join_and(earlier)} have earlier dates of receipt than {ins_lbl}.")
        paras.append("The INS delegation [[position of the INS delegation for this case]].")
        paras.append("The J delegation [[response of the J delegation]].")
    no_ov = [n for g in a["groups"] if not (g["se"] or g["es"] or g["opp"]) for n, _ in g["nets"]]
    if no_ov:
        paras.append(f"## {inp['item_no']}.{k + 1}\tSatellite networks without frequency overlap")
        paras.append(f"Both delegations noted that the frequency assignments of {join_and(no_ov)} do not overlap with "
                     f"those of {ins_lbl} in the band(s) under consideration.")
    return "\n\n".join(paras)


def draft_conclusion(inp: dict, data: dict | None = None) -> str:
    multi_ins = len(inp.get("ins_nets", [])) > 1
    head = (f"Based on the above, both delegations agreed that coordination between the {inp['ins_label']} satellite "
            f"network{'s' if multi_ins else ''} and the {inp['j_operator']} satellite networks listed in Table 2 in "
            f"the {inp['band_label']} band")
    if not data:
        return head + (" [[was completed / was not completed and will be continued via correspondence or at the "
                       "future satellite coordination meeting]].")
    a = analyse(inp, data)
    lines = [head + ":"]
    k = 0
    for g in a["groups"]:
        if not (g["se"] or g["es"] or g["opp"]):
            continue
        letter = "abcdefghijklmnopqrstuvwxyz"[k]
        k += 1
        names = [n for n, _ in g["nets"]]
        who = (f"{join_and(names)} (Section {inp['item_no']}.{k})" if len(names) <= 4
               else f"the networks listed in Section {inp['item_no']}.{k}")
        lines.append(f"{letter})\twith {who} [[was completed / was not completed and "
                     f"will be continued via correspondence or at the future satellite coordination meeting]];")
    if len(lines) > 1:
        lines[-1] = lines[-1].rstrip(";") + "."
    return "\n\n".join(lines)
