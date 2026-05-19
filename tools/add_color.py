"""
Add COLR v0 + CPAL color tables to TiroTelugu font.

Two styles available:
  --style contour : Split by contour size (largest=black, smaller=red)
  --style ats     : ATS-Chikkamagaluru style (colored fill + dark outline, 9-color palette)

Usage:
    python tools/add_color.py [--style contour|ats] [input.ttf] [output.ttf]

Defaults:
    input:  output/indigo/TiroTelugu/TTF/TiroTelugu-Regular.ttf
    output: output/indigo/TiroTelugu/TTF/TiroTelugu-Regular-Color.ttf
"""

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.colorLib.builder import buildCOLR, buildCPAL


# --- Contour style palette (original) ---
CONTOUR_PALETTE = [
    (0, 0, 0, 1.0),            # black (base)
    (0.8, 0.2, 0.2, 1.0),     # red (accent)
]

# --- ATS-Chikkamagaluru 9-color palette ---
ATS_PALETTE = [
    (0x1D/255, 0x1D/255, 0x1D/255, 1.0),  # [0] dark outline
    (0xEE/255, 0x34/255, 0x41/255, 1.0),  # [1] red
    (0xF1/255, 0xF0/255, 0x9A/255, 1.0),  # [2] light yellow
    (0xF7/255, 0xAC/255, 0xBA/255, 1.0),  # [3] pink
    (0xBB/255, 0x9C/255, 0xD4/255, 1.0),  # [4] lavender
    (0xEB/255, 0xA7/255, 0xD1/255, 1.0),  # [5] magenta
    (0xFB/255, 0xB8/255, 0x8F/255, 1.0),  # [6] peach
    (0x93/255, 0xD4/255, 0x9B/255, 1.0),  # [7] green
    (0x76/255, 0xCF/255, 0xE9/255, 1.0),  # [8] cyan
]

ATS_FILL_COLORS = [2, 3, 4, 5, 6, 7, 8]  # rotate through these for fill layer
ATS_OUTLINE_COLOR = 0                      # dark outline on top


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


def contour_bbox(glyph, contour_idx):
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    xs = [glyph.coordinates[i][0] for i in range(start, end + 1)]
    ys = [glyph.coordinates[i][1] for i in range(start, end + 1)]
    if not xs or not ys:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def contour_winding(glyph, contour_idx):
    """Return signed area. Positive = CW (outer), Negative = CCW (hole) in font coords."""
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    area = 0
    for i in range(start, end + 1):
        x1, y1 = glyph.coordinates[i]
        x2, y2 = glyph.coordinates[start + (i - start + 1) % (end - start + 1)]
        area += (x2 - x1) * (y2 + y1)
    return area


def detect_regions(glyph):
    """Group contours into regions: each outer CW contour + its CCW hole children.
    Returns list of (outer_idx, [hole_indices]) tuples."""
    num = glyph.numberOfContours
    if num is None or num < 1:
        return []

    contours = []
    for ci in range(num):
        bbox = contour_bbox(glyph, ci)
        winding = contour_winding(glyph, ci)
        contours.append({"idx": ci, "bbox": bbox, "is_outer": winding > 0})

    outers = [c for c in contours if c["is_outer"]]
    inners = [c for c in contours if not c["is_outer"]]

    regions = []
    assigned_inners = set()

    # Sort outers by area (largest first) so nesting works for complex cases
    outers.sort(key=lambda c: contour_bbox_area(glyph, c["idx"]), reverse=True)

    for outer in outers:
        ob = outer["bbox"]
        holes = []
        for inner in inners:
            if inner["idx"] in assigned_inners:
                continue
            ib = inner["bbox"]
            if ib[0] >= ob[0] and ib[1] >= ob[1] and ib[2] <= ob[2] and ib[3] <= ob[3]:
                holes.append(inner["idx"])
                assigned_inners.add(inner["idx"])
        regions.append((outer["idx"], holes))

    # Any unassigned inner contours become standalone regions
    for inner in inners:
        if inner["idx"] not in assigned_inners:
            regions.append((inner["idx"], []))

    return regions


def _extract_contours(source_glyph, contour_indices):
    new_glyph = Glyph()
    new_glyph.numberOfContours = len(contour_indices)

    coords = []
    flags = []
    end_pts = []

    for ci in sorted(contour_indices):
        start = 0 if ci == 0 else source_glyph.endPtsOfContours[ci - 1] + 1
        end = source_glyph.endPtsOfContours[ci]
        contour_coords = [source_glyph.coordinates[i] for i in range(start, end + 1)]
        contour_flags = [source_glyph.flags[i] for i in range(start, end + 1)]

        coords.extend(contour_coords)
        flags.extend(contour_flags)
        end_pts.append(len(coords) - 1)

    new_glyph.coordinates = GlyphCoordinates(coords)
    new_glyph.flags = bytes(flags) if isinstance(flags[0], int) else bytearray(flags)
    new_glyph.endPtsOfContours = end_pts
    new_glyph.program = Program()
    new_glyph.program.fromBytecode(b"")
    new_glyph.recalcBounds({"glyf": None})

    return new_glyph


def _clone_glyph(source_glyph):
    new_glyph = Glyph()
    new_glyph.numberOfContours = source_glyph.numberOfContours

    new_glyph.coordinates = GlyphCoordinates(list(source_glyph.coordinates))
    new_glyph.flags = bytes(source_glyph.flags)
    new_glyph.endPtsOfContours = list(source_glyph.endPtsOfContours)
    new_glyph.program = Program()
    new_glyph.program.fromBytecode(b"")
    new_glyph.xMin = source_glyph.xMin
    new_glyph.yMin = source_glyph.yMin
    new_glyph.xMax = source_glyph.xMax
    new_glyph.yMax = source_glyph.yMax

    return new_glyph


# --- Style: contour (original approach) ---

def build_contour_style(font, targets):
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    new_glyph_names = []
    for name in targets:
        new_glyph_names.append(f"{name}.base")
        new_glyph_names.append(f"{name}.accent")

    font.setGlyphOrder(font.getGlyphOrder() + new_glyph_names)

    color_layers = {}
    for name in targets:
        glyph = glyf[name]
        if glyph.numberOfContours < 2:
            continue

        num_contours = glyph.numberOfContours
        areas = [(i, contour_bbox_area(glyph, i)) for i in range(num_contours)]
        areas.sort(key=lambda x: x[1], reverse=True)
        largest_idx = areas[0][0]

        base_layer_name = f"{name}.base"
        accent_layer_name = f"{name}.accent"

        base_glyph = _extract_contours(glyph, [largest_idx])
        accent_glyph = _extract_contours(glyph, [i for i, _ in areas[1:]])

        glyf[base_layer_name] = base_glyph
        glyf[accent_layer_name] = accent_glyph

        width, lsb = hmtx[name]
        hmtx[base_layer_name] = (width, base_glyph.xMin if base_glyph.xMin is not None else lsb)
        hmtx[accent_layer_name] = (width, accent_glyph.xMin if accent_glyph.xMin is not None else lsb)

        color_layers[name] = [
            (base_layer_name, 0),
            (accent_layer_name, 1),
        ]

    font["CPAL"] = buildCPAL([CONTOUR_PALETTE])
    font["COLR"] = buildCOLR(color_layers)

    return len(color_layers)


# --- Style: ats (fill + outline, rotating colors) ---

def build_ats_style(font, targets):
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    new_glyph_names = []
    for name in targets:
        new_glyph_names.append(f"{name}.fill")

    font.setGlyphOrder(font.getGlyphOrder() + new_glyph_names)

    color_layers = {}
    for i, name in enumerate(targets):
        glyph = glyf[name]
        if glyph.numberOfContours is None or glyph.numberOfContours < 1:
            continue

        fill_name = f"{name}.fill"
        fill_glyph = _clone_glyph(glyph)
        glyf[fill_name] = fill_glyph

        width, lsb = hmtx[name]
        hmtx[fill_name] = (width, lsb)

        fill_color_idx = ATS_FILL_COLORS[i % len(ATS_FILL_COLORS)]
        color_layers[name] = [
            (fill_name, fill_color_idx),
        ]

    font["CPAL"] = buildCPAL([ATS_PALETTE])
    font["COLR"] = buildCOLR(color_layers)

    return len(color_layers)


# --- Style: manual (per-contour color from JSON mapping) ---

def _parse_glyph_mapping(entry, regions_list):
    """Parse a glyph entry into list of (contour_indices, palette_idx) layers.

    Supports:
      - "regions": {"0": 7, "0.h0": 3, "0.h1": 5, "1": 2}
        Region keys like "0" fill the whole region (outer+holes as cutouts).
        Hole keys like "0.h0" fill just that hole's interior on top.
      - "groups": [{"regions": [0], "color": 7}, ...]
    """
    layers = []

    if "groups" in entry:
        for g in entry["groups"]:
            contour_indices = _regions_to_contour_indices(regions_list, g["regions"])
            if contour_indices:
                layers.append((contour_indices, g["color"]))
        return layers

    region_entries = entry.get("regions", entry.get("contours", {}))

    # Separate region fills from hole fills
    region_fills = {}  # ri -> color
    hole_fills = []    # (contour_idx, color)

    for idx_str, color_idx in region_entries.items():
        if idx_str.startswith("_"):
            continue
        if ".h" in idx_str:
            # Hole fill: "0.h1" means hole index 1 of region 0
            parts = idx_str.split(".h")
            ri = int(parts[0])
            hi = int(parts[1])
            if ri < len(regions_list):
                _, hole_indices = regions_list[ri]
                if hi < len(hole_indices):
                    hole_fills.append((hole_indices[hi], color_idx))
        else:
            region_fills[int(idx_str)] = color_idx

    # Group regions by color for base layers
    color_to_regions = {}
    for ri, color in region_fills.items():
        color_to_regions.setdefault(color, []).append(ri)

    for color, region_indices in sorted(color_to_regions.items()):
        contour_indices = _regions_to_contour_indices(regions_list, region_indices)
        if contour_indices:
            layers.append((contour_indices, color))

    # Add hole fills as individual layers on top
    for contour_idx, color in hole_fills:
        layers.append(([contour_idx], color))

    return layers


def _regions_to_contour_indices(regions_list, region_indices):
    """Convert region indices to flat contour indices (outer + holes)."""
    contour_indices = []
    for ri in region_indices:
        if ri >= len(regions_list):
            continue
        outer_idx, hole_indices = regions_list[ri]
        contour_indices.append(outer_idx)
        contour_indices.extend(hole_indices)
    return contour_indices


def build_manual_style(font, targets, mapping_data):
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    defaults = mapping_data.get("defaults", {})
    unmapped_strategy = defaults.get("unmapped_glyphs", "auto:contour")
    glyph_mappings = mapping_data.get("glyphs", {})

    # First pass: determine all layer glyph names needed
    layer_plan = []
    new_glyph_names = []

    for i, name in enumerate(targets):
        glyph = glyf[name]
        if glyph.numberOfContours is None or glyph.numberOfContours < 1:
            continue

        num_contours = glyph.numberOfContours
        regions = detect_regions(glyph)

        if name in glyph_mappings:
            groups = _parse_glyph_mapping(glyph_mappings[name], regions)
        elif unmapped_strategy == "auto:contour" and len(regions) >= 2:
            # Largest region gets color 0, rest get color 1
            region_areas = [(ri, contour_bbox_area(glyph, outer)) for ri, (outer, _) in enumerate(regions)]
            region_areas.sort(key=lambda x: x[1], reverse=True)
            largest_ri = region_areas[0][0]
            largest_contours = _regions_to_contour_indices(regions, [largest_ri])
            rest_contours = _regions_to_contour_indices(regions, [ri for ri, _ in region_areas[1:]])
            groups = [
                (largest_contours, 0),
                (rest_contours, 1),
            ]
        elif unmapped_strategy == "auto:ats":
            fill_color_idx = ATS_FILL_COLORS[i % len(ATS_FILL_COLORS)]
            groups = [(list(range(num_contours)), fill_color_idx)]
        else:
            continue

        glyph_layers = []
        for contour_indices, palette_idx in groups:
            valid_indices = [ci for ci in contour_indices if ci < num_contours]
            if not valid_indices:
                continue

            layer_name = f"{name}.c{palette_idx}"
            suffix = 0
            while layer_name in new_glyph_names:
                suffix += 1
                layer_name = f"{name}.c{palette_idx}_{suffix}"

            new_glyph_names.append(layer_name)
            glyph_layers.append((layer_name, valid_indices, palette_idx))

        if glyph_layers:
            layer_plan.append((name, glyph_layers))

    # Set glyph order BEFORE adding glyphs
    font.setGlyphOrder(font.getGlyphOrder() + new_glyph_names)

    # Second pass: create layer glyphs and build color_layers
    color_layers = {}
    for name, glyph_layers in layer_plan:
        glyph = glyf[name]
        layers = []
        for layer_name, valid_indices, palette_idx in glyph_layers:
            layer_glyph = _extract_contours(glyph, valid_indices)
            glyf[layer_name] = layer_glyph

            width, lsb = hmtx[name]
            hmtx[layer_name] = (width, layer_glyph.xMin if layer_glyph.xMin is not None else lsb)
            layers.append((layer_name, palette_idx))

        color_layers[name] = layers

    font["CPAL"] = buildCPAL([ATS_PALETTE])
    font["COLR"] = buildCOLR(color_layers)

    return len(color_layers)


def main():
    parser = argparse.ArgumentParser(description="Add COLR/CPAL color to TiroTelugu font")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("output", nargs="?", help="Output TTF path")
    parser.add_argument("--style", choices=["contour", "ats", "manual"], default="contour",
                        help="Color style: contour (split by size), ats (fill, 9 colors), manual (JSON mapping)")
    parser.add_argument("--mapping", type=Path, help="JSON color mapping file (required for --style manual)")
    args = parser.parse_args()

    if args.style == "manual" and not args.mapping:
        parser.error("--mapping is required when --style manual")

    base_dir = Path(__file__).parent.parent

    input_path = Path(args.input) if args.input else base_dir / "output/indigo/TiroTelugu/TTF/TiroTelugu-Regular.ttf"
    if args.output:
        output_path = Path(args.output)
    else:
        suffix_map = {"contour": "-Color.ttf", "ats": "-ColorATS.ttf", "manual": "-ColorManual.ttf"}
        suffix = suffix_map[args.style]
        output_path = input_path.with_name(f"TiroTelugu-Regular{suffix}")

    print(f"Loading {input_path}")
    font = TTFont(str(input_path))

    glyf = font["glyf"]
    glyph_order = font.getGlyphOrder()

    if args.style == "contour":
        targets = [
            name for name in glyph_order
            if is_telugu_glyph(name)
            and glyf[name].numberOfContours is not None
            and glyf[name].numberOfContours >= 2
        ]
    else:
        targets = [
            name for name in glyph_order
            if is_telugu_glyph(name)
            and glyf[name].numberOfContours is not None
            and glyf[name].numberOfContours >= 1
        ]

    mapping_data = None
    if args.style == "manual":
        mapping_data = json.loads(args.mapping.read_text(encoding="utf-8"))

    print(f"Found {len(targets)} target Telugu glyphs (style: {args.style})")

    if args.style == "contour":
        count = build_contour_style(font, targets)
    elif args.style == "ats":
        count = build_ats_style(font, targets)
    else:
        count = build_manual_style(font, targets, mapping_data)

    print(f"Added color layers for {count} glyphs")
    print(f"Saving {output_path}")
    font.save(str(output_path))
    print("Done!")


if __name__ == "__main__":
    main()
