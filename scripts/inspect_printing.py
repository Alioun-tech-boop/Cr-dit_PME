"""Contrôles de texte et préparation d’images de revue visuelle, sans données réelles."""

import json
from pathlib import Path
import fitz
from PIL import Image, ImageDraw

root = Path("output/printing/visual")
root.mkdir(parents=True, exist_ok=True)
manifest = []
thumbs = []
for pdf in sorted(Path("examples/printing").glob("*.pdf")):
    with fitz.open(pdf) as doc:
        texts = []
        for i, page in enumerate(doc, 1):
            content = page.get_text()
            texts.append(content)
            assert content.strip(), (pdf, i)
            assert f"Page {i} / {len(doc)}" in content, (pdf, i, "pagination")
            for block in page.get_text("blocks"):
                assert (
                    0 <= block[0] < block[2] <= page.rect.width + 1
                    and 0 <= block[1] < block[3] <= page.rect.height + 1
                ), (pdf, i, block[:4])
            pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), colorspace=fitz.csGRAY)
            target = root / (pdf.stem + f"-{i:02}.png")
            pix.save(target)
            image = Image.open(target).convert("RGB")
            image.thumbnail((410, 580))
            thumb = Image.new("RGB", (440, 615), "#ddd")
            thumb.paste(image, ((440 - image.width) // 2, 25))
            ImageDraw.Draw(thumb).text((6, 5), pdf.stem + f" / {i}", fill="black")
            thumbs.append(thumb)
        (root / (pdf.stem + ".txt")).write_text("\n".join(texts))
        manifest.append({"file": str(pdf), "pages": len(doc), "characters": sum(map(len, texts))})
for start in range(0, len(thumbs), 6):
    sheet = Image.new("RGB", (1320, 1230), "white")
    for j, thumb in enumerate(thumbs[start : start + 6]):
        sheet.paste(thumb, ((j % 3) * 440, (j // 3) * 615))
    sheet.save(root / f"sheet-{start // 6 + 1:02}.png")
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
print("Pages préparées pour revue :", len(thumbs))
