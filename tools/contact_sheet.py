"""Make a labelled contact sheet of images: python3 tools/contact_sheet.py OUT.jpg DIR_OR_FILES..."""
import sys, os, glob
from PIL import Image, ImageDraw, ImageOps
out, args = sys.argv[1], sys.argv[2:]
files = []
for a in args:
    files += sorted(glob.glob(os.path.join(a, "*.*"))) if os.path.isdir(a) else [a]
T, cols = 220, 6
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * T, rows * (T + 18)), "white")
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, "white"); bg.alpha_composite(im); im = bg
    im = ImageOps.contain(im.convert("RGB"), (T - 6, T - 6))
    x, y = (i % cols) * T, (i // cols) * (T + 18)
    sheet.paste(im, (x + 3, y + 3))
    d.text((x + 3, y + T), os.path.relpath(f)[-34:], fill="black")
sheet.save(out, quality=85)
print(out, len(files))
