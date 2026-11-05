# Summary Record Generator (INS-J)

Web app that builds one section of the INS-J satellite coordination meeting summary record (.docx) from the
official template, with a live preview of the document beside the form. Deployed on Vercel as a static site plus
one serverless function.

## How it works

- **Browser** (`index.html`, `js/`): reads the draft agenda (.xlsx), computes the tables, overlap and draft text,
  writes the .docx into the template with JSZip and previews it with docx-preview. Nothing is uploaded; the
  template and agenda stay in the browser.
- **`/api/itu`** (`api/itu.js`): small Vercel function that queries the public ITU Space Explorer API (special
  sections, dates of receipt, orbital positions, frequency ranges). It exists only because browsers may not call
  itu.int directly (CORS).

The .docx is generated in the browser on purpose: the template is about 7.7 MB (embedded fonts), above the
4.5 MB request and response limit of Vercel functions.

## Deploy (Vercel)

Import the repo in Vercel with the default settings (Framework preset: Other, no build command). `vercel.json`
gives the ITU function up to 60 s. `streamlit/` and `tests/` are excluded by `.vercelignore`.

Local run: `npx vercel dev`, then open http://localhost:3000.

## Using the app

1. **Template and agenda**: the INS-J template in `templates/` loads by default; another one can be uploaded.
   Upload the draft agenda (.xlsx) to pick a sheet and item. Networks, band and operators fill in automatically.
2. **Agenda item**: everything stays editable. "Agenda comments" shows the INS/J comment history of the row.
3. **ITU Space Explorer data**: choose the band window(s) and click **Fetch from ITU Space Explorer**.
   **Save data** keeps a JSON snapshot; **Load data** reuses one without calling ITU. Tick networks to exclude
   (for example those moved to Other Business).
4. **Text**: headings follow the networks automatically until edited. Discussion and Conclusion are drafted from the
   data: one subsection per overlap group (overlap, minimal orbital separation, BRI assessment, RR Appendix 5
   coordination arc for C/Ku/Ka, counterpart response, agreement, bracketed conclusion).
   - Blank line between paragraphs
   - `## 2.2.3.1<TAB>Title` starts a numbered subsection
   - `a)<TAB>text` is a lettered line
   - `[[text]]` is highlighted yellow (still to be completed)

**Download .docx** saves the document. Form contents and fetched data are kept in the browser between visits.

## Files

| Path | Purpose |
| --- | --- |
| `index.html` | UI |
| `js/core.js` | agenda parsing, overlap analysis, tables, draft text |
| `js/docx.js` | writes the section into the template |
| `js/app.js` | UI logic, ITU fetch, preview |
| `api/itu.js` | Vercel function, ITU Space Explorer proxy |
| `templates/` | INS-J summary record template |
| `vendor/` | JSZip, docx-preview, SheetJS (bundled, no CDN) |
| `streamlit/` | earlier Streamlit version (same logic in Python; `streamlit run streamlit/app.py`) |
| `tests/itu_fixture.json` | ITU data for item 2.2.3 (BR IFIC 3083), usable with **Load data** |
