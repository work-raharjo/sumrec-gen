"""Summary Record Generator (INS-J satellite coordination meeting).

Left: pick an agenda item, fetch ITU Space Explorer data, edit the text.
Right: live preview of the generated .docx and a download button.

Run:  streamlit run app.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import mammoth
import streamlit as st
import streamlit.components.v1 as components

from agenda import parse_networks, read_agenda
from core import BANDS, DEFAULT_SS_TYPES, build_content, draft_conclusion, draft_discussion
from docx_builder import build_docx
from itu import fetch_networks

APP_DIR = Path(__file__).parent
DEFAULT_TEMPLATE = APP_DIR / "templates" / "Template_summary_record_INS-J_2026.docx"
OPERATOR_NAMES = {
    "BRI": "PT Bank Rakyat Indonesia (Persero) Tbk",
}
SS_CHOICES = ["AR11/C", "CR/C", "AR11/A", "API/A", "API/C", "CR/D", "CR/E", "RES49", "PART I-S", "PART II-S"]

st.set_page_config(page_title="Summary Record Generator", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.2rem;max-width:100%}
div[data-testid="stTextArea"] textarea{font-size:0.85rem}
</style>""", unsafe_allow_html=True)
st.title("Summary Record Generator")
st.caption("INS-J satellite coordination meeting. Text inside [[double brackets]] is highlighted yellow in the docx.")


@st.cache_data(ttl=3600, show_spinner=False)
def itu_fetch(names: tuple[str, ...]) -> dict:
    return fetch_networks(list(names))


@st.cache_data(show_spinner=False)
def load_agenda(data: bytes) -> dict:
    import io
    return read_agenda(io.BytesIO(data))


def nets_to_text(nets):
    return "\n".join(f"{n} ({p})" for n, p in nets)


def text_to_nets(txt):
    return parse_networks(txt.replace("\n", ", "))


ss = st.session_state
for k, v in {"item_no": "2.2.1", "ins_op": "", "ins_nets": "", "j_op": "", "j_nets": "", "band_txt": "",
             "bands": []}.items():
    ss.setdefault(k, v)
left, right = st.columns([1, 1.15], gap="large")

with left:
    # 1. Files
    with st.expander("1. Template and agenda", expanded=True):
        tpl_up = st.file_uploader("Summary record template (.docx)", type=["docx"])
        if tpl_up:
            ss.template = tpl_up.getvalue()
        elif "template" not in ss and DEFAULT_TEMPLATE.exists():
            ss.template = DEFAULT_TEMPLATE.read_bytes()
        st.caption("Using: " + (tpl_up.name if tpl_up else DEFAULT_TEMPLATE.name if DEFAULT_TEMPLATE.exists()
                                else "no template yet"))
        ag_up = st.file_uploader("Draft agenda (.xlsx), optional", type=["xlsx"])
        agenda = load_agenda(ag_up.getvalue()) if ag_up else {}

    # 2. Agenda item
    with st.expander("2. Agenda item", expanded=True):
        item = None
        if agenda:
            c1, c2 = st.columns([1, 2])
            sheet = c1.selectbox("Sheet", list(agenda))
            items = agenda[sheet]
            labels = [f"{x['item']} | {x['ins_operator']} | {', '.join(n for n, _ in x['ins_networks'])} | "
                      f"{x['band']} | {x['j_operator']}" for x in items]
            idx = c2.selectbox("Item", range(len(items)), format_func=lambda i: labels[i])
            item = items[idx]
            key = f"{sheet}|{item['item']}"
            if ss.get("loaded_item") != key:  # load agenda values into the editable fields
                ss.loaded_item = key
                ss.item_no = item["item"]
                ss.ins_op = OPERATOR_NAMES.get(item["ins_operator"], item["ins_operator"])
                ss.ins_nets = nets_to_text(item["ins_networks"])
                ss.j_op = item["j_operator"]
                ss.j_nets = nets_to_text(item["j_networks"])
                ss.band_txt = item["band"]
                ss.bands = [b for b in BANDS if re.search(rf"(^|[ ,]){re.escape(b)}($|[ ,])", item["band"])]
                ss.pop("itu", None)
                ss.pop("discussion", None)
                ss.pop("conclusion", None)
            if item["comments"]:
                with st.popover("Agenda comments"):
                    for h, v in item["comments"]:
                        st.markdown(f"**{h}**")
                        st.text(v)

        c1, c2 = st.columns([1, 2])
        item_no = c1.text_input("Item no.", key="item_no")
        ins_op = c2.text_input("Indonesian operator (as written in the heading)", key="ins_op")
        ins_nets_txt = st.text_area("Indonesian network(s), one per line: NAME (POS)", key="ins_nets", height=68)
        c1, c2 = st.columns([1, 2])
        j_op = c1.text_input("Japanese operator", key="j_op")
        band_txt = c2.text_input("Band label (used in headings)", key="band_txt")
        j_nets_txt = st.text_area("Japanese network(s), one per line: NAME (POS)", key="j_nets", height=140)
        ins_nets, j_nets = text_to_nets(ins_nets_txt or ""), text_to_nets(j_nets_txt or "")

    # 3. ITU data
    with st.expander("3. ITU Space Explorer data", expanded=True):
        c1, c2 = st.columns([1, 1])
        bands = c1.multiselect("Band window(s) for the overlap", list(BANDS), key="bands")
        custom = c2.text_input("Extra ranges in MHz (e.g. 7250-7750; 7900-8400)", value="")
        custom_ranges = []
        for m in re.finditer(r"([\d.]+)\s*-\s*([\d.]+)", custom):
            custom_ranges.append((float(m.group(1)), float(m.group(2))))
        ss_types = st.multiselect("Special sections to list in Tables 1 and 2", SS_CHOICES, default=DEFAULT_SS_TYPES)
        ific_label = st.text_input("Data cut-off label", value="BR IFIC [[No. (date)]]",
                                   help="Shown in source notes, e.g. 'BR IFIC 3083 (27.10.2026)'")
        names = tuple(n for n, _ in ins_nets + j_nets)
        if st.button("Fetch from ITU Space Explorer", type="primary", disabled=not names):
            with st.spinner(f"Querying {len(names)} networks..."):
                try:
                    ss.itu = itu_fetch(names)
                    ss.pop("discussion", None)
                    ss.pop("conclusion", None)
                except Exception as e:
                    st.error(f"ITU request failed: {e}")
        cache_up = st.file_uploader("Or load saved ITU data (.json)", type=["json"])
        if cache_up and ss.get("itu_file") != cache_up.file_id:
            ss.itu_file = cache_up.file_id
            ss.itu = json.loads(cache_up.getvalue())
            ss.pop("discussion", None)
            ss.pop("conclusion", None)
        itu = ss.get("itu", {})
        if itu:
            found = [n for n in names if itu.get(n, {}).get("found")]
            missing = [n for n in names if n not in found]
            st.success(f"{len(found)} of {len(names)} networks found in SNS.")
            if missing:
                st.warning("Not found: " + ", ".join(missing))
            st.download_button("Save ITU data (.json)", json.dumps(itu, indent=1), "itu_data.json",
                               mime="application/json")
        exclude = st.multiselect("Exclude from this item (e.g. moved to Other Business)", [n for n, _ in j_nets])

    # 4. Text
    inp = {
        "section_no": ".".join(item_no.split(".")[:2]),
        "section_title": f"Coordination between {ins_op} satellite network(s) and {j_op} satellite network(s)",
        "item_no": item_no,
        "item_title": (f"Coordination between the {', '.join(f'{n} ({p})' for n, p in ins_nets)} satellite network "
                       f"and the {j_op} satellite networks in the {band_txt} band"),
        "ins_nets": ins_nets, "j_nets": j_nets, "exclude": exclude, "bands": bands, "custom_ranges": custom_ranges,
        "ss_types": ss_types, "ific_label": ific_label, "band_label": band_txt, "j_operator": j_op,
        "ins_label": ", ".join(f"{n} ({p})" for n, p in ins_nets),
    }
    with st.expander("4. Headings, Discussion and Conclusion", expanded=True):
        inp["section_title"] = st.text_input(f"Heading {inp['section_no']}", value=inp["section_title"])
        inp["item_title"] = st.text_area(f"Heading {item_no}", value=inp["item_title"], height=68)
        if "discussion" not in ss:
            ss.discussion = draft_discussion(inp, itu)
        if "conclusion" not in ss:
            ss.conclusion = draft_conclusion(inp, itu)
        if st.button("Redraft Discussion and Conclusion from data"):
            ss.discussion = draft_discussion(inp, itu)
            ss.conclusion = draft_conclusion(inp, itu)
        inp["discussion"] = st.text_area("Discussion (blank line between paragraphs; \"## 2.2.3.1<TAB>Title\" starts a subsection)", key="discussion", height=260)
        inp["conclusion"] = st.text_area("Conclusion", key="conclusion", height=110)

# Preview
with right:
    if not ss.get("template"):
        st.info("Upload the summary record template to start.")
    elif not (ins_nets and j_nets):
        st.info("Fill in the networks (or pick an agenda item) to see the preview.")
    else:
        content = build_content(inp, ss.get("itu", {}))
        docx_bytes = build_docx(ss.template, content)
        fname = f"Summary Record {item_no} {'-'.join(n for n, _ in ins_nets)} vs {j_op.replace('/', '-')} {band_txt}.docx"
        c1, c2 = st.columns([3, 1])
        c1.subheader("Preview")
        c2.download_button("Download .docx", docx_bytes, fname, type="primary",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        import io
        html = mammoth.convert_to_html(io.BytesIO(docx_bytes), style_map="highlight[color='yellow'] => mark").value
        page = f"""<html><head><style>
        body{{background:#e9ecef;margin:0;padding:16px;font-family:Arial,Helvetica,sans-serif}}
        .page{{background:#fff;max-width:816px;margin:0 auto;padding:56px 72px;box-shadow:0 1px 4px rgba(0,0,0,.2);
              font-size:12pt;line-height:1.35;color:#000}}
        h3{{font-size:12pt;margin:14px 0 8px}} h4{{font-size:12pt;text-decoration:underline;margin:14px 0 6px}}
        p{{text-align:justify;margin:6px 0}}
        table{{border-collapse:collapse;width:100%;margin:6px 0 4px;font-size:9pt}}
        td,th{{border:1px solid #000;padding:2px 5px;vertical-align:middle}}
        td p,th p{{text-align:center;margin:0}} th{{background:#d9d9d9;font-weight:bold}} td:first-child p{{text-align:left}}
        mark{{background:#ffff00}}
        </style></head><body><div class="page">{html}</div></body></html>"""
        if hasattr(st, "iframe"):
            st.iframe(page, height=1150)
        else:  # older Streamlit
            components.html(page, height=1150, scrolling=True)
