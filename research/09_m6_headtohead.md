# 09 — M6 head-to-head: arjuna-pdf vs PDF24 (2026-10-03/04, DONE)

## Benches (PRIVATE, `data/bench_private/`, gitignored; numbers may be published, pages/lines never)
| bench | pages | GT lines | source | mapping check |
|---|---|---|---|---|
| kn_private_eval | 39 (11 docs) | 1,629 verified | Arjuna's held-out labelled pages, cut from the original PDFs | image corr ≥ 0.959, 1-based pages |
| hi_private_test | 43 (8 docs) | 382 labelled | Arjuna-hi held-out test documents, cut from the original PDFs | corr ≥ 0.98 via the ingest manifest |
GT covers only the labelled lines of each page -> RECALL metrics only (`tests/bench_m6.py`): multiset word recall and
verbatim line recall, NFC + ZWJ/ZWNJ removed on both sides, text extracted from the OUTPUT PDF (pdfium, pdfminer).

## PDF24 side (`scripts/pdf24_equiv.py`: strip old invisible text = removeExistingText, gray render min(300 dpi, 50 MP),
tesseract 5.3.4 + PDF24's tessdata, --oem 3 --psm 1 textonly_pdf, foreground overlay)
| bench | word recall | line found | s/page |
|---|---|---|---|
| kn_private_eval (kan+eng) | 0.788 | 0.585 | 1.5-3 (CPU, 1 thread) |
| hi_private_test (hin+eng) | 0.867 | 0.416 | ~1 |
Worst kn pages: one page 0.0 (a single labelled line, printed sideways), one form page 0.10 (mostly garbage).
Note: PDF24's DEFAULT (skipPagesWithText) would not OCR these pages at all — every one carries an old OCR layer.

## RESULT (2026-10-04 02:02, GPU, queue fired 24 s after h10 finished)
Same pages, same metric, text extracted from each tool's OUTPUT PDF (pdfminer; pdfium within 0.1-0.8 pt):
| bench | PDF24 word recall | **arjuna-pdf word recall** | PDF24 lines verbatim | **arjuna-pdf lines verbatim** |
|---|---|---|---|---|
| kn private documents (39 pages, 1,629 lines) | 0.788 | **0.985** | 0.585 | **0.951** |
| hi private documents (43 pages, 382 lines) | 0.868 | **0.984** | 0.416 | **0.882** |
Arjuna speed on GPU: kn 0.24 s/page, hi 1.2 s/page (hi recogniser on ORT, no TRT engine) vs Tesseract 1-3 s/page (CPU).
Caveats: recall only (labelled lines); kn private-eval pages belong to documents whose OTHER pages trained Arjuna (eval pages held
out, same layouts/offices) -> some domain advantage; hi test documents are fully held out.
