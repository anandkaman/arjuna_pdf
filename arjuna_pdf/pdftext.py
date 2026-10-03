"""Existing text on PDF pages: detect it, and strip OLD INVISIBLE OCR layers (M4, `--redo`).

Scanned PDFs often already carry an OCR layer -- scanner software or an earlier OCR run (all 40 private fixtures do:
invisible GlyphLessFont / subset-Helvetica text inside Form XObjects). A text-showing operator draws nothing when the
text render mode is 3 (invisible) or 7 (clip only), so removing exactly those operators changes no pixel of the page
while deleting the old, usually wrong, text. Visible text (watermarks, born-digital text) is never touched.

Text render mode is part of the graphics state: it is saved by q / restored by Q, persists across BT..ET, and a Form
XObject starts with the state current at its `Do`. All of that is tracked here, including nested forms.
"""
import pikepdf
from pikepdf import Name

SHOW_OPS = {"Tj", "TJ", "'", '"'}
INVISIBLE = {3, 7}


def _strip_stream(holder, resources, tr_in, seen, stats):
    """Rewrite one content stream (page or form) without invisible text-showing operators. Returns nothing."""
    try:
        ops = pikepdf.parse_content_stream(holder)
    except Exception:
        stats["unparsable"] += 1; return
    out, tr, stack, changed = [], tr_in, [], False
    for operands, op in ops:
        o = str(op)
        if o == "q": stack.append(tr)
        elif o == "Q": tr = stack.pop() if stack else tr_in
        elif o == "Tr" and operands: tr = int(operands[0])
        elif o in SHOW_OPS and tr in INVISIBLE:
            stats["removed_ops"] += 1; changed = True
            if o in ("'", '"'): out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("T*")))   # keep the line move
            continue
        elif o == "Do" and resources is not None and Name.XObject in resources and operands:
            x = resources.XObject.get(operands[0])
            if x is not None and x.get(Name.Subtype) == Name.Form:
                key = (x.objgen, tr)
                if key not in seen:
                    seen.add(key); _strip_stream(x, x.get(Name.Resources, resources), tr, seen, stats)
        out.append(pikepdf.ContentStreamInstruction(operands, op))
    if changed:
        holder.write(pikepdf.unparse_content_stream(out)); stats["streams_rewritten"] += 1   # holder = a Form XObject stream


def strip_invisible_text(pdf, page):
    """Remove invisible (Tr 3/7) text from `page` (pikepdf.Page) and the forms it draws. Returns stats dict."""
    from collections import Counter
    stats = Counter()
    try:
        ops = pikepdf.parse_content_stream(page)
    except Exception:
        stats["unparsable"] += 1; return dict(stats)
    out, tr, stack, changed, seen = [], 0, [], False, set()
    res = page.obj.get(Name.Resources)
    for operands, op in ops:
        o = str(op)
        if o == "q": stack.append(tr)
        elif o == "Q": tr = stack.pop() if stack else 0
        elif o == "Tr" and operands: tr = int(operands[0])
        elif o in SHOW_OPS and tr in INVISIBLE:
            stats["removed_ops"] += 1; changed = True
            if o in ("'", '"'): out.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("T*")))
            continue
        elif o == "Do" and res is not None and Name.XObject in res and operands:
            x = res.XObject.get(operands[0])
            if x is not None and x.get(Name.Subtype) == Name.Form:
                key = (x.objgen, tr)
                if key not in seen:
                    seen.add(key); _strip_stream(x, x.get(Name.Resources, res), tr, seen, stats)
        out.append(pikepdf.ContentStreamInstruction(operands, op))
    if changed:
        page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(out)); stats["streams_rewritten"] += 1
    return dict(stats)
