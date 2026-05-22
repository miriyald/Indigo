"""
Add COLR v0 + CPAL color tables to TiroTelugu font.

Three styles available:
  --style region  : Split by region size (largest=black, smaller=red)
  --style ats     : ATS-Chikkamagaluru style (colored fill + dark outline, 9-color palette)
  --style manual  : Per-region color from JSON mapping

Usage:
    python tools/add_color.py [--style region|ats|manual] [--ufo source.ufo] [input.ttf] [output.ttf]

The --ufo flag extracts layer glyph outlines from the original UFO source,
preserving contours that overlap removal would merge in the compiled TTF.

Defaults:
    input:  output/indigo/TiroTelugu/TTF/TiroTelugu-Regular.ttf
    output: output/indigo/TiroTelugu/TTF/TiroTelugu-Regular-Color.ttf
"""

import argparse
import json
from pathlib import Path

import ufoLib2
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.colorLib.builder import buildCOLR, buildCPAL


# --- Region style palette (size heuristic) ---
REGION_PALETTE = [
    (0, 0, 0, 1.0),            # black (base)
    (0.8, 0.2, 0.2, 1.0),     # red (accent)
]

# --- ATS-Chikkamagaluru 9-color palette ---
ATS_PALETTE = [
    (0x1D/255, 0x1D/255, 0x1D/255, 1.0),  # [0] dark outline
    (0xEE/255, 0x34/255, 0x41/255, 1.0),  # [1] 
    (0xBB/255, 0x9C/255, 0xD4/255, 1.0),  # [2] lavender
    (0xF7/255, 0xAC/255, 0xBA/255, 1.0),  # [3] pink
    (0xF1/255, 0xF0/255, 0x9A/255, 1.0),  # [4] light yellow
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


def contour_centroid(glyph, contour_idx):
    xmin, ymin, xmax, ymax = contour_bbox(glyph, contour_idx)
    return ((xmin + xmax) / 2, (ymin + ymax) / 2)


def contour_aspect_ratio(glyph, contour_idx):
    xmin, ymin, xmax, ymax = contour_bbox(glyph, contour_idx)
    w = xmax - xmin
    h = ymax - ymin
    if w == 0 or h == 0:
        return 1.0
    return max(w, h) / min(w, h)


SMART_COLOR_BASE = 0
SMART_COLOR_ABOVE = 5
SMART_COLOR_BELOW = 7
SMART_COLOR_CIRCULAR = 2
SMART_COLOR_ELLIPTICAL = 4
SMART_ASPECT_THRESHOLD = 1.5


def classify_regions_smart(glyph):
    regions = detect_regions(glyph)
    if not regions:
        return {}

    base_idx = max(range(len(regions)), key=lambda i: contour_bbox_area(glyph, regions[i][0]))
    base_cy = contour_centroid(glyph, regions[base_idx][0])[1]

    mapping = {}
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        if ri == base_idx:
            mapping[str(ri)] = SMART_COLOR_BASE
        else:
            cy = contour_centroid(glyph, outer_idx)[1]
            mapping[str(ri)] = SMART_COLOR_ABOVE if cy > base_cy else SMART_COLOR_BELOW

        for hi, hole_ci in enumerate(hole_indices):
            ar = contour_aspect_ratio(glyph, hole_ci)
            mapping[f"{ri}.h{hi}"] = SMART_COLOR_CIRCULAR if ar < SMART_ASPECT_THRESHOLD else SMART_COLOR_ELLIPTICAL

    return mapping


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


def detect_regions_ufo(ufo_font, glyph_name):
    """Detect regions from UFO source (sees original contours before overlap removal)."""
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


def _extract_contours_ufo(ufo_font, glyph_name, contour_indices):
    """Extract specific contours from a UFO glyph and return a TrueType Glyph object."""
    glyphset = ufo_font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)

    tt_pen = TTGlyphPen(None)
    cu2qu_pen = Cu2QuPen(tt_pen, max_err=1.0, reverse_direction=False)
    for ci in sorted(contour_indices):
        contours[ci].draw(cu2qu_pen)
    tt_glyph = tt_pen.glyph()
    tt_glyph.recalcBounds({"glyf": None})
    return tt_glyph


# --- Style: region (split by size) ---

def build_region_style(font, targets):
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

    font["CPAL"] = buildCPAL([REGION_PALETTE])
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


# --- Style: manual (per-region color from JSON mapping) ---

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


def _parse_contours_mapping(entry):
    """Parse a UFO-sourced 'contours' entry into (contour_indices, palette_idx) groups."""
    contour_entries = entry.get("contours", {})
    color_to_contours = {}
    for idx_str, color_idx in contour_entries.items():
        if idx_str.startswith("_"):
            continue
        color_to_contours.setdefault(color_idx, []).append(int(idx_str))

    layers = []
    for color, indices in sorted(color_to_contours.items()):
        layers.append((sorted(indices), color))
    return layers


def build_manual_style(font, targets, mapping_data, ufo_font=None):
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    defaults = mapping_data.get("defaults", {})
    unmapped_strategy = defaults.get("unmapped_glyphs", "auto:region")
    glyph_mappings = mapping_data.get("glyphs", {})

    ufo_glyphset = ufo_font.layers.defaultLayer if ufo_font else None

    # First pass: determine all layer glyph names needed
    layer_plan = []
    new_glyph_names = []

    for i, name in enumerate(targets):
        glyph = glyf[name]
        if glyph.numberOfContours is None or glyph.numberOfContours < 1:
            continue

        entry = glyph_mappings.get(name)
        use_ufo_for_glyph = (entry and entry.get("_source") == "ufo"
                             and ufo_font and ufo_glyphset and name in ufo_glyphset)
        # Also use UFO when ufo_contours key is present and UFO source is available
        use_ufo_contours = (entry and "ufo_contours" in entry
                            and ufo_font and ufo_glyphset and name in ufo_glyphset)

        if use_ufo_for_glyph:
            num_contours = len(list(ufo_glyphset[name].contours))
            groups = _parse_contours_mapping(entry)
        elif use_ufo_contours:
            num_contours = len(list(ufo_glyphset[name].contours))
            groups = _parse_contours_mapping({"contours": entry["ufo_contours"]})
        else:
            num_contours = glyph.numberOfContours
            regions = detect_regions(glyph)

            if entry and "regions" in entry:
                groups = _parse_glyph_mapping(entry, regions)
            elif unmapped_strategy in ("auto:region", "auto:contour") and len(regions) >= 2:
                smart_map = classify_regions_smart(glyph)
                groups = list(_parse_glyph_mapping({"regions": smart_map}, regions))
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
            glyph_layers.append((layer_name, valid_indices, palette_idx, use_ufo_for_glyph or use_ufo_contours))

        if glyph_layers:
            layer_plan.append((name, glyph_layers))

    # Set glyph order BEFORE adding glyphs
    font.setGlyphOrder(font.getGlyphOrder() + new_glyph_names)

    # Second pass: create layer glyphs and build color_layers
    color_layers = {}
    for name, glyph_layers in layer_plan:
        glyph = glyf[name]
        layers = []
        for layer_name, valid_indices, palette_idx, from_ufo in glyph_layers:
            if from_ufo:
                layer_glyph = _extract_contours_ufo(ufo_font, name, valid_indices)
            else:
                layer_glyph = _extract_contours(glyph, valid_indices)
            glyf[layer_name] = layer_glyph

            width, lsb = hmtx[name]
            hmtx[layer_name] = (width, layer_glyph.xMin if layer_glyph.xMin is not None else lsb)
            layers.append((layer_name, palette_idx))

        color_layers[name] = layers

    font["CPAL"] = buildCPAL([ATS_PALETTE])
    font["COLR"] = buildCOLR(color_layers)

    return len(color_layers)


COLOR_FONT_META = {
    "copyright": "Copyright 2020 The Indigo Project Authors (https://github.com/TiroTypeworks/Indigo). Color version copyright 2026 Dileep Miriyala.",
    "designer": "Telugu: John Hudson & Fiona Ross. Color: Dileep Miriyala.",
    "vendor_url": "https://github.com/miriyald/Indigo",
}


def _update_color_name_table(font, family_suffix="Color"):
    """Update name table to establish the color font as a separate family."""
    name_table = font["name"]

    # Read base family name from existing name table
    base_family = None
    for record in name_table.names:
        if record.nameID == 1 and record.platformID == 3:
            base_family = record.toUnicode()
            break
    if not base_family:
        base_family = "Tiro Telugu"

    color_family = f"{base_family} {family_suffix}"
    ps_family = base_family.replace(" ", "") + family_suffix.replace(" ", "")
    ps_name = f"{ps_family}-Regular"

    entries = {
        0: COLOR_FONT_META["copyright"],
        1: color_family,
        2: "Regular",
        4: color_family,
        6: ps_name,
        9: COLOR_FONT_META["designer"],
        11: COLOR_FONT_META["vendor_url"],
        16: color_family,
        17: "Regular",
    }

    for name_id, value in entries.items():
        name_table.setName(value, name_id, 3, 1, 0x0409)
        name_table.setName(value, name_id, 1, 0, 0)


def main():
    parser = argparse.ArgumentParser(description="Add COLR/CPAL color to TiroTelugu font")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("output", nargs="?", help="Output TTF path")
    parser.add_argument("--style", choices=["region", "ats", "manual", "contour"], default="region",
                        help="Color style: region (split by size), ats (fill, 9 colors), manual (JSON mapping)")
    parser.add_argument("--mapping", type=Path, help="JSON color mapping file (default: color_mapping.json next to input TTF)")
    parser.add_argument("--ufo", type=Path, help="UFO source for layer glyph extraction (sees contours before overlap removal)")
    parser.add_argument("--family-suffix", default="Color", help="Suffix for color font family name (default: Color)")
    args = parser.parse_args()

    if args.style == "contour":
        args.style = "region"

    base_dir = Path(__file__).parent.parent

    input_path = Path(args.input) if args.input else base_dir / "output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf"

    if args.style == "manual" and not args.mapping:
        # Check UFO data/ folder first, then next to input TTF
        ufo_data = base_dir / "source" / (input_path.stem + ".ufo") / "data" / "color_mapping.json"
        ttf_sibling = input_path.parent / "color_mapping.json"
        if ufo_data.exists():
            args.mapping = ufo_data
        elif ttf_sibling.exists():
            args.mapping = ttf_sibling
        else:
            parser.error(f"--mapping is required when --style manual (no color_mapping.json found in UFO data/ or next to input TTF)")

    if args.output:
        output_path = Path(args.output)
    else:
        suffix_map = {"region": "-Color.ttf", "ats": "-ColorATS.ttf", "manual": "-ColorManual.ttf"}
        suffix = suffix_map[args.style]
        output_path = input_path.with_name(input_path.stem + suffix)

    print(f"Loading {input_path}")
    font = TTFont(str(input_path))

    glyf = font["glyf"]
    glyph_order = font.getGlyphOrder()

    if args.style == "region":
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

    ufo_font = None
    if args.ufo:
        print(f"Loading UFO source {args.ufo}")
        ufo_font = ufoLib2.Font.open(str(args.ufo))

    if args.style == "region":
        count = build_region_style(font, targets)
    elif args.style == "ats":
        count = build_ats_style(font, targets)
    else:
        count = build_manual_style(font, targets, mapping_data, ufo_font=ufo_font)

    print(f"Added color layers for {count} glyphs")

    _update_color_name_table(font, args.family_suffix)
    print(f"Updated name table: family = '{font['name'].getDebugName(1)}'")

    print(f"Saving {output_path}")
    font.save(str(output_path))
    print("Done!")


if __name__ == "__main__":
    main()
