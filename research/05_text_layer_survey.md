# 05 — Invisible text layer for Indic scripts: survey + extraction test (sub-agent, 2026-10-03)

## Tested (scripts: research/experiments/exp.py, ocrm.py — 2 Hindi + 2 Kannada lines, n is SMALL)
Extractors: pdfium (Chrome), poppler, mupdf, pdfminer, pdf.js 6.3.289.
| encoding | result |
|---|---|
| 1 glyph per code point, logical order, identity ToUnicode (Tesseract GlyphLessFont / Occulta) | OK in all 5 |
| real Noto font, unshaped | OK in all 5 |
| HarfBuzz-shaped real font (OCRmyPDF 17.13 fpdf2 path for 0x0900-0x0DFF) | BROKEN in all 5 (control chars / (cid:N), spurious spaces `कि ताब`, `ಕೆ ಲಸ`) |
| shaped + /ActualText | OK pdfium/poppler only; mupdf duplicates, pdfminer + pdf.js ignore |
| tesseract 5.3.4 `-l kan textonly_pdf=1` (= PDF24) | OK in all 5 |
Not tested: Acrobat, macOS Preview, Edge → manual check before release.
Related: pdf.js #21890 (space after separately-positioned Indic glyph), pdf.js #12237 (ActualText ignored),
OCRmyPDF #1632 (poppler drops Tz across BT/ET), #1630 (rotation/non-zero origin), #1747 + gs bug 709030
(Ghostscript drops ToUnicode blocks >100 entries / multi-char entries → conjunct mappings lost).

## Decision
**GlyphLessFont-style encoding**: Type0/CIDFontType2, one glyph, CID = UTF-16 unit, identity ToUnicode
(`bfrange <0000><FFFF>`), uniform width, render mode 3, NFC text in logical order, keep ZWJ/ZWNJ.
One BT…ET per line; per word `Td` + `Tz` (fit word box) + one `Tj` with trailing space. Never per-glyph Td.
No shaping, no ActualText, no real Indic font, no Ghostscript in the text path.

## Stack (permissive)
pypdfium2 (render, text detection) + own ~300-line writer on pikepdf (MPL-2.0) + Occulta.ttf or Tesseract
pdf.ttf (Apache) + graft as Form XObject (pattern: OCRmyPDF `_graft.py`, MPL). PDF/A optional via
`pikepdf.pdfa` (pikepdf ≥10.16), validate with veraPDF.

## Overlay mechanics
Wrap existing content q…Q; append `q cm /OCR<rand> Do Q`; XObject BBox = MediaBox; keep /Rotate; text in
unrotated user space; px→pt: x = crop.x0 + px·72/dpi, y = crop.y1 − py·72/dpi (rotation: inverse matrix or
pdfium FPDF_DeviceToPage); divide by /UserUnit; skip pages with text (count_chars) or strip `3 Tr` text;
never re-encode images.

## Test gate
(1) exact string match from pdfium/poppler -raw/mupdf/pdfminer/pdf.js, no control chars / (cid: / intra-word
spaces; (2) pdfium search hits for conjunct words; (3) word IoU ≥ 0.9 (pdfium char boxes vs OCR word box)
on /Rotate 0/90/180/270, offset CropBox, UserUnit; (4) at scale on real kn + hi pages.

## Code to study
tesseract src/api/pdfrenderer.cpp (Apache) · OCRmyPDF _graft.py, fpdf_renderer/renderer.py L751-930,
fpdf2_patches.py, data/Occulta.ttf · hocr-tools hocr-pdf (Apache) · archive-pdf-tools pdfrenderer.py (AGPL).

## Verified on arjuna-pdf's own output (2026-10-04)
The test above used 2 Hindi + 2 Kannada lines. On a real 12-page Kannada document OCR'd by arjuna-pdf (glyphless encoding,
CTC word boxes), every word containing a conjunct (virama + consonant) was compared with the recogniser's text:
| engine | conjunct words copied back exactly | corrupted characters |
|---|---|---|
| pdfium (Chrome) | 659 / 659 | 0 |
| pdfminer | 659 / 659 | 0 |
| MuPDF | 659 / 659 | 0 |
| pdf.js (Firefox) | 655 / 659 | 0 |
| poppler | 643 / 659 | 0 |
The pdf.js / poppler misses are neighbouring words joined together (geometric word breaking), not broken conjuncts.
The same test lines written with a HarfBuzz-shaped real font still come back as `शि\x07क्षा`, `कि ताब`, `ಕರ್ನಾ ಟಕ`
in pdfium / poppler / pdf.js — the encoding decision stands. A user check by hand on an arjuna-pdf output also found
no copy-paste problems. Still untested: Adobe Acrobat, macOS Preview, Edge.
