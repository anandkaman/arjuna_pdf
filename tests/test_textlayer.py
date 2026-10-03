"""Fast tests for the text-layer writer + graft (no OCR, no GPU).  python -m pytest -q tests/test_textlayer.py
Synthetic Kannada / Hindi / English lines (conjuncts, pre-base ि, ZWJ-free NFC text, digits, punctuation) are written onto
an image page; every extractor must return exactly the written words, and the image stream must stay byte-identical."""
import io, sys, hashlib
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
sys.path.append(str(ROOT / ".deps")); sys.path.append(str(ROOT / ".deps_test"))
import pikepdf
from arjuna_pdf.textlayer import TextLine, Word, text_form, graft, split_words
from gate_m1 import EXTRACTORS, fidelity

LINES = [
    "ಕರ್ನಾಟಕ ರಾಜ್ಯ ಪತ್ರ ಶ್ರೀ ಕ್ಷೇತ್ರ ಸ್ತ್ರೀ ೧೯೫೨ ರೂ. ೪೫,೦೦೦/-",
    "किताब शिक्षा प्रधानमंत्री हिन्दी स्त्री धर्म कार्यक्रम ज्ञान ॥ १२३",
    "Survey No. 45/2A, Hobli: Kasaba (Agreement) dated 12-03-2020",
    "ಮಾಲೀಕರು Owner ಹೆಸರು: श्री राम Kumar",
]


def image_page_pdf():
    """One A4-ish page whose content is a single gray image (like a scan)."""
    pdf = pikepdf.new(); pdf.add_blank_page(page_size=(400, 560)); p = pdf.pages[0]
    raw = (np.random.RandomState(0).rand(280, 200) * 255).astype(np.uint8).tobytes()
    img = pikepdf.Stream(pdf, raw, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=200, Height=280,
                         ColorSpace=pikepdf.Name.DeviceGray, BitsPerComponent=8)
    p.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img))
    p.obj.Contents = pdf.make_stream(b"q 400 0 0 560 0 0 cm /Im0 Do Q\n")
    b = io.BytesIO(); pdf.save(b); return b.getvalue()


def build(mode="words", with_words=False):
    src = pikepdf.open(io.BytesIO(image_page_pdf())); page = src.pages[0]; lines = []
    for k, t in enumerate(LINES):
        w = 340.0; ws = [Word(x.text, x.x0, x.x1) for x in split_words(t, w)] if with_words else []
        lines.append(TextLine(origin=(30.0, 500.0 - 40 * k), direction=(1.0, 0.0), height=18.0, width=w, text=t, words=ws))
    graft(src, page, text_form(src, lines, [float(v) for v in page.mediabox], mode))
    b = io.BytesIO(); src.save(b); return b.getvalue()


def _img_md5(data):
    pdf = pikepdf.open(io.BytesIO(data))
    return sorted(hashlib.md5(o.read_raw_bytes()).hexdigest() for o in pdf.objects if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image")


def test_all_extractors_exact_words_mode():
    data = build("words")
    for name, fn in EXTRACTORS.items():
        r = fidelity(LINES, fn(data))
        assert r["bad"] == 0, (name, r)
        assert r["recall"] == 1.0 and r["precision"] == 1.0, (name, r)


def test_explicit_word_boxes():
    data = build("words", with_words=True)
    for name, fn in EXTRACTORS.items():
        r = fidelity(LINES, fn(data)); assert r["recall"] == 1.0 and r["precision"] == 1.0, (name, r)


def test_image_untouched():
    assert _img_md5(image_page_pdf()) == _img_md5(build())


def test_rotated_line_direction():
    """A line along +y (text running up the page) still extracts, in pdfium and pdfminer."""
    src = pikepdf.open(io.BytesIO(image_page_pdf())); page = src.pages[0]
    ln = TextLine(origin=(60.0, 60.0), direction=(0.0, 1.0), height=16.0, width=300.0, text=LINES[0])
    graft(src, page, text_form(src, [ln], [float(v) for v in page.mediabox]))
    b = io.BytesIO(); src.save(b); data = b.getvalue()
    for name in ("pdfium", "pdfminer", "mupdf"):
        r = fidelity([LINES[0]], EXTRACTORS[name](data)); assert r["recall"] == 1.0, (name, r)


def test_same_row_backward_run():
    """Header fragments written right-to-left on one row must not be glued by pdf.js (or anyone)."""
    pdf = pikepdf.new(); pdf.add_blank_page(page_size=(300, 400)); p = pdf.pages[0]
    L = [TextLine((217.15, 365.52), (1.0, 0.0), 12.58, 14.09, text="११३"), TextLine((118.85, 364.49), (1.0, 0.0), 11.66, 31.82, text="सूत्रस्थानम्"),
         TextLine((38.02, 363.48), (1.0, 0.0), 13.2, 25.37, text="अ॰ ८ ]")]
    p.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary({"/X": text_form(pdf, L, [0, 0, 300, 400])}))
    p.obj.Contents = pdf.make_stream(b"q /X Do Q\n"); b = io.BytesIO(); pdf.save(b); data = b.getvalue()
    for name, fn in EXTRACTORS.items():
        r = fidelity([l.text for l in L], fn(data)); assert r["recall"] == 1.0 and r["precision"] == 1.0, (name, r)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("PASS", n)
