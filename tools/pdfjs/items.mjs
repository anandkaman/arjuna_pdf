import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
const doc = await pdfjs.getDocument({url: process.argv[2], verbosity: 0}).promise;
const tc = await (await doc.getPage(1)).getTextContent();
for (const it of tc.items.slice(0, +process.argv[3] || 12)) console.log(JSON.stringify({s: it.str, eol: it.hasEOL, x: +it.transform[4].toFixed(1), y: +it.transform[5].toFixed(1), w: +it.width.toFixed(1), h: +it.height.toFixed(1)}));
