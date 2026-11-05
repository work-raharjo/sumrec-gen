# Summary Record Generator (INS-J)

Streamlit web app that builds one section of the INS-J satellite coordination meeting summary record
(.docx) from the official template, with a live preview beside the input form.

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. To share it with the team, deploy the folder to Streamlit
Community Cloud or any server that runs Python (Vercel does not run Streamlit).

## How to use

1. **Template and agenda**: the INS-J template is bundled in `templates/`; upload another one to replace it.
   Upload the draft agenda (.xlsx) to pick items from it.
2. **Agenda item**: choose the sheet (operator) and item. Networks, band and operator fill in automatically
   and can be edited. "Agenda comments" shows the INS/J comment history for that row.
3. **ITU Space Explorer data**: choose the band window(s), then click **Fetch from ITU Space Explorer**.
   The app pulls the special sections (AR11/C, CR/C and modifications by default), dates of receipt,
   orbital positions and frequency ranges for every network. Use **Save ITU data** to keep a snapshot
   and **load saved ITU data** to reuse it offline. Exclude networks that moved to Other Business.
4. **Text**: headings, Discussion and Conclusion are drafted from the data and can be edited.
   Write `[[text]]` for anything still to be completed; it comes out highlighted yellow in the docx.

The right side shows the generated document; **Download .docx** saves it.

## What is computed

- Table 1 and 2: special sections per network from the BR IFIC publication history.
- Table 3: geocentric orbital separation, grouped by orbital position.
- Table 4: overlapping ranges per Japanese network (same direction, plus opposite direction when present),
  from the coordination and notification notices, limited to the chosen band window(s).
- Discussion draft: networks not yet published, and which Japanese networks were received by the BR
  after the Indonesian network.

## Files

- `app.py` Streamlit UI
- `itu.py` ITU Space Explorer client (public endpoints, no login)
- `agenda.py` draft agenda reader
- `core.py` tables, overlap and text drafting
- `docx_builder.py` writes the section into the template
- `tests/` offline check with saved ITU data (`python tests/run_offline.py <agenda.xlsx> out.docx`)
