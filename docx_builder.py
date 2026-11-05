"""Write one summary-record section into the INS-J template (.docx), keeping its styles, page setup and footer.

The template body (format guide and notes) is replaced; text inside [[...]] is highlighted yellow.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

FONT = '<w:rFonts w:ascii="Arial" w:eastAsia="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
BORDER = ('<w:tblBorders>' + ''.join(
    f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
    for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>')
PAGE_W = 8640  # text width of the template (Letter, 1.25" side margins)


def rpr(b=False, u=False, hl=False, sz=24, color=None, i_off=False):
    s = FONT
    if b:
        s += '<w:b/><w:bCs/>'
    if i_off:
        s += '<w:i w:val="0"/><w:iCs w:val="0"/>'
    if color:
        s += f'<w:color w:val="{color}"/>'
    s += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    if hl:
        s += '<w:highlight w:val="yellow"/>'
    if u:
        s += '<w:u w:val="single"/>'
    return '<w:rPr>' + s + '</w:rPr>'


def runs(text, **kw):
    out = ''
    for part in re.split(r'(\[\[.*?\]\])', text):
        if not part:
            continue
        hl = part.startswith('[[')
        t = part[2:-2] if hl else part
        out += '<w:r>' + rpr(hl=hl, **kw) + '<w:t xml:space="preserve">' + escape(t) + '</w:t></w:r>'
    return out


def para(text, jc='both', spacing=None, b=False, u=False, sz=24, keep=False):
    ppr = '<w:keepNext/>' if keep else ''
    if spacing:
        ppr += f'<w:spacing w:before="{spacing[0]}" w:after="{spacing[1]}"/>'
    ppr += f'<w:jc w:val="{jc}"/>' + rpr(b=b, u=u, sz=sz)
    return '<w:p><w:pPr>' + ppr + '</w:pPr>' + runs(text, b=b, u=u, sz=sz) + '</w:p>'


def empty():
    return '<w:p><w:pPr><w:jc w:val="both"/>' + rpr() + '</w:pPr></w:p>'


def h3(num, text):
    rp = rpr(color='000000')
    return ('<w:p><w:pPr><w:pStyle w:val="Heading3"/><w:ind w:left="1134" w:hanging="1134"/><w:jc w:val="both"/>'
            + rp + '</w:pPr><w:r>' + rp + f'<w:t>{escape(num)}</w:t><w:tab/>'
            + f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def h4(text):
    rp = rpr(i_off=True, color='000000', u=True)
    return ('<w:p><w:pPr><w:pStyle w:val="Heading4"/><w:jc w:val="both"/>' + rp + '</w:pPr><w:r>' + rp
            + f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def caption(text):
    return para(text, jc='center', b=True, u=True, keep=True)


def cell(text, w, sz=24, b=False, jc='center', vmerge=None, shade=None):
    tcpr = f'<w:tcW w:w="{w}" w:type="dxa"/>'
    if vmerge == 'restart':
        tcpr += '<w:vMerge w:val="restart"/>'
    elif vmerge == 'cont':
        tcpr += '<w:vMerge/>'
    if shade:
        tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>'
    tcpr += '<w:vAlign w:val="center"/>'
    ps = ''
    for ln in (text.split('\n') if text else ['']):
        ps += (f'<w:p><w:pPr><w:spacing w:before="20" w:after="20"/><w:jc w:val="{jc}"/>' + rpr(b=b, sz=sz)
               + '</w:pPr>' + (runs(ln, b=b, sz=sz) if ln else '') + '</w:p>')
    return '<w:tc><w:tcPr>' + tcpr + '</w:tcPr>' + ps + '</w:tc>'


def table(widths, header, rows, merge_cols=(), left_cols=(), sz=24):
    tw = sum(widths)
    x = (f'<w:tbl><w:tblPr><w:tblW w:w="{tw}" w:type="dxa"/><w:jc w:val="center"/>' + BORDER
         + '<w:tblLayout w:type="fixed"/><w:tblLook w:val="0400" w:firstRow="0" w:lastRow="0" w:firstColumn="0" '
           'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>'
         + ''.join(f'<w:gridCol w:w="{w}"/>' for w in widths) + '</w:tblGrid>')
    x += '<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' + ''.join(
        cell(h, w, sz=sz) for h, w in zip(header, widths)) + '</w:tr>'
    for ri, r in enumerate(rows):
        x += '<w:tr><w:trPr><w:cantSplit/></w:trPr>'
        for ci, (v, w) in enumerate(zip(r, widths)):
            vm = None
            if ci in merge_cols:
                keys = [k for k in merge_cols if k <= ci]
                same = ri > 0 and all(rows[ri - 1][k] == r[k] for k in keys)
                nxt = ri + 1 < len(rows) and all(rows[ri + 1][k] == r[k] for k in keys)
                if same:
                    vm, v = 'cont', ''
                elif nxt:
                    vm = 'restart'
            x += cell(v, w, sz=sz, jc='left' if ci in left_cols else 'center', vmerge=vm)
        x += '</w:tr>'
    return x + '</w:tbl>'


def list_para(text, spacing=(0, 60)):
    """'a)<TAB>text' paragraph with a hanging indent."""
    return ('<w:p><w:pPr>' + f'<w:spacing w:before="{spacing[0]}" w:after="{spacing[1]}"/>'
            + '<w:ind w:left="720" w:hanging="360"/><w:jc w:val="both"/>' + rpr() + '</w:pPr>'
            + ''.join(runs(t) + ('<w:r>' + rpr() + '<w:tab/></w:r>' if i == 0 and '\t' in text else '')
                      for i, t in enumerate(text.split('\t', 1))) + '</w:p>')


def subheading(text):
    """'2.2.3.1<TAB>Title' -> bold numbered subsection heading inside Discussion."""
    num, _, title = text.partition('\t')
    if not title:
        num, _, title = text.partition(' ')
    rp = rpr(b=True)
    return ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:ind w:left="1134" w:hanging="1134"/>'
            '<w:jc w:val="both"/>' + rp + '</w:pPr><w:r>' + rp + f'<w:t>{escape(num.strip())}</w:t><w:tab/>'
            + f'<w:t xml:space="preserve">{escape(title.strip())}</w:t></w:r></w:p>')


def rich_text(text):
    """Blank line separates paragraphs. '## ' starts a subsection heading, 'a)<TAB>' or 'a) ' a lettered line."""
    out = ''
    for p in [p.strip() for p in re.split(r'\n\s*\n', text or '') if p.strip()]:
        if p.startswith('## '):
            out += subheading(p[3:].strip())
        elif re.match(r'^[a-z]\)[\t ]', p):
            out += list_para(p[:2] + '\t' + ' '.join(p[3:].split()), spacing=(0, 80))
        else:
            out += para(' '.join(p.split()), spacing=(0, 200))
    return out


def band_block(label, rows):
    """Borderless 'X-Band : <range> in the ... direction, as appropriate;' block (reference layout)."""
    nb = ('<w:tblBorders>' + ''.join(f'<w:{x} w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
          for x in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>')

    def tc(w, paras_txt):
        ps = ''.join('<w:p><w:pPr><w:spacing w:before="120" w:after="120"/><w:jc w:val="both"/>' + rpr()
                     + '</w:pPr>' + runs(t) + '</w:p>' for t in paras_txt)
        return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/></w:tcPr>{ps}</w:tc>'
    return ('<w:tbl><w:tblPr><w:tblW w:w="9006" w:type="dxa"/>' + nb + '<w:tblLayout w:type="fixed"/>'
            '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" w:noHBand="0" '
            'w:noVBand="1"/></w:tblPr><w:tblGrid><w:gridCol w:w="1526"/><w:gridCol w:w="567"/><w:gridCol w:w="6913"/>'
            '</w:tblGrid><w:tr>' + tc(1526, [label]) + tc(567, [':']) + tc(6913, rows) + '</w:tr></w:tbl>')


def section_xml(c: dict) -> str:
    W5 = [2450, 1150, 1700, 1550, 1775]
    body = h3(c['section_no'], c['section_title']) + h3(c['item_no'], c['item_title'])

    body += h4('ITU Publications')
    body += para('The coordination between the satellite networks of the Administrations of Indonesia and Japan was '
                 'considered based on the following ITU publications.', spacing=(240, 240))
    body += caption('Table 1. The Indonesian satellite network(s)')
    body += table(W5, ['Network Name', 'Orbital Location', 'Special Section No.', 'Date of Receipt by BR',
                       'WIC/IFIC date'], c['t1'], merge_cols=(0, 1), sz=22)
    body += empty()
    body += caption('Table 2. The Japanese satellite network(s)')
    body += table(W5, ['Network Name', 'Orbital Position', 'Special Section No.', 'Date of Receipt by BR',
                       'Published Date'], c['t2'], merge_cols=(0, 1), sz=22)
    body += empty()

    body += h4('Orbital Separation')
    body += para('The following table presents the geocentric orbital separations between the Indonesian and '
                 'Japanese satellite networks under consideration.', spacing=(240, 240))
    body += caption('Table 3. Orbital Separation')
    body += table([3394, 3296, 1950], ['Indonesian satellite network(s)', 'Japanese satellite network(s)',
                                       'Orbital separation (\u00b0)'], c['t3'])
    body += empty()

    body += h4('Frequency Overlap')
    band = c['band_label']
    if c.get('freq_rows'):
        body += para(f"Both delegations agreed that the frequency overlap between the {c['ins_label']} satellite network "
                     f"and the {c['j_list']} satellite networks in the {band} band occurred in these following bands:",
                     spacing=(240, 120))
        body += band_block(f"{band}-Band" if band else "", c['freq_rows'])
    else:
        body += para(f"Both delegations agreed that there is no frequency overlap between the {c['ins_label']} "
                     f"satellite network and the {c['j_list']} satellite networks in the {band} band.",
                     spacing=(240, 240))

    body += h4('Discussion')
    body += rich_text(c['discussion'])
    body += h4('Conclusion')
    body += rich_text(c['conclusion'])
    return body


def build_docx(template_bytes: bytes, content: dict) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(template_bytes))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == 'word/document.xml':
                d = data.decode('utf-8')
                b0 = d.index('<w:body>') + len('<w:body>')
                s0 = d.rindex('<w:sectPr')
                d = d[:b0] + section_xml(content) + d[s0:]
                data = d.encode('utf-8')
            elif re.match(r'word/footer\d*\.xml', info.filename):
                f = data.decode('utf-8')
                # template footer label "2.[x].1 - Page" -> "<item no> - Page"
                f = re.sub(r'<w:t>2\.\[x</w:t>(.*?)<w:t>\]</w:t>(.*?)<w:t xml:space="preserve">\.1 - Page </w:t>',
                           lambda m: f'<w:t>{escape(content["item_no"])}</w:t>{m.group(1)}<w:t></w:t>{m.group(2)}'
                                     f'<w:t xml:space="preserve"> - Page </w:t>', f, count=1, flags=re.S)
                data = f.encode('utf-8')
            zout.writestr(info, data)
    return out.getvalue()
