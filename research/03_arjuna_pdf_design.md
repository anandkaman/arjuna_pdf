# 03 — arjuna-pdf: design + what we need (2026-10-03, draft v0)

Goal (user): PDF in → **layout → detection → OCR with our recogniser → text attached back onto the
ORIGINAL PDF page as-is** (searchable, selectable, image untouched), PDF24-equivalent, Kannada+English
and Hindi+English. Inputs: research 01/02 (PDF24 teardown), 04 (detector survey), 05 (text-layer survey).

## Pipeline
```
PDF ──open (pypdfium2)──▶ per page:
  0 skip?      page already has text (count_chars>0) → skip | --redo strips old 3-Tr text
  1 raster     GRAY, DPI chosen to put text at Arjuna's 150-DPI POV (cap 50 MP); remember dpi, CropBox, /Rotate
  2 Arjuna     layout (v14/v15) → det v1.2.1 (pad_top .03 / pad_bottom .25) → orientation + deskew
               → rec (kn-en or hi-en ONNX/TRT) → assembler (reading order, tables)       [EXISTS]
  3 words      split each line into word boxes from CTC frame positions of the space token  [NEW]
  4 geometry   deskewed/rotated frame → raster frame → PDF user space (CropBox, /Rotate, UserUnit) [NEW]
  5 text page  GlyphLessFont writer: per line BT…ET, per word Td+Tz+Tj+space, 3 Tr, NFC     [NEW]
  6 graft      Form XObject overlay (q…Q wrap, foreground), images never re-encoded          [NEW]
  7 options    autorotate page from text direction · deskew/clean written into image (opt-in) ·
               PDF/A (pikepdf.pdfa) · .txt / .json side outputs                              [NEW]
```

## What we have vs what we need
| stage | have (Arjuna) | need |
|---|---|---|
| PDF read/render | `kanen_infer/io.py` pdf_pages (pypdfium2, fixed dpi) | per-page DPI choice + keep CropBox/Rotate/dpi metadata; text-presence check |
| layout | v14 shipped, v15 (15-class) ready to ship beside it | nothing new; a "text-layer policy": which block types get a text layer (figure/seal/handwriting suppression must NOT delete printed text — open Arjuna issue) |
| detection | det v1.2.1 self-distilled; Hindi transfer verified (0.6 % fragments, no top clipping) | **re-measure clipping at scale on PDF pages** for both scripts (above- AND below-band per-component overflow); optional connected-component y-snap (survey 04 fix #3) only if measurement shows loss |
| recognition | kn-en v1.3.x, hi-en v1.1.x ONNX/TRT | expose per-char CTC frame indices (`rec_onnx.py` already computes argmax per frame) |
| words | none (hOCR writes a line as one word) | frame→x mapping through resize/pad/warp quad; fallback proportional split |
| geometry | outputs in deskewed + rotated frame (`page.rotation`, `deskew_deg`) | exact inverse transform to raster, then to PDF space — same class of bug as shipped kn v1.3.1 bbox leak |
| text writer | none | own pikepdf writer, Occulta/pdf.ttf (Apache), identity ToUnicode |
| overlay | none | pikepdf Form XObject graft |
| CLI/API | `arjuna ocr` (json/md/txt/hocr/alto/tsv) | `arjuna pdf in.pdf -o out.pdf --lang kn-en|hi-en [--deskew --clean --rotate-pages --pdfa --redo --skip-text]` + `--sidecar out.txt` |
| tests | parity tests | extraction gate (5 engines), search gate, geometry IoU gate, rotation/CropBox/UserUnit fixtures |

## Decisions (with evidence)
- **Detector: keep ours.** No public commercial-OK detector is trained on printed kn/hi pages (04). Candidates
  for an A/B only: IndicPhotoOCR TextBPN++ (scene, kn+hi), Surya det (restricted licence, reference only),
  Tesseract psm 1 (= PDF24). Gate = dropped above/below marks on identical pixels, at scale.
- **Text encoding: one glyph per code point, logical order, identity ToUnicode** (05: OK in 5/5 engines;
  shaped fonts broken in 5/5). No ActualText, no Ghostscript in the text path.
- **Never modify the page image by default.** Deskew/clean are opt-in and, like PDF24, only on single-image pages.
- **Licences:** pypdfium2 (Apache/BSD), pikepdf (MPL), fonts Apache, own code AGPL like Arjuna. Do not copy
  PDF24 code; OCRmyPDF (MPL) patterns OK with attribution.

## Build order (fast iteration — smallest end-to-end first)
1. **M1 walking skeleton**: line-level text layer (1 word = 1 line, Tz to line width) for /Rotate 0 pages
   → extraction gate on 20 kn + 20 hi pages. Proves writer + graft + geometry.
2. M2 word boxes from CTC frames → geometry IoU gate.
3. M3 rotation/deskew inverse mapping + /Rotate, CropBox offsets, UserUnit fixtures.
4. M4 skip/redo text pages, mixed born-digital+scan PDFs, multi-image pages.
5. M5 CLI/API + sidecar + PDF/A option + speed (batch pages through BatchOCR.stream).
6. M6 head-to-head vs PDF24-equivalent (tesseract psm 1 kan+eng / hin+eng): text CER, word IoU, pages/s, size.
7. M7 manual viewer check: Acrobat, Chrome, Firefox, Edge, Preview, Evince — copy/paste + search on kn + hi.

## Open questions
- Which DPI to rasterise PDFs at: Arjuna is trained at a 150-DPI POV; render at native image resolution and
  let Arjuna normalise, or render at 150? Must keep the geometry map exact either way.
- Text-layer policy for tables (cell text order) and suppressed regions (handwriting/seal/figure).
- Hindi pre-base matra ि: stored after the consonant, extracts fine in 5 engines (2 lines tested) — re-test at scale.
