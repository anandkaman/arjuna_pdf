# 07 — M2 word boxes, M3 geometry, M4 redo mode (2026-10-03)

## M2 — word boxes from the recogniser's CTC frames (`arjuna_pdf/words.py`)
How: `capture()` wraps `kanen_infer.batch_pipeline.assemble` in-process (shipped package untouched) so each page doc also
carries the raw detector quads + texts + final-frame image. Each quad is re-cropped exactly like the pipeline
(`pipeline_base.crop`), decoded by the SAME ONNX session with the same preprocessing, keeping the frame of every emitted
char. Word span = space frame before → space frame after, tightened to Otsu ink columns, mapped back through the inverse
crop warp. If the re-decode ≠ Arjuna's text, retry with the second-pass padding (0.06/0.08); else proportional fallback.
Assembled lines are matched to quads whose tokens occur in the line (neighbouring stamp/bracket quads excluded).

Measured (pixels of the original page; `tests/gate_m2.py`), ganita1952_p050, 30 lines / 145 words, same lines:
| | word edge cuts a glyph (1.5 px outside) | line ink covered by no word |
|---|---|---|
| CTC word boxes | 2.8 % | 0.8 % |
| proportional split (M1) | 42.8 % | 13.7 % |
Coverage: one private page 34/35 lines with CTC words after the 2 fixes (was 28/35: 4 decode mismatches fixed by the
second-pass retry, 2 token mismatches by the neighbour filter; 1 left: two identical "R" quads).
Newspaper vijaykarnataka p010: 429/429 lines. **Full 80-page M2 gate is queued** (`scripts/after_gpu_free.sh`) — the GPU
is held by Arjuna-hi h10 training; CPU mode OOM-killed twice (12.6 GB RSS), CUDA with a 3 GB cap ran out of arena.

### Text-layer encoding A/B with real CTC words (16 kn pages, 1814 words; `scripts/textlayer_ab.py`)
| mode | pdfium | mupdf | pdfminer | poppler | selection IoU (pdfium) |
|---|---|---|---|---|---|
| **words** (Tesseract: "word+space" stretched to next word) | 16/16 | 16/16 | 16/16 | 13/16 | 0.913 |
| fit (letters fit word, space in same run) | 16/16 | 16/16 | 16/16 | 3/16 | 0.978 |
| split (space as its own run filling the gap) | 5/16 | 16/16 | 16/16 | 3/16 | 0.978 |
Decision: keep **words**. Tighter selection (fit/split) costs real word breaks in poppler (and pdfium for split) — they
merge words (`ಭಾಡಿಗೆಎಷ್ಟಾಗುತ್ತದೆ`). Price of "words": selection extends into the gap after each word.

### Text-layer policy change
Lines of blocks Arjuna marks `text_suppressed` (withheld from its own text) are no longer written (M1 wrote 47
handwriting + 37 seal + 21 figure lines). `ArjunaPDF(include_withheld=True)` restores them.

## M3 — geometry (`tests/test_geometry.py`, no OCR)
Black box at a known user-space rect, rendered by pdfium like the engine, mapped back: max error ≤ 0.56 pt for /Rotate
0/90/180/270 × {plain, offset CropBox, negative MediaBox origin}; /UserUnit 2 also ≤ 0.56 pt (pdfium and our text both
stay in user space). Arjuna frame inverse (rot90 → deskew if |deg|>0.4 → flip180, using Arjuna's own functions): ≤ 0.27 px
for all 4 rotations × deskew {0, 0.3, 1.7, −2.4}. Still to do: an end-to-end OCR run on /Rotate-d copies of fixtures.

## M4 — redo mode (`arjuna_pdf/pdftext.py`, `tests/test_strip.py`)
All 40 private fixtures carry an old OCR layer = invisible (Tr 3) text inside Form XObjects (kn: GlyphLessFont; hi: many
subset-Helvetica fonts). `strip_invisible_text` removes text-showing ops while Tr ∈ {3, 7}, tracking q/Q, BT/ET and the
state inherited by nested forms. Result: **40/40 pages pixel-identical before/after, image bytes identical**, old text
gone (up to 2,347 chars/page), visible watermark "For Government Purpose Only" kept.
Engine modes: `skip` (default, PDF24) · `redo` (strip, then OCR unless ≥ 200 visible chars remain) · `force`.
CLI: `--redo` / `--force`.

## Operational lessons
- Do not run Arjuna in CPU mode beside training on this 15 GB box: ORT CPU arena grew to 12.6 GB → OOM kills.
  Use `systemd-run --scope -p MemoryMax=...` for any side job; the OOM killer then can only take that job.
- `pkill -f`/`kill $(ps|grep)` patterns that occur in the Bash command line itself kill the tool's own shell (twice).

## M2 full gate (2026-10-04, 80 pages, GPU) — `runs/m2/gate_m2.json`, `gate_m1_on_m2.json`
| set | lines | CTC-word coverage | edges cutting glyph CTC / proportional | uncovered ink CTC / proportional | pdfium selection IoU |
|---|---|---|---|---|---|
| kn | 1856 | 99.7 % | 9.6 % / 51.8 % | 0.7 % / 10.5 % | 0.90 |
| kn_private | 691 | 98.1 % | 13.4 % / 53.8 % | 2.2 % / 10.2 % | 0.92 |
| hi | 837 | 98.6 % | 8.2 % / 55.0 % | 0.9 % / 14.5 % | 0.89 |
| hi_private | 764 | 100 % | 7.7 % / 56.0 % | 1.2 % / 11.3 % | 0.91 |
Extraction exact pages (pdfium/poppler/pdfminer/mupdf/pdf.js), 0 corrupt chars everywhere, images identical 80/80:
kn 18/14/20/19/13 · kn_private 20/9/20/19/8 · hi 16/4/20/13/13 · hi_private 18/11/20/19/8.
REGRESSION vs M1 (proportional words): poppler hi 13 -> 4, mupdf hi 19 -> 13 exact pages. Real word gaps are sometimes
small -> geometric word breakers merge words. OPEN — investigate before calling M2 done for poppler/mupdf users.
