"""
Estimate whether anything on a slide overflows.

There is no renderer here, so text height is estimated from the box width, the
font size and the character count, using a deliberately WIDE average-character
factor for Bookman Old Style. Over-estimating is the safe direction: it flags
slides that are merely tight as well as ones that genuinely overflow.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu, Inches

EMU_IN = 914400
SLIDE_W, SLIDE_H = 13.333, 7.5
# Bookman Old Style is a wide serif; 0.56 em per character is conservative.
CHAR_W = 0.56
LINE_H = 1.24          # line height as a multiple of font size
SAFE_BOTTOM = 7.35     # anything below this is too close to the slide edge


def est_text_height(text: str, font_pt: float, box_w_in: float,
                    space_after_pt: float = 0.0) -> float:
    """Height in inches this paragraph is likely to occupy."""
    if not text:
        return (font_pt * LINE_H + space_after_pt) / 72.0
    usable_pt = max(box_w_in * 72.0 - 8, 20)         # minus internal margins
    chars_per_line = max(int(usable_pt / (font_pt * CHAR_W)), 6)
    lines = 0
    for hard_line in text.split("\n"):
        lines += max(1, math.ceil(len(hard_line) / chars_per_line))
    return (lines * font_pt * LINE_H + space_after_pt) / 72.0


def check(path: Path) -> int:
    prs = Presentation(str(path))
    problems = 0
    for idx, slide in enumerate(prs.slides, 1):
        notes = []
        for shape in slide.shapes:
            if shape.left is None:
                continue
            left, top = shape.left / EMU_IN, shape.top / EMU_IN
            w, h = shape.width / EMU_IN, shape.height / EMU_IN

            if left < -0.02 or top < -0.02 or left + w > SLIDE_W + 0.02:
                notes.append(f"    shape '{shape.name}' sits outside the slide "
                             f"({left:.2f},{top:.2f} {w:.2f}x{h:.2f})")
                continue

            if shape.has_text_frame and shape.text_frame.text.strip():
                total = 0.0
                for p in shape.text_frame.paragraphs:
                    text = "".join(r.text for r in p.runs)
                    size = next((r.font.size.pt for r in p.runs if r.font.size), 18)
                    sa = p.space_after.pt if p.space_after else 0
                    total += est_text_height(text, size, w, sa)
                bottom = top + total
                if bottom > SAFE_BOTTOM:
                    notes.append(f"    TEXT OVERFLOW '{shape.name}': needs "
                                 f"{total:.2f}in from y={top:.2f} -> ends at "
                                 f"{bottom:.2f}in (slide is {SLIDE_H}in)")
                elif total > h + 0.35:
                    notes.append(f"    tight '{shape.name}': text ~{total:.2f}in in "
                                 f"a {h:.2f}in box (ends {bottom:.2f}in) — ok, box grows")

            if shape.has_table:
                table = shape.table
                widths = [c.width / EMU_IN for c in table.columns]
                total_h = 0.0
                for r_i, row in enumerate(table.rows):
                    row_h = 0.0
                    for c_i, cell in enumerate(row.cells):
                        size = next((run.font.size.pt
                                     for para in cell.text_frame.paragraphs
                                     for run in para.runs if run.font.size), 9)
                        cell_h = est_text_height(cell.text, size, widths[c_i]) + 0.06
                        row_h = max(row_h, cell_h)
                    total_h += max(row_h, row.height / EMU_IN)
                bottom = top + total_h
                flag = "TABLE OVERFLOW" if bottom > SAFE_BOTTOM else "table"
                line = (f"    {flag} '{shape.name}': {len(table.rows)} rows ~"
                        f"{total_h:.2f}in from y={top:.2f} -> ends at {bottom:.2f}in")
                if bottom > SAFE_BOTTOM:
                    notes.append(line)
                else:
                    notes.append("  ok" + line[5:])

        header = f"Slide {idx:>2}: {slide_title(slide)}"
        bad = [n for n in notes if "OVERFLOW" in n or "outside" in n]
        if bad:
            problems += len(bad)
            print(header)
            for n in notes:
                print(n)
        else:
            info = [n for n in notes if n.strip().startswith("ok") or "tight" in n]
            print(f"{header}  ✓")
            for n in info:
                print(n)
    print(f"\n{'PROBLEMS: ' + str(problems) if problems else 'No overflow detected.'}")
    return problems


def slide_title(slide) -> str:
    """The title is the largest text on the slide, not the first shape added."""
    best, best_size = "(untitled)", 0
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = "".join(r.text for r in para.runs).strip()
            if not text or len(text) > 70:
                continue
            size = next((r.font.size.pt for r in para.runs if r.font.size), 0)
            if size > best_size:
                best, best_size = text, size
    return best


if __name__ == "__main__":
    sys.exit(1 if check(Path(sys.argv[1])) else 0)
