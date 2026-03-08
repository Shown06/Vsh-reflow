import os
import logging
from datetime import datetime
from typing import List, Dict

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = landscape(A4)

PRIMARY = HexColor("#1565C0")
PRIMARY_DARK = HexColor("#0D47A1")
ACCENT = HexColor("#FF6F00")
DARK = HexColor("#212121")
BODY = HexColor("#424242")
SUBTLE = HexColor("#9E9E9E")
WHITE = HexColor("#FFFFFF")
BG = HexColor("#F5F5F5")
CARD_BORDER = HexColor("#E0E0E0")
BULLET_COLOR = HexColor("#1E88E5")

FONT_PATHS = [
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
]

FONT_R = "JPGothic"
_fonts_ok = False


def _register_fonts() -> bool:
    global _fonts_ok
    if _fonts_ok:
        return True

    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(FONT_R, path))
                _fonts_ok = True
                logger.info(f"Font registered: {path}")
                return True
            except Exception as e:
                logger.warning(f"Font registration failed for {path}: {e}")

    logger.error("No usable Japanese TrueType font found")
    return False


def _wrap(c: canvas.Canvas, text: str, size: float, max_w: float) -> List[str]:
    c.setFont(FONT_R, size)
    result: List[str] = []
    for para in text.split("\n"):
        if not para.strip():
            result.append("")
            continue
        buf = ""
        for ch in para:
            if c.stringWidth(buf + ch, FONT_R, size) > max_w:
                result.append(buf)
                buf = ch
            else:
                buf += ch
        if buf:
            result.append(buf)
    return result


def _title_slide(c: canvas.Canvas, topic: str, date_str: str):
    # Full-bleed dark background
    c.setFillColor(PRIMARY_DARK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Upper area - lighter blue
    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H * 0.38, PAGE_W, PAGE_H * 0.62, fill=1, stroke=0)

    # Accent stripe
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H * 0.38, PAGE_W, 3 * mm, fill=1, stroke=0)

    # Sub-heading
    c.setFillColor(HexColor("#90CAF9"))
    c.setFont(FONT_R, 13)
    c.drawString(50, PAGE_H - 45, "Vsh-reflow  AI Meeting Report")

    # Decorative line under sub-heading
    c.setStrokeColor(HexColor("#42A5F5"))
    c.setLineWidth(0.6)
    c.line(50, PAGE_H - 52, 300, PAGE_H - 52)

    # Main title
    lines = _wrap(c, topic, 32, PAGE_W - 120)
    c.setFillColor(WHITE)
    c.setFont(FONT_R, 32)
    y_start = PAGE_H * 0.7
    for i, line in enumerate(lines[:3]):
        c.drawString(50, y_start - i * 42, line)

    # Lower area metadata
    c.setFillColor(HexColor("#B0BEC5"))
    c.setFont(FONT_R, 14)
    c.drawString(50, PAGE_H * 0.38 - 35, date_str)
    c.setFont(FONT_R, 11)
    c.drawString(50, PAGE_H * 0.38 - 55, "Powered by Multi-Agent Autonomous System")

    # Page 1 indicator
    c.setFillColor(SUBTLE)
    c.setFont(FONT_R, 9)
    c.drawRightString(PAGE_W - 30, 20, "1")


def _content_slide(c: canvas.Canvas, idx: int, total: int, title: str, content: str):
    # Background
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Left accent sidebar
    c.setFillColor(PRIMARY)
    c.rect(0, 0, 6, PAGE_H, fill=1, stroke=0)

    # Top header bar
    c.setFillColor(PRIMARY)
    c.rect(6, PAGE_H - 56, PAGE_W - 6, 56, fill=1, stroke=0)

    # Slide title in header
    title_lines = _wrap(c, title, 20, PAGE_W - 140)
    c.setFillColor(WHITE)
    c.setFont(FONT_R, 20)
    ty = PAGE_H - 24
    for line in title_lines[:2]:
        c.drawString(26, ty, line)
        ty -= 26

    # Slide number badge
    c.setFillColor(ACCENT)
    badge_x = PAGE_W - 50
    badge_y = PAGE_H - 42
    c.circle(badge_x, badge_y, 14, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(FONT_R, 11)
    c.drawCentredString(badge_x, badge_y - 4, str(idx))

    # Content card
    card_x = 22
    card_y = 22
    card_w = PAGE_W - 44
    card_h = PAGE_H - 90

    # Card shadow
    c.setFillColor(HexColor("#E0E0E0"))
    c.roundRect(card_x + 2, card_y - 2, card_w, card_h, 6, fill=1, stroke=0)

    # Card background
    c.setFillColor(WHITE)
    c.roundRect(card_x, card_y, card_w, card_h, 6, fill=1, stroke=0)

    # Card border
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.4)
    c.roundRect(card_x, card_y, card_w, card_h, 6, fill=0, stroke=1)

    # Content text
    text_x = card_x + 20
    text_w = card_w - 40
    lines = _wrap(c, content, 13, text_w - 14)

    y = card_y + card_h - 22
    max_y = card_y + 16

    for line in lines:
        if y < max_y:
            break

        stripped = line.lstrip("・-•▪▸► ")
        is_bullet = stripped != line and stripped

        if is_bullet:
            c.setFillColor(BULLET_COLOR)
            c.circle(text_x + 4, y + 3.5, 2.5, fill=1, stroke=0)
            c.setFillColor(BODY)
            c.setFont(FONT_R, 13)
            c.drawString(text_x + 14, y, stripped)
        elif not line.strip():
            pass  # blank line = spacing
        else:
            c.setFillColor(BODY)
            c.setFont(FONT_R, 13)
            c.drawString(text_x, y, line)

        y -= 19

    # Footer
    c.setFillColor(SUBTLE)
    c.setFont(FONT_R, 8)
    c.drawRightString(PAGE_W - 30, 10, f"{idx} / {total}")


async def generate_presentation_pdf(
    topic: str, slides: List[Dict[str, str]], output_path: str
) -> bool:
    try:
        if not _register_fonts():
            return False

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        c = canvas.Canvas(output_path, pagesize=landscape(A4))
        c.setTitle(f"AI Meeting Report: {topic}")
        c.setAuthor("Vsh-reflow")

        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        total = len(slides) + 1

        _title_slide(c, topic, date_str)
        c.showPage()

        for i, slide in enumerate(slides, start=2):
            _content_slide(
                c, idx=i, total=total,
                title=slide.get("title", f"Slide {i}"),
                content=slide.get("content", ""),
            )
            c.showPage()

        c.save()
        logger.info(f"PDF created: {output_path}")
        return True

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return False
