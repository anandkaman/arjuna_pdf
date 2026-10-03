"""Invisible text layer: Arjuna lines -> a PDF Form XObject of invisible, selectable, searchable text.

Encoding (research/05): one glyph per UTF-16 code unit, text in logical (stored) order, identity ToUnicode,
render mode 3. A single-glyph "GlyphLessFont" (Tesseract's pdf.ttf, Apache-2.0) is drawn for every code, so
nothing is shaped -- shaping a real Indic font loses the ToUnicode mapping of conjuncts in every extractor tested.

Placement: one BT..ET per line, the text matrix puts the baseline on the line's bottom edge (rotated with the
line), font size = line height, and Tz stretches each word so its advance equals its box width.
"""
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
import pikepdf
from pikepdf import Name, Dictionary, Array, Stream

FONT_FILE = Path(__file__).resolve().parent / "data" / "pdf.ttf"
CHAR_W = 0.5            # advance of the one glyph, in em (DW 500)
FONT_RES = "/GlyphLess"
MIN_CELL_FS = 0.15     # smallest glyph cell (incl. the space) as a fraction of the font size
SPACE_MIN = 0.0        # "split" mode: smallest advance of a space glyph, as a fraction of the font size


@dataclass
class Word:
    text: str
    x0: float           # start / end of the word ALONG the line, in points from the line origin
    x1: float


@dataclass
class TextLine:
    origin: tuple       # baseline start (bottom-left of the line box) in PDF user space
    direction: tuple    # unit vector along the baseline
    height: float       # line box height in points (font size)
    width: float        # line box width in points
    words: list = field(default_factory=list)   # [Word]; empty -> the whole text is one run over the full width
    text: str = ""


def _font(pdf):
    """Type0 / CIDFontType2 GlyphLessFont, every CID drawn with GID 1, identity ToUnicode."""
    ttf = FONT_FILE.read_bytes()
    cid2gid = Stream(pdf, b"\x00\x01" * 65536)
    tounicode = Stream(pdf, (
        b"/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        b"/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        b"1 beginbfrange\n<0000> <FFFF> <0000>\nendbfrange\n"
        b"endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"))
    descriptor = Dictionary(Type=Name.FontDescriptor, FontName=Name.GlyphLessFont, Flags=5,
                            FontBBox=Array([0, 0, 1000 * CHAR_W, 1000]), ItalicAngle=0, Ascent=1000, Descent=0,
                            CapHeight=1000, StemV=80, FontFile2=Stream(pdf, ttf))
    cidfont = Dictionary(Type=Name.Font, Subtype=Name.CIDFontType2, BaseFont=Name.GlyphLessFont,
                         CIDSystemInfo=Dictionary(Registry=pikepdf.String("Adobe"), Ordering=pikepdf.String("Identity"), Supplement=0),
                         FontDescriptor=pdf.make_indirect(descriptor), DW=int(1000 * CHAR_W), CIDToGIDMap=pdf.make_indirect(cid2gid))
    return pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type0, BaseFont=Name.GlyphLessFont, Encoding=Name("/Identity-H"),
                                        DescendantFonts=Array([pdf.make_indirect(cidfont)]), ToUnicode=pdf.make_indirect(tounicode)))


def _hex(s):
    return "<" + s.encode("utf-16-be").hex().upper() + ">"


def _units(s):
    return len(s.encode("utf-16-be")) // 2


def _f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) >= 1e-4 else "0"


def _weight(ch):
    """Rough visual width of one code point in ems-of-a-cell: base letters 1, combining marks (matras, virama,
    anusvara, nukta) narrow, joiners 0. Only used until real word positions (CTC frames, M2) are available."""
    if ch in "\u200c\u200d": return 0.0
    cat = unicodedata.category(ch)
    return 0.3 if cat.startswith("M") else 1.0


def split_words(text, width):
    """Proportional word boxes along a line of `width` pt: [Word] in reading order, gaps = the spaces' share."""
    toks = text.split(" "); spaces = len(toks) - 1; SPACE_W = 1.0
    total = sum(_weight(c) for c in text if c != " ") + SPACE_W * spaces
    if total <= 0: return [Word(text, 0.0, width)]
    unit = width / total; x = 0.0; out = []
    for t in toks:
        if t:
            w = sum(_weight(c) for c in t) * unit; out.append(Word(t, x, x + w)); x += w
        x += SPACE_W * unit
    return out


def order_same_row_runs(lines):
    """Consecutive lines (in reading order) that sit on ONE row but jump BACKWARDS along it are re-emitted left-to-right.
    pdf.js joins same-row text with no space when the next run starts to the left of the previous one (measured:
    header '११३ | सूत्रस्थानम् | अ॰ ८ ]' written R->L came out '११३सूत्रस्थानम्अ॰ ८ ]'); poppler/pdfminer reorder by geometry
    anyway. Only CONSECUTIVE same-row lines move, so two-column reading order is untouched."""
    out, i = [], 0
    def same_row(a, b):
        da, db = a.direction, b.direction
        if da[0] * db[0] + da[1] * db[1] < 0.99: return False
        nx, ny = -da[1], da[0]   # normal to the baseline
        off = (b.origin[0] - a.origin[0]) * nx + (b.origin[1] - a.origin[1]) * ny
        return abs(off) < 0.5 * min(a.height, b.height)
    along = lambda l, ref: l.origin[0] * ref.direction[0] + l.origin[1] * ref.direction[1]
    while i < len(lines):
        j = i + 1
        while j < len(lines) and same_row(lines[i], lines[j]): j += 1
        run = lines[i:j]
        if len(run) > 1 and any(along(run[k + 1], run[0]) < along(run[k], run[0]) for k in range(len(run) - 1)):
            run = sorted(run, key=lambda l: along(l, run[0]))
        out.extend(run); i = j
    return out


def content_ops(lines, mode="words"):
    """PDF content stream (bytes) drawing `lines` as invisible text.
    mode "words": Tesseract scheme -- each word positioned with Td; "word + space" is stretched (Tz) to reach the next
    word's start, so the space glyph exactly fills the real gap; the last word is stretched to its own width.
    mode "split": each word stretched to exactly its own box, then the space drawn as a separate run that fills the real
    gap (at least SPACE_MIN x font size, overhanging when the gap is smaller) -> selection boxes stop at the word's ink.
    mode "fit": letters stretched to exactly the word box, the trailing space inside the same run (overhangs one cell).
    mode "line": the whole line as one uniformly stretched run (M1 first try; poppler merges words on dense lines)."""
    out = ["BT", "3 Tr"]
    for ln in order_same_row_runs(list(lines)):
        text = " ".join(unicodedata.normalize("NFC", ln.text).split())
        if not text or ln.height <= 0 or ln.width <= 0: continue
        if ln.words: words = ln.words
        elif mode in ("words", "split", "fit"): words = split_words(text, ln.width)
        else: words = [Word(text, 0.0, ln.width)]
        words = [w for w in words if w.text]
        if not words: continue
        ux, uy = ln.direction; ox, oy = ln.origin
        # glyph cell (pt) of each run: advances are fixed by the boxes, independent of the font size
        if mode in ("split", "fit"): cells = [(w.x1 - w.x0) / _units(w.text) for w in words]   # letters only; spaces get SPACE_MIN
        else: cells = [(words[k + 1].x0 - w.x0) / _units(w.text + " ") for k, w in enumerate(words[:-1])] + [(words[-1].x1 - words[-1].x0) / _units(words[-1].text)]
        # extractors break words where a gap exceeds ~0.1 x font size (poppler); a box that is very tall for its text
        # (decorative type, merged lines) would make every space "too narrow" -> shrink the font, centre it in the box
        fs = min(ln.height, max(min(cells), 0.01) / MIN_CELL_FS)
        if fs < ln.height:
            sh = (ln.height - fs) / 2; ox, oy = ox - uy * sh, oy + ux * sh
        out.append(f"{FONT_RES} {_f(fs)} Tf")
        out.append(f"{_f(ux)} {_f(uy)} {_f(-uy)} {_f(ux)} {_f(ox)} {_f(oy)} Tm")   # line frame, unscaled
        prev_x = 0.0
        for k, w in enumerate(words):
            wt = unicodedata.normalize("NFC", w.text)
            if not wt: continue
            last = k == len(words) - 1
            if mode == "split":
                if abs(w.x0 - prev_x) > 1e-3: out.append(f"{_f(w.x0 - prev_x)} 0 Td")
                prev_x = w.x0
                out.append(f"{_f(100.0 * max(w.x1 - w.x0, 0.1) / (_units(wt) * CHAR_W * fs))} Tz")
                out.append(f"{_hex(wt)} Tj")
                gap = (words[k + 1].x0 - w.x1) if not last else 0.0
                adv = max(gap, SPACE_MIN * fs, 0.01)   # every word, also the last of a line, ends with a real space glyph
                out.append(f"{_f(100.0 * adv / (CHAR_W * fs))} Tz")
                out.append(f"{_hex(' ')} Tj")
                continue
            run = wt + " "   # trailing space on EVERY word, also at line end: without it pdfminer joins lines' words
            if mode == "fit" or last: tz = 100.0 * max(w.x1 - w.x0, 0.1) / (_units(wt) * CHAR_W * fs)   # letters fit the box, space overhangs
            else: tz = 100.0 * max(words[k + 1].x0 - w.x0, 0.1) / (_units(run) * CHAR_W * fs)
            if abs(w.x0 - prev_x) > 1e-3: out.append(f"{_f(w.x0 - prev_x)} 0 Td")
            prev_x = w.x0
            out.append(f"{_f(tz)} Tz")
            out.append(f"{_hex(run)} Tj")
        out.append("100 Tz")   # line breaks come from the next line's Tm; no newline glyph is drawn
    out.append("ET")
    return ("\n".join(out) + "\n").encode("ascii")


def text_form(pdf, lines, bbox, mode="words"):
    """Form XObject holding the invisible text for one page; `bbox` = page MediaBox (user space)."""
    return Stream(pdf, content_ops(lines, mode), Type=Name.XObject, Subtype=Name.Form, BBox=Array([float(v) for v in bbox]),
                  Resources=Dictionary(Font=Dictionary({FONT_RES: _font(pdf)})))


def graft(pdf, page, form):
    """Draw `form` on top of the page's existing content. The original content is wrapped in q..Q so whatever
    graphics state it leaves behind cannot move the text; image streams are never touched."""
    name = Name.random(prefix="OCR")
    res = page.obj.get(Name.Resources)
    if res is None:
        page.obj.Resources = Dictionary(); res = page.obj.Resources
    if Name.XObject not in res: res.XObject = Dictionary()
    res.XObject[name] = form
    page.contents_add(Stream(pdf, b"q\n"), prepend=True)
    page.contents_add(Stream(pdf, b"\nQ\nq " + str(name).encode() + b" Do Q\n"), prepend=False)
    return name
