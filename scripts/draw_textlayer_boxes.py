"""Draw the word boxes of a PDF text layer (pdftotext -bbox) over the page image: visual placement check."""
import re, subprocess, sys
import cv2
pdf, img_path, out = sys.argv[1:4]
img = cv2.imread(img_path); H, W = img.shape[:2]
xml = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True).stdout
pw, ph = map(float, re.search(r'<page width="([\d.]+)" height="([\d.]+)"', xml).groups())
sx, sy = W / pw, H / ph; n = 0
for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">', xml):
    x0, y0, x1, y1 = map(float, m.groups()); n += 1
    cv2.rectangle(img, (int(x0 * sx), int(y0 * sy)), (int(x1 * sx), int(y1 * sy)), (0, 0, 255), 2)
cv2.imwrite(out, img); print(f"{n} words, page {pw:.0f}x{ph:.0f} pt, image {W}x{H}")
