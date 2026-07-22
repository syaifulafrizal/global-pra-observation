from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "GEMPRA_Consolidated_Core_Source_Code.pdf"
PAGE_SIZE = landscape(A4)
SNAPSHOT_DATE = date(2026, 7, 21)

NAVY = colors.HexColor("#12304A")
TEAL = colors.HexColor("#007F7B")
INK = colors.HexColor("#17212B")
MUTED = colors.HexColor("#5D6975")
PALE = colors.HexColor("#F3F6F8")
LINE = colors.HexColor("#CCD5DC")


SOURCE_FILES = [
    ("app.py", "Flask application server, API routes, and local dashboard delivery."),
    ("pra_nighttime.py", "Core nighttime Polarization Ratio Analysis and anomaly-detection pipeline."),
    ("download_symh.py", "SYM-H geomagnetic-index acquisition and cache preparation."),
    ("earthquake_integration.py", "USGS earthquake acquisition, geospatial calculations, and event correlation logic."),
    ("integrate_earthquakes.py", "Integration workflow that links earthquake events with station analysis outputs."),
    ("ensure_station_data.py", "Station-data availability checks and acquisition orchestration."),
    ("initialize_7day_dataset.py", "Initial seven-day processing workflow for operational datasets."),
    ("load_stations.py", "Station metadata loading, lookup, and validation helpers."),
    ("logging_utils.py", "Shared rotating-file and console logging configuration."),
    ("upload_results.py", "Static web-output aggregation, transformation, and publishing preparation."),
    ("templates/index.html", "Primary dashboard document template used by Flask and web-output generation."),
    ("static/app.js", "Interactive dashboard behavior, data loading, charts, maps, and user interactions."),
    ("static/style.css", "Responsive dashboard presentation and visual theme definitions."),
    ("requirements.txt", "Python runtime dependency manifest."),
    ("stations.json", "Operational station metadata and timezone configuration used by the analysis pipeline."),
]


def register_fonts() -> None:
    font_dir = Path("C:/Windows/Fonts")
    sans_path = font_dir / "arial.ttf"
    sans_bold_path = font_dir / "arialbd.ttf"
    mono_path = font_dir / "consola.ttf"
    mono_bold_path = font_dir / "consolab.ttf"

    for font_path in (sans_path, sans_bold_path, mono_path, mono_bold_path):
        if not font_path.is_file():
            raise FileNotFoundError(f"Required PDF font not found: {font_path}")

    pdfmetrics.registerFont(TTFont("GEMPRA-Sans", sans_path))
    pdfmetrics.registerFont(TTFont("GEMPRA-Sans-Bold", sans_bold_path))
    pdfmetrics.registerFont(TTFont("GEMPRA-Mono", mono_path))
    pdfmetrics.registerFont(TTFont("GEMPRA-Mono-Bold", mono_bold_path))


class SourceCodeDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "FileHeading":
            text = flowable.getPlainText()
            key = getattr(flowable, "_bookmark_name", None)
            if key:
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0, closed=False)
                self.notify("TOCEntry", (0, text, self.page, key))


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for page_state in self._saved_page_states:
            self.__dict__.update(page_state)
            self._draw_page_number(total_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, total_pages: int):
        width, _ = PAGE_SIZE
        self.saveState()
        self.setFont("GEMPRA-Sans", 7)
        self.setFillColor(MUTED)
        self.drawRightString(width - 12 * mm, 7 * mm, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def draw_page_chrome(pdf_canvas, doc):
    width, height = PAGE_SIZE
    pdf_canvas.saveState()
    if doc.page > 1:
        pdf_canvas.setFont("GEMPRA-Sans-Bold", 7.5)
        pdf_canvas.setFillColor(NAVY)
        pdf_canvas.drawString(12 * mm, height - 8 * mm, "GEMPRA - Consolidated Core Source Code")
        pdf_canvas.setFont("GEMPRA-Sans", 7.5)
        pdf_canvas.setFillColor(MUTED)
        pdf_canvas.drawRightString(width - 12 * mm, height - 8 * mm, "Copyright Submission Copy")
        pdf_canvas.setStrokeColor(LINE)
        pdf_canvas.setLineWidth(0.5)
        pdf_canvas.line(12 * mm, height - 10 * mm, width - 12 * mm, height - 10 * mm)

    pdf_canvas.setStrokeColor(LINE)
    pdf_canvas.setLineWidth(0.4)
    pdf_canvas.line(12 * mm, 10 * mm, width - 12 * mm, 10 * mm)
    pdf_canvas.setFont("GEMPRA-Sans", 7)
    pdf_canvas.setFillColor(MUTED)
    pdf_canvas.drawString(12 * mm, 7 * mm, "Source snapshot: 21 July 2026")
    pdf_canvas.restoreState()


def read_source(relative_path: str) -> tuple[str, list[str], str]:
    path = ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Required source file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return text, lines, digest


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="GEMPRA-Sans-Bold",
            fontSize=27,
            leading=33,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=9 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSubtitle",
            parent=styles["Normal"],
            fontName="GEMPRA-Sans",
            fontSize=15,
            leading=21,
            textColor=TEAL,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontName="GEMPRA-Sans-Bold",
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceAfter=5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="FileHeading",
            parent=styles["Heading1"],
            fontName="GEMPRA-Sans-Bold",
            fontSize=15,
            leading=19,
            textColor=NAVY,
            spaceAfter=2.5 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyTextCustom",
            parent=styles["BodyText"],
            fontName="GEMPRA-Sans",
            fontSize=9.2,
            leading=13,
            textColor=INK,
            spaceAfter=3 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallText",
            parent=styles["BodyText"],
            fontName="GEMPRA-Sans",
            fontSize=7.7,
            leading=10.5,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CodeBlock",
            fontName="GEMPRA-Mono",
            fontSize=6.25,
            leading=7.55,
            textColor=INK,
            backColor=PALE,
            borderColor=LINE,
            borderWidth=0.4,
            borderPadding=5,
            leftIndent=0,
            rightIndent=0,
            spaceBefore=2 * mm,
            spaceAfter=0,
        )
    )
    return styles


def source_inventory(styles, file_data):
    rows = [
        [
            Paragraph("No.", styles["SmallText"]),
            Paragraph("Source file", styles["SmallText"]),
            Paragraph("Purpose", styles["SmallText"]),
            Paragraph("Lines", styles["SmallText"]),
        ]
    ]
    for index, (relative_path, description, _, lines, _) in enumerate(file_data, start=1):
        rows.append(
            [
                str(index),
                Paragraph(f"<font name='GEMPRA-Mono'>{escape(relative_path)}</font>", styles["SmallText"]),
                Paragraph(escape(description), styles["SmallText"]),
                str(len(lines)),
            ]
        )

    table = Table(rows, colWidths=[14 * mm, 58 * mm, 170 * mm, 18 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "GEMPRA-Sans-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "GEMPRA-Sans"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.7),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_pdf() -> None:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = build_styles()

    file_data = []
    for relative_path, description in SOURCE_FILES:
        text, lines, digest = read_source(relative_path)
        file_data.append((relative_path, description, text, lines, digest))

    total_lines = sum(len(item[3]) for item in file_data)
    doc = SourceCodeDocTemplate(
        str(OUTPUT),
        pagesize=PAGE_SIZE,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=13 * mm,
        title="GEMPRA - Consolidated Core Source Code",
        author="Universiti Putra Malaysia",
        subject="Core source code submitted for copyright filing",
        creator="GEMPRA source-code compilation",
    )

    story = []
    story.extend(
        [
            Spacer(1, 20 * mm),
            Paragraph(
                "Geomagnetic Earthquake Monitoring Platform using<br/>Polarization Ratio Analysis (GEMPRA)",
                styles["CoverTitle"],
            ),
            HRFlowable(width="65%", thickness=1.4, color=TEAL, spaceBefore=2 * mm, spaceAfter=8 * mm),
            Paragraph("Consolidated Core Source Code", styles["CoverSubtitle"]),
            Paragraph("Copyright Submission Copy", styles["CoverSubtitle"]),
            Spacer(1, 12 * mm),
            Table(
                [
                    ["Institution", "Universiti Putra Malaysia"],
                    ["Compilation date", "21 July 2026"],
                    ["Included source files", str(len(file_data))],
                    ["Total source lines", f"{total_lines:,}"],
                ],
                colWidths=[48 * mm, 90 * mm],
                hAlign="CENTER",
                style=TableStyle(
                    [
                        ("FONTNAME", (0, 0), (0, -1), "GEMPRA-Sans-Bold"),
                        ("FONTNAME", (1, 0), (1, -1), "GEMPRA-Sans"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
                        ("TEXTCOLOR", (1, 0), (1, -1), INK),
                        ("LINEBELOW", (0, 0), (-1, -2), 0.35, LINE),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                ),
            ),
            Spacer(1, 18 * mm),
            Paragraph(
                "This document consolidates the production-relevant source files that implement the GEMPRA analysis, integration, serving, and visualization workflow.",
                ParagraphStyle(
                    name="CoverNote",
                    parent=styles["BodyTextCustom"],
                    alignment=TA_CENTER,
                    textColor=MUTED,
                    leftIndent=35 * mm,
                    rightIndent=35 * mm,
                ),
            ),
            PageBreak(),
            Paragraph("Document Scope", styles["SectionHeading"]),
            Paragraph(
                "Included files are the core production components required to understand and reproduce the GEMPRA software workflow: geomagnetic processing, PRA anomaly detection, earthquake correlation, station metadata handling, web-output preparation, application serving, and browser visualization.",
                styles["BodyTextCustom"],
            ),
            Paragraph(
                "Excluded from this filing copy: one-off repair scripts, deployment and scheduler helpers, generated web output, raw INTERMAGNET downloads, analysis results, figures, logs, repository metadata, and duplicate or superseded artifacts.",
                styles["BodyTextCustom"],
            ),
            Paragraph(
                "Line numbers are added for review and are not part of the original files. Long source lines are visually wrapped only for PDF readability. Each section records a SHA-256 digest of the original file for traceability.",
                styles["BodyTextCustom"],
            ),
            Spacer(1, 3 * mm),
            Paragraph("Source File Inventory", styles["SectionHeading"]),
            source_inventory(styles, file_data),
            PageBreak(),
            Paragraph("Table of Contents", styles["SectionHeading"]),
        ]
    )

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            name="TOCLevel1",
            fontName="GEMPRA-Sans",
            fontSize=9,
            leading=14,
            textColor=INK,
            leftIndent=3 * mm,
            firstLineIndent=0,
            spaceBefore=1.5 * mm,
        )
    ]
    story.extend([toc, PageBreak()])

    for index, (relative_path, description, text, lines, digest) in enumerate(file_data, start=1):
        heading = Paragraph(f"{index}. {escape(relative_path)}", styles["FileHeading"])
        heading._bookmark_name = f"source-file-{index:02d}"
        story.append(heading)
        story.append(Paragraph(escape(description), styles["BodyTextCustom"]))

        metadata = Table(
            [
                [
                    Paragraph(f"<b>Type:</b> {escape(Path(relative_path).suffix.lstrip('.').upper() or 'TEXT')}", styles["SmallText"]),
                    Paragraph(f"<b>Lines:</b> {len(lines):,}", styles["SmallText"]),
                    Paragraph(f"<b>SHA-256:</b> <font name='GEMPRA-Mono'>{digest}</font>", styles["SmallText"]),
                ]
            ],
            colWidths=[35 * mm, 32 * mm, 193 * mm],
            hAlign="LEFT",
        )
        metadata.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(metadata)

        numbered_lines = []
        width = max(4, len(str(max(1, len(lines)))))
        if not lines:
            lines = [""]
        for line_number, line in enumerate(lines, start=1):
            numbered_lines.append(f"{line_number:0{width}d} | {line.expandtabs(4)}")
        code_text = "\n".join(numbered_lines)
        story.append(
            Preformatted(
                code_text,
                styles["CodeBlock"],
                maxLineLength=170,
                splitChars=" ",
                newLineChars="       ",
            )
        )
        if index < len(file_data):
            story.append(PageBreak())

    doc.multiBuild(
        story,
        onFirstPage=draw_page_chrome,
        onLaterPages=draw_page_chrome,
        canvasmaker=NumberedCanvas,
    )

    print(f"Created: {OUTPUT}")
    print(f"Files: {len(file_data)}")
    print(f"Source lines: {total_lines}")


if __name__ == "__main__":
    build_pdf()
