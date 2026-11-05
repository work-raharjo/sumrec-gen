"""Offline end-to-end check: agenda xlsx + saved ITU data -> docx."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from agenda import read_agenda
from core import build_content, draft_discussion, draft_conclusion
from docx_builder import build_docx

ag = read_agenda(sys.argv[1])
print({k: [i["item"] for i in v] for k, v in ag.items()})
it = next(i for i in ag["BRI"] if i["band"] == "X" and i["j_operator"] == "MoD/MCC")
print(it["item"], it["band"], len(it["j_networks"]), it["comments"][:2])
data = json.loads(Path(__file__).with_name("itu_fixture.json").read_text())
inp = {"section_no": "2.2", "section_title": "Coordination between PT Bank Rakyat Indonesia (Persero) Tbk satellite network(s) and MoD/MCC satellite network(s)",
       "item_no": "2.2.3", "item_title": "Coordination between the NUSANTARA-BR1-E (150.5E) satellite network and the MoD/MCC satellite networks in the X band",
       "ins_nets": it["ins_networks"], "j_nets": it["j_networks"], "exclude": ["JMCS-5A", "JMCS-5D"], "bands": ["X"],
       "custom_ranges": [], "ss_types": ["AR11/C", "CR/C"], "ific_label": "BR IFIC 3083 (27.10.2026)", "band_label": "X",
       "j_operator": "MoD/MCC", "ins_label": "NUSANTARA-BR1-E (150.5E)"}
inp["discussion"] = draft_discussion(inp, data)
inp["conclusion"] = draft_conclusion(inp, data)
print("---DISCUSSION---\n" + inp["discussion"])
c = build_content(inp, data)
print(c["overlap_lines"])
print(c["ins_band_txt"])
tpl = Path(__file__).parent.parent / "templates" / "Template_summary_record_INS-J_2026.docx"
Path(sys.argv[2]).write_bytes(build_docx(tpl.read_bytes(), c))
print("written", sys.argv[2])
