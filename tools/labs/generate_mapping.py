"""
Generate a color mapping scaffold JSON for manual region-to-color assignment.

Uses compiled TTF for region/hole detection (correct topology), and optionally
the UFO source for glyphs where overlap removal merged contours.

Usage:
    python tools/generate_mapping.py --ufo source/TiroTelugu-Regular.ufo
    python tools/generate_mapping.py output/.../TiroTelugu-Regular.ttf
    python tools/generate_mapping.py [input.ttf] --ufo [source.ufo] --output path/to/color_mapping.json

Output defaults to source/<font>.ufo/data/color_mapping.json.
"""

import argparse
import json
import sys
from pathlib import Path

import ufoLib2
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from add_color import (
    is_telugu_glyph,
    contour_bbox_area,
    detect_regions,
    classify_regions_smart,
    classify_regions_holes_only,
    SMART_COLOR_BASE,
    SMART_COLOR_ABOVE,
    SMART_COLOR_BELOW,
    SMART_ASPECT_THRESHOLD,
)
from telugu_sort import sort_telugu_glyphs


def classify_contours_ufo(ufo_font, glyph_name):
    """Assign colors to UFO contours by position (for glyphs with no TTF regions)."""
    glyphset = ufo_font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)
    if len(contours) < 2:
        return {}

    def contour_bounds(ci):
        pen = BoundsPen(glyphset)
        contours[ci].draw(pen)
        return pen.bounds or (0, 0, 0, 0)

    def contour_area(ci):
        b = contour_bounds(ci)
        return (b[2] - b[0]) * (b[3] - b[1])

    def contour_centroid_y(ci):
        b = contour_bounds(ci)
        return (b[1] + b[3]) / 2

    base_idx = max(range(len(contours)), key=contour_area)
    base_cy = contour_centroid_y(base_idx)

    mapping = {}
    for ci in range(len(contours)):
        if ci == base_idx:
            mapping[str(ci)] = SMART_COLOR_BASE
        else:
            cy = contour_centroid_y(ci)
            mapping[str(ci)] = SMART_COLOR_ABOVE if cy > base_cy else SMART_COLOR_BELOW

    return mapping


def classify_contours_ufo_holes_only(ufo_font, glyph_name):
    """Assign colors to UFO contours by winding: CW (outer)=0, CCW (hole)=2."""
    glyphset = ufo_font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)
    if len(contours) < 2:
        return {}

    mapping = {}
    for ci, contour in enumerate(contours):
        pts = [(pt.x, pt.y) for pt in contour]
        signed_area = 0
        for j in range(len(pts)):
            x1, y1 = pts[j]
            x2, y2 = pts[(j + 1) % len(pts)]
            signed_area += (x2 - x1) * (y2 + y1)
        mapping[str(ci)] = SMART_COLOR_BASE if signed_area > 0 else 2

    return mapping


def main():
    parser = argparse.ArgumentParser(description="Generate color mapping scaffold JSON")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("--ufo", type=Path, help="UFO source (for glyphs where TTF merged contours)")
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--holes-only", action="store_true",
                        help="Simplified scaffold: regions=0, holes=2 only")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    input_path = Path(args.input) if args.input else base_dir / "output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf"

    if not args.ufo:
        ufo_path = base_dir / "source" / (input_path.stem + ".ufo")
        if ufo_path.exists():
            args.ufo = ufo_path

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

    ufo_font = None
    ufo_glyphset = None
    if args.ufo:
        print(f"Loading UFO {args.ufo}")
        ufo_font = ufoLib2.Font.open(str(args.ufo))
        ufo_glyphset = ufo_font.layers.defaultLayer

    glyf = font["glyf"]
    glyph_order = font.getGlyphOrder()

    targets = sort_telugu_glyphs([
        name for name in glyph_order
        if is_telugu_glyph(name)
        and glyf[name].numberOfContours is not None
        and glyf[name].numberOfContours >= 1
    ])

    # Load existing mapping to preserve manual edits
    existing_glyphs = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            existing_glyphs = existing.get("glyphs", {})
        except (json.JSONDecodeError, OSError):
            pass

    mapping = {
        "_meta": {
            "palette": "ats",
            "description": "Manual region-to-color mapping for TiroTelugu COLR v0",
            "note": "Entries with 'regions' use TTF topology (outer+holes). Entries with 'contours' use UFO source paths."
        },
        "defaults": {
            "unmapped_regions": 0,
            "unmapped_glyphs": "auto:region"
        },
        "glyphs": {}
    }

    ttf_count = 0
    ufo_count = 0

    for name in targets:
        glyph = glyf[name]
        ttf_contours = glyph.numberOfContours

        # Check if UFO has more contours than TTF (overlap removal merged some)
        ufo_contour_count = 0
        if ufo_glyphset and name in ufo_glyphset:
            ufo_contour_count = len(list(ufo_glyphset[name].contours))

        existing_entry = existing_glyphs.get(name, {})

        if ttf_contours >= 2:
            # TTF has enough contours for proper region/hole detection
            regions = detect_regions(glyph)

            region_info = []
            for ri, (outer_idx, hole_indices) in enumerate(regions):
                area = contour_bbox_area(glyph, outer_idx)
                holes_str = f"+{len(hole_indices)} holes" if hole_indices else ""
                region_info.append(f"r{ri}(area={area}{holes_str})")

            # Preserve existing region mapping if present, otherwise generate
            if "regions" in existing_entry:
                region_map = existing_entry["regions"]
            elif args.holes_only:
                region_map = classify_regions_holes_only(glyph)
            else:
                region_map = classify_regions_smart(glyph)

            entry = {
                "_info": f"{len(regions)} regions: {', '.join(region_info)}",
                "regions": region_map
            }

            # Generate/preserve ufo_contours for dual-view glyphs
            if ufo_contour_count >= 2 and ufo_contour_count != ttf_contours:
                if "ufo_contours" in existing_entry:
                    entry["ufo_contours"] = existing_entry["ufo_contours"]
                elif args.holes_only:
                    entry["ufo_contours"] = classify_contours_ufo_holes_only(ufo_font, name)
                else:
                    entry["ufo_contours"] = classify_contours_ufo(ufo_font, name)

                contours = list(ufo_glyphset[name].contours)
                ufo_info_parts = []
                for ci, contour in enumerate(contours):
                    pen = BoundsPen(ufo_glyphset)
                    contour.draw(pen)
                    bounds = pen.bounds or (0, 0, 0, 0)
                    area = int((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
                    ufo_info_parts.append(f"uc{ci}({area})")
                entry["_ufo_info"] = f"{ufo_contour_count} contours: {','.join(ufo_info_parts)}"

            mapping["glyphs"][name] = entry
            ttf_count += 1

        elif ufo_contour_count >= 2:
            # TTF has 1 contour (merged) but UFO has multiple — use UFO contours
            contours = list(ufo_glyphset[name].contours)

            contour_info = []
            for ci, contour in enumerate(contours):
                pen = BoundsPen(ufo_glyphset)
                contour.draw(pen)
                bounds = pen.bounds or (0, 0, 0, 0)
                area = int((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
                contour_info.append(f"uc{ci}(area={area})")

            # Preserve existing contour mapping if present
            if "contours" in existing_entry:
                contour_map = existing_entry["contours"]
            elif args.holes_only:
                contour_map = classify_contours_ufo_holes_only(ufo_font, name)
            else:
                contour_map = classify_contours_ufo(ufo_font, name)

            mapping["glyphs"][name] = {
                "_info": f"{ttf_contours} ttf-contour, {ufo_contour_count} ufo-contours: {', '.join(contour_info)}",
                "_source": "ufo",
                "contours": contour_map
            }
            ufo_count += 1

        else:
            # Single contour in both TTF and UFO — simple single-region entry
            if "regions" in existing_entry:
                region_map = existing_entry["regions"]
            elif args.holes_only:
                region_map = {"0": SMART_COLOR_BASE}
            else:
                region_map = {"0": SMART_COLOR_ABOVE}

            mapping["glyphs"][name] = {
                "_info": f"1 region: r0(area={contour_bbox_area(glyph, 0)})",
                "regions": region_map
            }
            ttf_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved mapping scaffold to {output_path}")
    print(f"  {len(mapping['glyphs'])} glyph entries ({ttf_count} TTF regions, {ufo_count} UFO contours)")


if __name__ == "__main__":
    main()
