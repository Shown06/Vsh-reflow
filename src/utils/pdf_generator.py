import os
import logging
from datetime import datetime
from typing import List, Dict

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = landscape(A4)

PRIMARY = HexColor("#1565C0")
PRIMARY_DARK = HexColor("#0D47A1")
PRIMARY_LIGHT = HexColor("#E3F2FD")
ACCENT = HexColor("#FF6F00")
DARK = HexColor("#212121")
BODY = HexColor("#424242")
SUBTLE = HexColor("#9E9E9E")
WHITE = HexColor("#FFFFFF")
BG = HexColor("#FAFAFA")

FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
BOLD_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]

FONT_R = "NotoR"
FONT_B = "NotoB"
_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return True

    r_path = next((p for p in FONT_PATHS if os.path.exists(p)), None)
    b_path = next((p for p in BOLD_FONT_PATHS if os.path.exists(p)), None)

    if not r_path:
        logger.error("CJK Regular font not found")
        return False

    pdfmetrics.registerFont(TTFont(FONT_R, r_path, subfontIndex=0))
    if b_path:
        pdfmetrics.registerFont(TTFont(FONT_B, b_path, subfontIndex=0))
    else:
        pdfmetrics.registerFont(TTFont(FONT_B, r_path, subfontIndex=0))

    _fonts_registered = True
    logger.info(f"Fonts registered: R={r_path} B={b_path}")
    return True


def _wrap_text(c: canvas.Canvas, text: str, font: str, size: float, max_width: float) -> List[str]:
    c.setFont(font, size)
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            test = current + ch
            if c.stringWidth(test, font, size) > max_width:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def _draw_title_slide(c: canvas.Canvas, topic: str, date_str: str):
    c.setFillColor(PRIMARY_DARK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H * 0.35, PAGE_W, PAGE_H * 0.65, fill=1, stroke=0)

    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H * 0.35, PAGE_W, 4, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont(FONT_B, 14)
    c.drawString(40, PAGE_H - 50, "Vsh-reflow AI Meeting Report")

    wrapped = _wrap_text(c, topic, FONT_B, 34, PAGE_W - 100)
    y = PAGE_H * 0.65
    c.setFont(FONT_B, 34)
    for line in wrapped[:3]:
        y -= 44
        c.drawString(50, y, line)

    c.setFillColor(HexColor("#B0BEC5"))
    c.setFont(FONT_R, 16)
    c.drawString(50, PAGE_H * 0.35 - 40, f"Generated: {date_str}")
    c.drawString(50, PAGE_H * 0.35 - 65, "Powered by Vsh-reflow Multi-Agent System")


def _draw_content_slide(c: canvas.Canvas, idx: int, total: int, title: str, content: str):
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H - 60, PAGE_W, 60, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont(FONT_B, 22)
    wrapped_title = _wrap_text(c, title, FONT_B, 22, PAGE_W - 120)
    ty = PAGE_H - 22
    for line in wrapped_title[:2]:
        c.drawString(30, ty, line)
        ty -= 28

    c.setFillColor(ACCENT)
    c.rect(30, PAGE_H - 66, 60, 3, fill=1, stroke=0)

    content_x = 40
    content_y = PAGE_H - 90
    content_w = PAGE_W - 80
    content_h = PAGE_H - 130
    c.setFillColor(WHITE)
    c.roundRect(content_x - 10, 40, content_w + 20, content_h, 8, fill=1, stroke=0)

    c.setStrokeColor(HexColor("#E0E0E0"))
    c.setLineWidth(0.5)
    c.roundRect(content_x - 10, 40, content_w + 20, content_h, 8, fill=0, stroke=1)

    lines = _wrap_text(c, content, FONT_R, 13, content_w - 20)
    y = content_y - 10
    max_lines = int(content_h / 18) - 1

    c.setFillColor(BODY)
    c.setFont(FONT_R, 13)
    for i, line in enumerate(lines[:max_lines]):
        if line.startswith("・") or line.startswith("- ") or line.startswith("• "):
            c.setFillColor(PRIMARY)
            c.circle(content_x + 4, y + 4, 3, fill=1, stroke=0)
            c.setFillColor(BODY)
            c.drawString(content_x + 14, y, line.lstrip("・-• "))
        else:
            c.drawString(content_x, y, line)
        y -= 18
        if y < 50:
            break

    c.setFillColor(SUBTLE)
    c.setFont(FONT_R, 9)
    c.drawRightString(PAGE_W - 30, 18, f"{idx} / {total}")

    c.setFillColor(PRIMARY_LIGHT)
    c.rect(0, 0, 6, PAGE_H, fill=1, stroke=0)


async def generate_presentation_pdf(
    topic: str, slides: List[Dict[str, str]], output_path: str
) -> bool:
    try:
        if not _register_fonts():
            logger.error("Font registration failed — cannot generate PDF")
            return False

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        c = canvas.Canvas(output_path, pagesize=landscape(A4))
        c.setTitle(f"AI Meeting Report: {topic}")
        c.setAuthor("Vsh-reflow")

        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        total = len(slides) + 1

        _draw_title_slide(c, topic, date_str)
        c.showPage()

        for i, slide in enumerate(slides, start=2):
            _draw_content_slide(
                c,
                idx=i,
                total=total,
                title=slide.get("title", f"Slide {i}"),
                content=slide.get("content", ""),
            )
            c.showPage()

        c.save()
        logger.info(f"PDF presentation created: {output_path}")
        return True

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return False
