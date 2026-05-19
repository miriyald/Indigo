"""
Generate a color mapping scaffold JSON for manual region-to-color assignment.

Detects visual regions in each glyph (outer contour + its holes) and outputs
a JSON file where users assign palette colors per region.

Usage:
    python tools/generate_mapping.py [input.ttf] --output data/color_mapping.json
    python tools/generate_mapping.py [input.ttf] --output data/color_mapping.json --auto-heuristic
"""

import argparse
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from add_color import is_telugu_glyph, contour_bbox_area, detect_regions


def main():
    parser = argparse.ArgumentParser(description="Generate color mapping scaffold JSON")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("--output", "-o", default="data/color_mapping.json", help="Output JSON path")
    parser.add_argument("--auto-heuristic", action="store_true",
                        help="Pre-fill using size heuristic (largest region=0, rest=1)")
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
            "description": "Manual region-to-color mapping for TiroTelugu COLR v0",
            "note": "Each region is an outer contour + its holes. Fill respects holes."
        },
        "defaults": {
            "unmapped_contours": 0,
            "unmapped_glyphs": "auto:contour"
        },
        "glyphs": {}
    }

    for name in targets:
        glyph = glyf[name]
        regions = detect_regions(glyph)

        # Only include glyphs that have at least one hole
        has_holes = any(len(holes) > 0 for _, holes in regions)
        if not has_holes:
            continue

        region_info = []
        region_map = {}
        color_cycle_idx = 0
        for ri, (outer_idx, hole_indices) in enumerate(regions):
            area = contour_bbox_area(glyph, outer_idx)
            holes_str = f"+{len(hole_indices)} holes" if hole_indices else ""
            region_info.append(f"r{ri}(area={area}{holes_str})")

            # Region itself keeps default color (0 = dark)
            region_map[str(ri)] = 0

            # Each hole gets a rotating color from the palette
            for hi in range(len(hole_indices)):
                fill_colors = [1, 2, 3, 4, 5, 6, 7, 8]
                region_map[f"{ri}.h{hi}"] = fill_colors[color_cycle_idx % len(fill_colors)]
                color_cycle_idx += 1

        mapping["glyphs"][name] = {
            "_info": f"{len(regions)} regions: {', '.join(region_info)}",
            "regions": region_map
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved mapping scaffold to {output_path}")
    print(f"  {len(mapping['glyphs'])} glyph entries")


if __name__ == "__main__":
    main()
