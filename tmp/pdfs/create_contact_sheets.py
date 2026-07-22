import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[2]
RENDER_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp" / "pdfs" / "rendered"
OUTPUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "tmp" / "pdfs" / "contact_sheets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pages = sorted(RENDER_DIR.glob("page-*.png"))
if not pages:
    raise SystemExit("No rendered PDF pages found")

columns = 4
rows = 4
thumb_width = 250
thumb_height = 177
label_height = 20
gap = 8
margin = 12
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)

for sheet_index, start in enumerate(range(0, len(pages), columns * rows), start=1):
    batch = pages[start : start + columns * rows]
    sheet_width = margin * 2 + columns * thumb_width + (columns - 1) * gap
    sheet_height = margin * 2 + rows * (thumb_height + label_height) + (rows - 1) * gap
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#D9E0E5")
    draw = ImageDraw.Draw(sheet)

    for offset, page_path in enumerate(batch):
        row, column = divmod(offset, columns)
        x = margin + column * (thumb_width + gap)
        y = margin + row * (thumb_height + label_height + gap)
        with Image.open(page_path) as page_image:
            page_image = page_image.convert("RGB")
            thumb = ImageOps.contain(page_image, (thumb_width, thumb_height), Image.Resampling.LANCZOS)
        thumb_x = x + (thumb_width - thumb.width) // 2
        thumb_y = y + (thumb_height - thumb.height) // 2
        sheet.paste(thumb, (thumb_x, thumb_y))
        draw.rectangle((x, y, x + thumb_width - 1, y + thumb_height - 1), outline="#7A8994", width=1)
        page_number = start + offset + 1
        label = f"Page {page_number}"
        label_box = draw.textbbox((0, 0), label, font=font)
        label_width = label_box[2] - label_box[0]
        draw.text((x + (thumb_width - label_width) / 2, y + thumb_height + 3), label, font=font, fill="#17212B")

    end_page = start + len(batch)
    output_path = OUTPUT_DIR / f"sheet-{sheet_index:02d}_pages-{start + 1:03d}-{end_page:03d}.png"
    sheet.save(output_path, optimize=True)
    print(output_path)
