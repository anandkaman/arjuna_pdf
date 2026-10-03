# 06 — M1 walking skeleton: results (2026-10-03)

Code: `arjuna_pdf/` (engine.py, geometry.py, textlayer.py, cli.py) · runner `scripts/run_m1.py` · gate `tests/gate_m1.py`
· encoding A/B without re-OCR `scripts/textlayer_ab.py`. Outputs `runs/m1/`, first (line-mode) outputs `runs/m1_v1_linemode/`.

## Fixtures (80 single-page PDFs, verbatim page copies)
| set | source | note |
|---|---|---|
| kn (20) | 6 public scanned Kannada books/periodicals 1898-2024 (`data/fixtures/`) | 2 blank pages (haidar) |
| hi (20) | 6 public scanned Hindi/Sanskrit books + Rajya Sabha debates | |
| kn_private (20) | private documents (Kannada) (`data/fixtures_private/`, never commit) | carry an old bad OCR layer |
| hi_private (20) | private documents (Hindi) | carry an old Helvetica OCR layer |

## Gate results (final writer: word mode, trailing space on every word, font floor 0.15)
Text-only layer extracted by 4 engines; exact = every written token back, nothing extra, no corrupt char.
| set | pages / lines | pdfminer | pdfium | mupdf | poppler -raw | corrupt chars | mean IoU | images identical |
|---|---|---|---|---|---|---|---|---|
| kn | 20 / 1856 | 20 | 18 | 19 | 16 | 0 | 0.935 | 20/20 |
| kn_private | 20 / 691 | 20 | 20 | 19 | 15 | 0 | 0.952 | 20/20 |
| hi | 20 / 837 | 20 | 18 | 19 | 13 | 0 | 0.976 | 20/20 |
| hi_private | 20 / 764 | 20 | 18 | 19 | 16 | 0 | 0.971 | 20/20 |
Graft check (full page incl. old text layers, pdfium): our lines recovered ≥ 0.99 on every page.

## Every remaining difference, explained (none is an encoding defect)
- pdfium (6 pages): dehyphenation — a line ending in `-` is joined to the next line with U+FFFE (viewer behaviour).
- mupdf (4 pages): splits recogniser-malformed clusters (e.g. `ನಡೆಿ`, `करेंेत` from public books) — recognition quality, not the layer.
- poppler -raw (20 pages): (a) vertical text (a sideways-printed card on a private page, dir (0,-1)) is chopped into 3-4-char pieces;
  (b) boxes that ABUT on the same row are merged without a space (detector fragments of one word, a form label next to
  its value, stamp text — all on private pages). Poppler breaks words purely on geometric gaps; fixing (b) would mean lying about
  geometry. Real word positions (M2) will not change (b).
- Hindi pre-base matra ि: extracts correctly in all 4 engines (pdfminer exact on all 40 Hindi pages).

## Defects found and fixed during M1
1. **pdfminer joined the last word of a line with the next line** when the last word had no trailing space → every word
   now carries a trailing space (research/05 said so; my word-mode rewrite had dropped it).
2. **poppler merged words on lines whose box is tall for its text** (space advance < 0.1 × font size): font size is
   now capped so every glyph cell ≥ 0.15 × font size, centred in the box (affects 0.1 % book / 0.4 % private-page lines).
3. **Hindi pack silently ran the Kannada model** — `kanen_infer` loads `kanen.yaml`, the Hindi package ships
   `arjuna_hi.yaml`, so it fell back to kn defaults and downloaded `arjuna-ocr-kn-en-inference@v1.3.0`. Symptoms: Kannada-
   charset garbage + 16/40 pages "rotated 180°". Fixed in arjuna-pdf (explicit config + charset identity check that
   refuses to run). **Same code in the PUBLIC `anandkaman/arjuna-ocr-hi-en` release** → logged in Arjuna-hi/TODO.md.

## Speed / size
kn 0.25-0.27 s/page (TensorRT rec), hi 1.0-1.2 s/page (rec on ORT, no TRT engine yet; pages processed one at a time).
Output grows a few KB per page; image streams untouched.

## Not yet covered (later milestones)
Word boxes are proportional estimates (M2: CTC frames) · /Rotate ≠ 0, CropBox offsets, UserUnit (M3) · old text layers
are kept, not stripped (M4 redo) · private-page DPI: hi_private fell back to 200 (page not detected as single-image) — check ·
Acrobat/Preview/Edge/pdf.js untested (M7) · 40 pages per language is a smoke-scale sample, not proof at scale.
