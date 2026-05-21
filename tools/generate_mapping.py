"""
Generate a color mapping scaffold JSON for manual region-to-color assignment.

Detects visual regions in each glyph (outer contour + its holes) and outputs
a JSON file where users assign palette colors per region.

Supports both UFO source (sees original contours before overlap removal)
and compiled TTF as input.

Usage:
    python tools/generate_mapping.py source/TiroTelugu-Regular.ufo
    python tools/generate_mapping.py output/.../TiroTelugu-Regular.ttf
    python tools/generate_mapping.py [input] --output path/to/color_mapping.json

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
    SMART_COLOR_BASE,
    SMART_COLOR_ABOVE,
    SMART_COLOR_BELOW,
    SMART_COLOR_CIRCULAR,
    SMART_COLOR_ELLIPTICAL,
    SMART_ASPECT_THRESHOLD,
)


def detect_regions_ufo(ufo_font, glyph_name):
    """Detect regions from UFO source: group outer contours with their hole children."""
    glyphset = ufo_font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)
    if not contours:
        return []

    info = []
    for i, contour in enumerate(contours):
        pen = BoundsPen(glyphset)
        contour.draw(pen)
        bounds = pen.bounds
        if bounds is None:
            info.append({"idx": i, "bounds": (0, 0, 0, 0), "is_outer": True, "area": 0})
            continue

        pts = [(pt.x, pt.y) for pt in contour]
        signed_area = 0
        for j in range(len(pts)):
            x1, y1 = pts[j]
            x2, y2 = pts[(j + 1) % len(pts)]
            signed_area += (x2 - x1) * (y2 + y1)

        bbox_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
        info.append({"idx": i, "bounds": bounds, "is_outer": signed_area > 0, "area": bbox_area})

    outers = [c for c in info if c["is_outer"]]
    inners = [c for c in info if not c["is_outer"]]

    outers.sort(key=lambda c: c["area"], reverse=True)

    regions = []
    assigned = set()

    for outer in outers:
        ob = outer["bounds"]
        holes = []
        for inner in inners:
            if inner["idx"] in assigned:
                continue
            ib = inner["bounds"]
            if ib[0] >= ob[0] and ib[1] >= ob[1] and ib[2] <= ob[2] and ib[3] <= ob[3]:
                holes.append(inner["idx"])
                assigned.add(inner["idx"])
        regions.append((outer["idx"], holes))

    for inner in inners:
        if inner["idx"] not in assigned:
            regions.append((inner["idx"], []))

    return regions


def classify_regions_smart_ufo(ufo_font, glyph_name, regions):
    """Assign colors based on region position/shape (UFO version)."""
    if not regions:
        return {}

    glyphset = ufo_font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)

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

    def contour_aspect(ci):
        b = contour_bounds(ci)
        w = b[2] - b[0]
        h = b[3] - b[1]
        if w == 0 or h == 0:
            return 1.0
        return max(w, h) / min(w, h)

    base_idx = max(range(len(regions)), key=lambda i: contour_area(regions[i][0]))
    base_cy = contour_centroid_y(regions[base_idx][0])

    mapping = {}
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        if ri == base_idx:
            mapping[str(ri)] = SMART_COLOR_BASE
        else:
            cy = contour_centroid_y(outer_idx)
            mapping[str(ri)] = SMART_COLOR_ABOVE if cy > base_cy else SMART_COLOR_BELOW

        for hi, hole_ci in enumerate(hole_indices):
            ar = contour_aspect(hole_ci)
            mapping[f"{ri}.h{hi}"] = SMART_COLOR_CIRCULAR if ar < SMART_ASPECT_THRESHOLD else SMART_COLOR_ELLIPTICAL

    return mapping


def main():
    parser = argparse.ArgumentParser(description="Generate color mapping scaffold JSON")
    parser.add_argument("input", nargs="?", help="Input UFO or TTF path")
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--auto-heuristic", action="store_true",
                        help="Pre-fill using size heuristic (largest region=0, rest=1)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    input_path = Path(args.input) if args.input else base_dir / "source" / "TiroTelugu-Regular.ufo"
    use_ufo = input_path.suffix == ".ufo" or input_path.is_dir()

    if args.output:
        output_path = Path(args.output)
    elif use_ufo:
        output_path = input_path / "data" / "color_mapping.json"
    else:
        ufo_data = base_dir / "source" / (input_path.stem + ".ufo") / "data"
        if ufo_data.parent.exists():
            output_path = ufo_data / "color_mapping.json"
        else:
            output_path = input_path.parent / "color_mapping.json"

    print(f"Loading {input_path}")

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

    if use_ufo:
        ufo = ufoLib2.Font.open(str(input_path))
        glyphset = ufo.layers.defaultLayer
        targets = [
            name for name in glyphset.keys()
            if is_telugu_glyph(name)
            and len(list(glyphset[name].contours)) >= 2
        ]
        targets.sort()

        print(f"Found {len(targets)} multi-contour Telugu glyphs (from UFO)")

        for name in targets:
            contours = list(glyphset[name].contours)
            regions = detect_regions_ufo(ufo, name)

            region_info = []
            for ri, (outer_idx, hole_indices) in enumerate(regions):
                pen = BoundsPen(glyphset)
                contours[outer_idx].draw(pen)
                bounds = pen.bounds or (0, 0, 0, 0)
                area = int((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
                holes_str = f"+{len(hole_indices)} holes" if hole_indices else ""
                region_info.append(f"r{ri}(area={area}{holes_str})")

            region_map = classify_regions_smart_ufo(ufo, name, regions)

            mapping["glyphs"][name] = {
                "_info": f"{len(regions)} regions: {', '.join(region_info)}",
                "regions": region_map
            }
    else:
        font = TTFont(str(input_path))
        glyf = font["glyf"]
        glyph_order = font.getGlyphOrder()

        targets = [
            name for name in glyph_order
            if is_telugu_glyph(name)
            and glyf[name].numberOfContours is not None
            and glyf[name].numberOfContours >= 2
        ]

        print(f"Found {len(targets)} multi-contour Telugu glyphs (from TTF)")

        for name in targets:
            glyph = glyf[name]
            regions = detect_regions(glyph)

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
