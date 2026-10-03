"""Build invisible-text PDFs for Indic lines in several encodings; extract with several engines."""
import subprocess, sys
from fpdf import FPDF
from fpdf.enums import TextMode, PDFResourceType
import uharfbuzz as hb

LINES = {
    "hi": ("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
           "किताब शिक्षा प्रधानमंत्री हिन्दी स्त्री धर्म कार्यक्रम"),
    "kn": ("/usr/share/fonts/truetype/noto/NotoSansKannada-Regular.ttf",
           "ಕನ್ನಡ ರಾಜ್ಯ ಕರ್ನಾಟಕ ಶ್ರೀ ಕೊಡು ಸರ್ಕಾರ ಕೆಲಸ"),
}

def utf16hex(s):
    return "FEFF" + s.encode("utf-16-be").hex().upper()

def build(variant, out):
    pdf = FPDF(unit="pt", format=(600, 200))
    pdf.add_page()
    pdf.add_font("occ", fname="Occulta.ttf")
    for k, (fp, _) in LINES.items():
        pdf.add_font(k, fname=fp)
    pdf.set_text_shaping(True)
    pdf.text_mode = TextMode.INVISIBLE if variant != "visible" else TextMode.FILL
    y = 60
    for k, (fp, text) in LINES.items():
        fs = 14
        # word x positions from real shaped widths (simulates OCR word boxes)
        blob = hb.Blob.from_file_path(fp); face = hb.Face(blob); font = hb.Font(face)
        upem = face.upem
        def width(w):
            buf = hb.Buffer(); buf.add_str(w); buf.guess_segment_properties()
            hb.shape(font, buf, {})
            return sum(p.x_advance for p in buf.glyph_positions) / upem * fs
        x = 20
        words = text.split(" ")
        fontname = "occ" if variant == "glyphless" else k
        pdf.set_font(fontname, size=fs)
        f = pdf.current_font
        pdf._resource_catalog.add(PDFResourceType.FONT, f.i, pdf.page)
        ops = ["BT", f"/F{f.i} {fs:.2f} Tf", "3 Tr" if variant != "visible" else "0 Tr"]
        px = py = None
        for i, w in enumerate(words):
            ww = width(w)
            if px is None:
                ops.append(f"{x:.2f} {200-y:.2f} Td")
            else:
                ops.append(f"{x-px:.2f} 0 Td")
            px = x
            t = w + " "
            if variant in ("glyphless", "unshaped"):
                # natural (unshaped) width
                pdf.text_shaping = None
                nat = pdf.get_string_width(w)
                pdf.set_text_shaping(True)
                tz = ww / nat * 100 if nat else 100
                body = f.encode_text(t)
            else:
                tz = 100
                glyphs = f.shape_text(t, pdf.font_size_pt, pdf.text_shaping)
                mapped = "".join(chr(g["mapped_char"]) for g in glyphs if g["mapped_char"] is not None)
                body = f"({f.escape_text(mapped)}) Tj"
            ops.append(f"{tz:.2f} Tz")
            if variant == "actualtext":
                ops.append(f"/Span <</ActualText <{utf16hex(t)}>>> BDC {body} EMC")
            else:
                ops.append(body)
            x += ww + fs * 0.3
        ops.append("ET")
        pdf._out("\n".join(ops))
        pdf.font_stretching = 100
        y += 60
    pdf.output(out)

def extract(path):
    res = {}
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(path); res["pdfium"] = d[0].get_textpage().get_text_range().strip()
    res["poppler"] = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout.strip()
    res["poppler-raw"] = subprocess.run(["pdftotext", "-raw", path, "-"], capture_output=True, text=True).stdout.strip()
    import pymupdf
    res["mupdf"] = pymupdf.open(path)[0].get_text().strip()
    from pdfminer.high_level import extract_text
    res["pdfminer"] = extract_text(path).strip()
    return res

if __name__ == "__main__":
    import unicodedata
    gold = [t for _, t in LINES.values()]
    for v in ["glyphless", "unshaped", "shaped", "actualtext"]:
        p = f"exp_{v}.pdf"; build(v, p)
        print(f"===== {v}")
        for eng, txt in extract(p).items():
            norm = " ".join(txt.split())
            ok = [g in norm for g in gold]
            print(f"  {eng:12s} hi={'OK ' if ok[0] else 'BAD'} kn={'OK ' if ok[1] else 'BAD'} | {norm[:140]}")
