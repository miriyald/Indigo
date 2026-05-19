"""
Generate a color mapping scaffold JSON for manual contour-to-color assignment.

Reads the compiled TiroTelugu font and outputs a JSON file with all multi-contour
Telugu glyphs, their contour counts, bounding-box areas, and default color indices.

Usage:
    python tools/generate_mapping.py [input.ttf] --output data/color_mapping.json
    python tools/generate_mapping.py [input.ttf] --output data/color_mapping.json --auto-heuristic
"""

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTFont


def is_telugu_glyph(name):
    if len(name) < 2:
        return False
    if not name.startswith("t"):
        return False
    return name[1].isupper()


def contour_bbox_area(glyph, contour_idx):
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    xs = [glyph.coordinates[i][0] for i in range(start, end + 1)]
    ys = [glyph.coordinates[i][1] for i in range(start, end + 1)]
    if not xs or not ys:
        return 0
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def main():
    parser = argparse.ArgumentParser(description="Generate color mapping scaffold JSON")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("--output", "-o", default="data/color_mapping.json", help="Output JSON path")
    parser.add_argument("--auto-heuristic", action="store_true",
                        help="Pre-fill using size heuristic (largest=0, rest=1)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    input_path = Path(args.input) if args.input else base_dir / "output/indigo/TiroTelugu/TTF/TiroTelugu-Regular.ttf"
    output_path = Path(args.output)

    print(f"Loading {input_path}")
    font = TTFont(str(input_path))

    glyf = font["glyf"]
    glyph_order = font.getGlyphOrder()

    targets = [
        name for name in glyph_order
        if is_telugu_glyph(name)
        and glyf[name].numberOfContours is not None
        and glyf[name].numberOfContours >= 2
    ]

    print(f"Found {len(targets)} multi-contour Telugu glyphs")

    mapping = {
        "_meta": {
            "palette": "ats",
            "description": "Manual contour-to-color mapping for TiroTelugu COLR v0"
        },
        "defaults": {
            "unmapped_contours": 0,
            "unmapped_glyphs": "auto:contour"
        },
        "glyphs": {}
    }

    for name in targets:
        glyph = glyf[name]
        num_contours = glyph.numberOfContours
        areas = [contour_bbox_area(glyph, i) for i in range(num_contours)]

        contours = {}
        if args.auto_heuristic:
            largest_idx = areas.index(max(areas))
            for i in range(num_contours):
                contours[str(i)] = 0 if i == largest_idx else 1
        else:
            for i in range(num_contours):
                contours[str(i)] = 0

        mapping["glyphs"][name] = {
            "_info": f"{num_contours} contours; areas: {areas}",
            "contours": contours
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved mapping scaffold to {output_path}")
    print(f"  {len(mapping['glyphs'])} glyph entries")


if __name__ == "__main__":
    main()
