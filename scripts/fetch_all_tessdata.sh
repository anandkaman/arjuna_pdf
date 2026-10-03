#!/bin/bash
# Mirror every language model PDF24 Creator 11.30.1 offers (list from creator.pdf24.org, tess 5.5.2).
cd "$(dirname "$0")/../models"
curl -s https://creator.pdf24.org/tesseract/5.5.2/traindata/list.txt > pdf24_traindata_list.txt
awk '{print $1" "$NF}' pdf24_traindata_list.txt | while read code url; do
  [ -s tessdata_pdf24/$code.traineddata ] || curl -s --retry 3 -o tessdata_pdf24/$code.traineddata "$url"
done
md5sum tessdata_pdf24/*.traineddata > tessdata_pdf24/MD5SUMS
echo DONE $(ls tessdata_pdf24/*.traineddata | wc -l) files $(du -sh tessdata_pdf24 | cut -f1)
