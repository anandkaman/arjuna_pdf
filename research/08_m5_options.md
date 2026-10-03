# 08 — M5 single recogniser pass + PDF24 option set (2026-10-03)

## One recogniser pass (`words.SessionTap`)
The recogniser's ONNX session is wrapped: every run stores, per input row, the argmax frame ids keyed by a blake2b hash
of that exact tensor. The word step rebuilds the bit-identical tensor per crop and reads the frames -> no second pass,
and words agree with Arjuna's own (incl. TensorRT fp16) reading. Misses (engine swapped) fall back to running the session.
Test (3 kn pages, CPU, chunk=2): 84 hits / 0 misses; words identical to the re-decode run on 30/30 lines; 80/80 lines CTC.

## Chunked processing
`process(chunk=8)`: render + OCR + graft 8 pages at a time (M1-M4 rendered the whole PDF first -> unbounded memory).

## PDF24 options now implemented
| PDF24 | arjuna-pdf | note |
|---|---|---|
| skipPagesWithText (default) | mode `skip` (default) | |
| removeExistingText | `--redo` | strips only INVISIBLE text; pixel-identical (research/07) |
| (force) | `--force` | |
| autoRotatePages | `--autorotate` | from Arjuna's own orientation; /Rotate = (old - rot) % 360; image untouched |
| .txt result | `--txt` | Arjuna reading order, pages split by form feed |
| PDF/A (Ghostscript) | `--pdfa 1b/2b/3b` | pikepdf.pdfa in a subprocess (ocr_env's old jsonschema shadows ours); kn3 test: 1b/2b/3b pass, 0 findings, +3 KB |
| deskew / removeBackground / clean written into the image | NOT done | would change the page image; user asked to attach text "as is" |

## M3 end to end
ganita p050 with /Rotate 0/90/180/270 (CPU): Arjuna read each correctly (rotation 0/90/180/270), autorotate restored
/Rotate 0 on all, word ends vs the upright page: median 0.00 / 0.12 / 0.37 / 0.39 pt. Outliers were detector variance on
the flipped image (one box ~1 pt longer -> 4.4 pt) and a smudge read as "S" detected twice (wrong pairing, 34.7 pt).

## Ops
CPU Arjuna needs > 4 GB RAM even for 3 small pages (4 GB cgroup killed it); 7 GB cap OK. Training unaffected.

## pdf.js as 5th extractor (tools/pdfjs + .deps_test/nodejs_wheel), 2026-10-03 late
- M1 outputs: 0 corrupt chars, but only ~18/40 pages exact in pdf.js. Two causes:
  1. Same-row lines written R->L (header '११३ | सूत्रस्थानम् | अ॰ ८ ]' in Arjuna's reading order): pdf.js glues them with
     no space. FIX `textlayer.order_same_row_runs`: consecutive same-row lines that jump backwards are emitted L->R
     (two-column order untouched). Unit test `test_same_row_backward_run` passes in all 5 engines. -> 24/38 exact.
  2. Remaining: pdf.js puts hasEOL inside slightly tilted (deskewed) lines and glues a line's last word to the next
     line's first. Font size is NOT the cause (tested 0.65-1.0 x box). Tesseract's own layer (= PDF24) shows the same
     1-4 glued tokens/page in pdf.js on the same pages -> parity with PDF24; logged as a known pdf.js limitation.
