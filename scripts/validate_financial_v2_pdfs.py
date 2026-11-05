"""Extraire le texte et produire des planches de contrôle des seuls PDF synthétiques v2."""

import json
from pathlib import Path
import fitz
from PIL import Image, ImageDraw


def main():
    output = Path("output/financial-v2/pdf-pages")
    output.mkdir(parents=True, exist_ok=True)
    thumbs, results = [], []
    for file in sorted(Path("examples/financial_v2").glob("*.pdf")):
        with fitz.open(file) as pdf:
            texts = [page.get_text() for page in pdf]
            assert texts and all(text.strip() for text in texts)
            assert "Score combiné 70/30" not in "\n".join(texts)
            for index, page in enumerate(pdf):
                pix = page.get_pixmap(matrix=fitz.Matrix(0.55, 0.55))
                path = output / (file.stem + "-" + str(index + 1) + ".png")
                pix.save(path)
                pic = Image.open(path).convert("RGB")
                pic.thumbnail((220, 315))
                tile = Image.new("RGB", (240, 345), "#ddd")
                tile.paste(pic, ((240 - pic.width) // 2, 15))
                ImageDraw.Draw(tile).text(
                    (5, 325), file.stem[:23] + " " + str(index + 1), fill="black"
                )
                thumbs.append(tile)
            results.append(
                {"file": str(file), "pages": len(pdf), "characters": sum(map(len, texts))}
            )
    for start in range(0, len(thumbs), 20):
        batch = thumbs[start : start + 20]
        sheet = Image.new("RGB", (1200, 345 * ((len(batch) + 4) // 5)), "#aaa")
        for j, tile in enumerate(batch):
            sheet.paste(tile, ((j % 5) * 240, (j // 5) * 345))
        sheet.save(output / ("montage-" + str(start // 20 + 1) + ".jpg"))
    (output.parent / "pdf-validation.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print(
        "Le rendu et le texte sont vérifiés mécaniquement ; les planches doivent être inspectées visuellement."
    )


if __name__ == "__main__":
    main()
