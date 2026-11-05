"""Read agenda items from the INS-J draft agenda workbook (one sheet per Indonesian operator)."""
from __future__ import annotations

import re

import openpyxl

ITEM_RE = re.compile(r"^\d+\.\d+\.\d+$")
NET_RE = re.compile(r"([A-Z0-9][A-Z0-9\-\._/]*)\s*\(([^)]+)\)")


def parse_networks(text) -> list[tuple[str, str]]:
    """'JMCS-1 (144E), JMCS-2 (110E)' -> [('JMCS-1','144E'), ...]; bracketed [..] proposals are dropped."""
    if not text:
        return []
    t = re.sub(r"\[[^\]]*\]", " ", str(text))
    out, seen = [], set()
    for name, pos in NET_RE.findall(t):
        if name not in seen:
            seen.add(name)
            out.append((name, pos.strip()))
    return out


def parse_pos(pos: str):
    """'150.5E' -> 150.5, '72W' -> -72, 'NGSO' -> None."""
    m = re.match(r"^\s*([\d.]+)\s*([EW])\s*$", pos or "", re.I)
    if not m:
        return None
    v = float(m.group(1))
    return -v if m.group(2).upper() == "W" else v


def read_agenda(file) -> dict:
    """Return {sheet: [item dict]} for rows whose first column is an item number like 2.2.3."""
    wb = openpyxl.load_workbook(file, data_only=True, read_only=True)
    result = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        comment_headers = {}
        items = []
        for r in rows:
            cells = list(r) + [None] * 14
            # header row with comment column titles (e.g. "J comments (06.08.2026)")
            for ci in range(6, 14):
                v = cells[ci]
                if isinstance(v, str) and "comment" in v.lower():
                    comment_headers[ci] = " ".join(v.split())
            a = cells[0]
            a = str(a).strip() if a is not None else ""
            if not ITEM_RE.match(a):
                continue
            comments = []
            for ci in range(6, 14):
                v = cells[ci]
                if v not in (None, "") and str(v).strip() not in ("-",):
                    comments.append((comment_headers.get(ci, f"Column {ci + 1}"), str(v).strip()))
            items.append({
                "item": a,
                "ins_operator": str(cells[1] or "").strip(),
                "ins_networks": parse_networks(cells[2]),
                "band": " ".join(str(cells[3] or "").split()),
                "j_operator": str(cells[4] or "").strip(),
                "j_networks": parse_networks(cells[5]),
                "comments": comments,
            })
        if items:
            result[ws.title] = items
    return result
