"""
Generate a color mapping scaffold JSON for manual region-to-color assignment.

Detects visual regions in each glyph (outer contour + its holes) and outputs
a JSON file where users assign palette colors per region.

Usage:
    python tools/generate_mapping.py [input.ttf]
    python tools/generate_mapping.py [input.ttf] --output path/to/color_mapping.json

Output defaults to color_mapping.json next to the input TTF.
"""

import argparse
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from add_color import is_telugu_glyph, contour_bbox_area, detect_regions, classify_regions_smart


def main():
    parser = argparse.ArgumentParser(description="Generate color mapping scaffold JSON")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("--output", "-o", help="Output JSON path (default: next to input TTF)")
    parser.add_argument("--auto-heuristic", action="store_true",
                        help="Pre-fill using size heuristic (largest region=0, rest=1)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    input_path = Path(args.input) if args.input else base_dir / "output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf"
    if args.output:
        output_path = Path(args.output)
    else:
        ufo_data = base_dir / "source" / (input_path.stem + ".ufo") / "data"
        if ufo_data.parent.exists():
            output_path = ufo_data / "color_mapping.json"
        else:
            output_path = input_path.parent / "color_mapping.json"

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

    print(f"Found {len(targets)} multi-region Telugu glyphs")

    mapping = {
        "_meta": {
            "palette": "ats",
            "description": "Manual region-to-color mapping for TiroTelugu COLR v0",
            "note": "Each region is an outer contour + its holes. Fill respects holes."
        },
        "defaults": {
            "unmapped_regions": 0,
            "unmapped_glyphs": "auto:region"
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
        for ri, (outer_idx, hole_indices) in enumerate(regions):
            area = contour_bbox_area(glyph, outer_idx)
            holes_str = f"+{len(hole_indices)} holes" if hole_indices else ""
            region_info.append(f"r{ri}(area={area}{holes_str})")

        region_map = classify_regions_smart(glyph)

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
