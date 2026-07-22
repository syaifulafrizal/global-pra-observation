from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "GEMPRA_Core_Source_Code_Only.pdf"
PAGE_SIZE = A4

SOURCE_FILES = [
    "app.py",
    "pra_nighttime.py",
    "download_symh.py",
    "earthquake_integration.py",
    "integrate_earthquakes.py",
    "ensure_station_data.py",
    "initialize_7day_dataset.py",
    "load_stations.py",
    "logging_utils.py",
    "upload_results.py",
    "templates/index.html",
    "static/app.js",
    "static/style.css",
    "requirements.txt",
    "stations.json",
]


def register_fonts() -> None:
    font_dir = Path("C:/Windows/Fonts")
    fonts = {
        "Source-Sans-Bold": font_dir / "arialbd.ttf",
        "Source-Mono": font_dir / "CascadiaMono.ttf",
    }
    for name, path in fonts.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required PDF font not found: {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))


def load_sources():
    sources = []
    for relative_path in SOURCE_FILES:
        path = ROOT / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Required source file not found: {path}")
        text = path.read_text(encoding="utf-8-sig")
        sources.append((relative_path, text.splitlines()))
    return sources


def wrap_code_line(line: str, max_columns: int) -> list[str]:
    expanded = line.expandtabs(4)
    if not expanded:
        return [""]
    return [expanded[start : start + max_columns] for start in range(0, len(expanded), max_columns)]


def new_code_text(pdf, x: float, y: float, font_size: float, leading: float):
    text = pdf.beginText(x, y)
    text.setFont("Source-Mono", font_size)
    text.setLeading(leading)
    text.setFillColor(colors.black)
    return text


def build_pdf() -> None:
    register_fonts()
    sources = load_sources()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = PAGE_SIZE
    left_margin = 10 * mm
    right_margin = 10 * mm
    top_margin = 10 * mm
    bottom_margin = 10 * mm
    available_width = page_width - left_margin - right_margin
    font_size = 6.2
    leading = font_size * 1.28
    character_width = pdfmetrics.stringWidth("M", "Source-Mono", font_size)
    max_columns = max(40, int(available_width / character_width))

    pdf = canvas.Canvas(
        str(OUTPUT),
        pagesize=PAGE_SIZE,
        pageCompression=1,
    )
    pdf.setTitle("GEMPRA Core Source Code")
    pdf.setSubject("Consolidated source code")
    pdf.setAuthor("Universiti Putra Malaysia")
    pdf.setCreator("GEMPRA source-code compilation")

    first_file = True
    total_lines = 0
    for relative_path, lines in sources:
        if not first_file:
            pdf.showPage()
        first_file = False

        y = page_height - top_margin
        pdf.setFont("Source-Sans-Bold", 8.5)
        pdf.setFillColor(colors.black)
        pdf.drawString(left_margin, y, relative_path)
        y -= 14

        code_text = new_code_text(pdf, left_margin, y, font_size, leading)
        for line in lines:
            for visual_line in wrap_code_line(line, max_columns):
                if code_text.getY() - leading < bottom_margin:
                    pdf.drawText(code_text)
                    pdf.showPage()
                    code_text = new_code_text(
                        pdf,
                        left_margin,
                        page_height - top_margin,
                        font_size,
                        leading,
                    )
                code_text.textLine(visual_line)
            total_lines += 1
        pdf.drawText(code_text)

    pdf.save()
    print(f"Created: {OUTPUT}")
    print(f"Files: {len(sources)}")
    print(f"Source lines: {total_lines}")
    print(f"Code font size: {font_size:.3f} pt")
    print(f"Visual wrap width: {max_columns} columns")


if __name__ == "__main__":
    build_pdf()
