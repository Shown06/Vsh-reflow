import os
import logging
from typing import List, Dict

from fpdf import FPDF

logger = logging.getLogger(__name__)

FONT_SEARCH_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
]

BLUE = (26, 115, 232)
DARK_TEXT = (60, 64, 67)
LIGHT_TEXT = (112, 117, 122)
WHITE = (255, 255, 255)


def _find_cjk_font() -> str | None:
    for path in FONT_SEARCH_PATHS:
        if os.path.exists(path):
            return path
    return None


class SlidePDF(FPDF):
    def __init__(self, topic: str, font_name: str):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.topic = topic
        self._font = font_name

    def header(self):
        self.set_font(self._font, size=8)
        self.set_text_color(*LIGHT_TEXT)
        self.cell(0, 6, self.topic, align="L")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._font, size=9)
        self.set_text_color(*LIGHT_TEXT)
        self.cell(0, 10, f"{self.page_no()}", align="R")


async def generate_presentation_pdf(
    topic: str, slides: List[Dict[str, str]], output_path: str
) -> bool:
    try:
        font_path = _find_cjk_font()
        font_name = "Helvetica"

        pdf = SlidePDF(topic, font_name="Helvetica")

        if font_path:
            pdf.add_font("NotoSansCJK", fname=font_path)
            font_name = "NotoSansCJK"
            pdf._font = font_name
            logger.info(f"CJK font loaded: {font_path}")
        else:
            logger.warning("CJK font not found — Japanese characters may not render")

        for i, slide in enumerate(slides):
            pdf.add_page()
            pdf.set_fill_color(*WHITE)

            # Slide title
            pdf.set_font(font_name, size=28)
            pdf.set_text_color(*BLUE)
            title = slide.get("title", f"Slide {i + 1}")
            pdf.cell(0, 18, title, ln=True)

            # Separator line
            pdf.set_draw_color(*BLUE)
            pdf.set_line_width(0.8)
            y = pdf.get_y()
            pdf.line(10, y, 287, y)
            pdf.ln(8)

            # Content body
            pdf.set_font(font_name, size=16)
            pdf.set_text_color(*DARK_TEXT)
            content = slide.get("content", "")
            pdf.multi_cell(0, 9, content)

            # Page indicator
            pdf.set_y(-25)
            pdf.set_font(font_name, size=10)
            pdf.set_text_color(*LIGHT_TEXT)
            pdf.cell(0, 10, f"{i + 1} / {len(slides)}", align="R")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pdf.output(output_path)
        logger.info(f"PDF presentation created: {output_path}")
        return True

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return False
