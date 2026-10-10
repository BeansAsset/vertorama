"""What to do with a tall capture: PDF pages, a searchable PDF, plain text."""

import os
import subprocess
import tempfile

from PIL import Image, ImageOps


def page_cuts(image, page_height, search=160):
    """Where to cut a tall image into pages: near every page_height, at the
    quietest row close by, so a cut never runs through a line of text."""
    gray = image.convert("L")
    narrow = gray.resize((16, gray.height), Image.BOX)
    data = narrow.tobytes()
    def busy(row):
        values = data[row * 16:(row + 1) * 16]
        mean = sum(values) / 16
        return sum((v - mean) ** 2 for v in values)
    cuts, y = [], 0
    while image.height - y > page_height:
        target = y + page_height
        lo, hi = max(y + page_height // 2, target - search), min(image.height - 1, target + search // 4)
        cut = min(range(lo, hi), key=lambda r: (busy(r), abs(r - target)))
        cuts.append(cut)
        y = cut
    return cuts


def pages(image, page_height=None):
    page_height = page_height or int(image.width * 1.414)   # A4 shape
    edges = [0, *page_cuts(image, page_height), image.height]
    return [image.crop((0, a, image.width, b)) for a, b in zip(edges, edges[1:]) if b > a]


def _tesseract(args):
    try:
        out = subprocess.run(["tesseract", *args], capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise RuntimeError("Tesseract isn't installed") from None
    if out.returncode != 0:
        lines = out.stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "Tesseract failed")
    return out.stdout


def save_pdf(image, path):
    """A searchable PDF: the image, with invisible recognised text behind it."""
    with tempfile.TemporaryDirectory(prefix="vertorama-") as tmp:
        listing = os.path.join(tmp, "pages.txt")
        with open(listing, "w") as f:
            for i, page in enumerate(pages(image)):
                p = os.path.join(tmp, f"page-{i:03d}.png")
                # Twice the size reads better; the PDF records 144 dpi so pages keep their look.
                page.resize((page.width * 2, page.height * 2), Image.LANCZOS).save(p, dpi=(144, 144))
                f.write(p + "\n")
        _tesseract([listing, path.removesuffix(".pdf"), "-l", "eng", "pdf"])
    return path


def readable(image):
    """Screen text made easy for Tesseract: grayscale, dark on light, 2x."""
    gray = image.convert("L")
    small = gray.resize((64, max(1, gray.height // 16)))
    if sum(small.tobytes()) / max(1, small.width * small.height) < 128:
        gray = ImageOps.invert(gray)
    return gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)


def lines_from_tsv(tsv):
    """(top, bottom, text) for each line in Tesseract's TSV output."""
    lines = {}
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))           # block, paragraph, line
        top, height = int(f[7]), int(f[9])
        entry = lines.setdefault(key, [top, top + height, []])
        entry[0], entry[1] = min(entry[0], top), max(entry[1], top + height)
        entry[2].append(f[11])
    return sorted((t, b, " ".join(words)) for t, b, words in lines.values())


def join_lines(lines):
    """Lines as text, with a blank line only where the screen has a real gap
    (Tesseract's own blank lines come and go between evenly spaced lines)."""
    if not lines:
        return ""
    heights = sorted(b - t for t, b, _ in lines)
    usual = heights[len(heights) // 2]
    out, last_bottom = [], None
    for top, bottom, text in lines:
        if last_bottom is not None and top - last_bottom > usual * 1.2:
            out.append("")
        out.append(text)
        last_bottom = bottom
    return "\n".join(out)


def text_of(image):
    """All the text in a tall image, read a page at a time."""
    parts = []
    with tempfile.TemporaryDirectory(prefix="vertorama-") as tmp:
        for i, page in enumerate(pages(image, 1400)):
            p = os.path.join(tmp, f"page-{i:03d}.png")
            readable(page).save(p)
            tsv = _tesseract([p, "-", "-l", "eng", "--psm", "6", "tsv"])
            parts.append(join_lines(lines_from_tsv(tsv)))
    return "\n".join(t for t in parts if t)
