import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
const path = process.argv[2];
const doc = await pdfjs.getDocument({url: path, verbosity: 0}).promise;
const page = await doc.getPage(1);
const tc = await page.getTextContent();
let s = ""; for (const it of tc.items) { s += it.str + (it.hasEOL ? "\n" : ""); }
console.log(s);
