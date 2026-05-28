"""
Colorize Telugu font glyphs using COLR v0 + CPAL.

Automatically classifies glyph regions into 6 semantic categories
based on geometry: Base, Above, Disconnected, Below, Post-base, Holes.
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import ufoLib2
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.colorLib.builder import buildCOLR, buildCPAL

# --- Categories ---

CAT_BASE = 0
CAT_ABOVE = 1
CAT_DISCONNECTED = 2
CAT_BELOW = 3
CAT_POSTBASE = 4
CAT_HOLE = 5

CATEGORY_NAMES = ["base", "above", "disconnected", "below", "postbase", "hole"]

# 6-color RGBA palette (normalized 0-1)
PALETTE = [
    (0x1A / 255, 0x1A / 255, 0x2E / 255, 1.0),  # 0 BASE: dark navy
    (0xE6 / 255, 0x4A / 255, 0x19 / 255, 1.0),  # 1 ABOVE: vermilion
    (0x2E / 255, 0xCC / 255, 0x71 / 255, 1.0),  # 2 DISCONNECTED: emerald
    (0x34 / 255, 0x98 / 255, 0xDB / 255, 1.0),  # 3 BELOW: blue
    (0x9B / 255, 0x59 / 255, 0xB6 / 255, 1.0),  # 4 POSTBASE: purple
    (0xF5 / 255, 0xD0 / 255, 0x7A / 255, 1.0),  # 5 HOLE: light warm amber
]

BBOX_OVERLAP_TOLERANCE = 10
POSTBASE_X_THRESHOLD = 0.7
TOUCHING_OVERLAP_RATIO = 0.5  # if >50% of a region's bbox overlaps the base, they're touching


# --- Geometry Utilities ---


def _ttf_contour_points(glyph, contour_idx):
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    return [(glyph.coordinates[i][0], glyph.coordinates[i][1]) for i in range(start, end + 1)]


def contour_winding_ttf(glyph, contour_idx):
    pts = _ttf_contour_points(glyph, contour_idx)
    area = 0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += (x2 - x1) * (y2 + y1)
    return area


def contour_bbox_ttf(glyph, contour_idx):
    pts = _ttf_contour_points(glyph, contour_idx)
    if not pts:
        return (0, 0, 0, 0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_area(bbox):
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def bbox_centroid(bbox):
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def bboxes_overlap(b1, b2, tolerance=0):
    return not (
        b1[2] - tolerance <= b2[0] or
        b2[2] - tolerance <= b1[0] or
        b1[3] - tolerance <= b2[1] or
        b2[3] - tolerance <= b1[1]
    )


def bbox_overlap_ratio(smaller, larger):
    """What fraction of the smaller bbox's area overlaps with the larger bbox."""
    ox = max(0, min(smaller[2], larger[2]) - max(smaller[0], larger[0]))
    oy = max(0, min(smaller[3], larger[3]) - max(smaller[1], larger[1]))
    overlap_area = ox * oy
    smaller_area = bbox_area(smaller)
    if smaller_area == 0:
        return 0
    return overlap_area / smaller_area


def contour_winding_ufo(contour):
    pts = [(pt.x, pt.y) for pt in contour]
    area = 0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += (x2 - x1) * (y2 + y1)
    return area


def contour_bbox_ufo(contour, glyphset):
    pen = BoundsPen(glyphset)
    contour.draw(pen)
    bounds = pen.bounds
    if bounds is None:
        return (0, 0, 0, 0)
    return bounds


# --- Region Detection ---


@dataclass
class Region:
    outer_idx: int
    hole_indices: list = field(default_factory=list)
    bbox: tuple = (0, 0, 0, 0)
    area: float = 0.0
    centroid: tuple = (0.0, 0.0)
    is_hole_only: bool = False


def detect_regions_ttf(glyph):
    num = glyph.numberOfContours
    if num is None or num < 1:
        return []

    contours = []
    for ci in range(num):
        bbox = contour_bbox_ttf(glyph, ci)
        winding = contour_winding_ttf(glyph, ci)
        contours.append({"idx": ci, "bbox": bbox, "is_outer": winding > 0, "area": bbox_area(bbox)})

    outers = sorted([c for c in contours if c["is_outer"]], key=lambda c: c["area"], reverse=True)
    inners = [c for c in contours if not c["is_outer"]]

    regions = []
    assigned = set()

    for outer in outers:
        ob = outer["bbox"]
        holes = []
        for inner in inners:
            if inner["idx"] in assigned:
                continue
            ib = inner["bbox"]
            if ib[0] >= ob[0] and ib[1] >= ob[1] and ib[2] <= ob[2] and ib[3] <= ob[3]:
                holes.append(inner["idx"])
                assigned.add(inner["idx"])
        regions.append(Region(
            outer_idx=outer["idx"],
            hole_indices=holes,
            bbox=ob,
            area=outer["area"],
            centroid=bbox_centroid(ob),
        ))

    for inner in inners:
        if inner["idx"] not in assigned:
            regions.append(Region(
                outer_idx=inner["idx"],
                hole_indices=[],
                bbox=inner["bbox"],
                area=inner["area"],
                centroid=bbox_centroid(inner["bbox"]),
                is_hole_only=True,
            ))

    return regions


def detect_regions_ufo(ufo_font, glyph_name):
    glyphset = ufo_font.layers.defaultLayer
    if glyph_name not in glyphset:
        return []
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)
    if not contours:
        return []

    info = []
    for i, contour in enumerate(contours):
        bounds = contour_bbox_ufo(contour, glyphset)
        winding = contour_winding_ufo(contour)
        area = bbox_area(bounds)
        # UFO/PostScript convention: CCW (negative winding) = outer, CW (positive) = hole
        info.append({"idx": i, "bbox": bounds, "is_outer": winding < 0, "area": area})

    outers = sorted([c for c in info if c["is_outer"]], key=lambda c: c["area"], reverse=True)
    inners = [c for c in info if not c["is_outer"]]

    regions = []
    assigned = set()

    for outer in outers:
        ob = outer["bbox"]
        holes = []
        for inner in inners:
            if inner["idx"] in assigned:
                continue
            ib = inner["bbox"]
            if ib[0] >= ob[0] and ib[1] >= ob[1] and ib[2] <= ob[2] and ib[3] <= ob[3]:
                holes.append(inner["idx"])
                assigned.add(inner["idx"])
        regions.append(Region(
            outer_idx=outer["idx"],
            hole_indices=holes,
            bbox=ob,
            area=outer["area"],
            centroid=bbox_centroid(ob),
        ))

    for inner in inners:
        if inner["idx"] not in assigned:
            regions.append(Region(
                outer_idx=inner["idx"],
                hole_indices=[],
                bbox=inner["bbox"],
                area=inner["area"],
                centroid=bbox_centroid(inner["bbox"]),
                is_hole_only=True,
            ))

    return regions


# --- Classification ---


TOUCHING_Y_OVERLAP = 0.5  # y-ranges must overlap by 50% of smaller height to be "same stroke"
TOUCHING_Y_OVERLAP_LENIENT = 0.01  # for substantial regions: any bbox overlap = connected
SUBSTANTIAL_SIZE_RATIO = 0.30  # region > 30% of base area = structural part, not a mark


def _regions_connected(r1, r2, tolerance, base_area=None):
    """Two regions are connected if their bboxes overlap AND they share significant vertical range.
    For substantial regions (>30% of base), use lenient threshold since vertically stacked
    connected strokes barely overlap at their junction point — but NOT if the smaller region
    is positioned above the larger (that's a separate mark, not a connected stroke)."""
    if not bboxes_overlap(r1.bbox, r2.bbox, tolerance):
        return False
    y_overlap = max(0, min(r1.bbox[3], r2.bbox[3]) - max(r1.bbox[1], r2.bbox[1]))
    h1 = r1.bbox[3] - r1.bbox[1]
    h2 = r2.bbox[3] - r2.bbox[1]
    smaller_h = min(h1, h2)
    if smaller_h == 0:
        return False
    y_ratio = y_overlap / smaller_h

    # For substantial regions, any bbox overlap means they're physically connected
    # UNLESS the smaller region sits above the larger one (separate mark)
    if base_area and base_area > 0:
        smaller_area = min(r1.area, r2.area)
        if smaller_area / base_area >= SUBSTANTIAL_SIZE_RATIO:
            # Determine which is the smaller region
            smaller_r = r1 if r1.area <= r2.area else r2
            larger_r = r2 if r1.area <= r2.area else r1
            # If smaller region's centroid is above the larger's top edge, it's a mark
            if smaller_r.centroid[1] > larger_r.bbox[3]:
                return y_ratio >= TOUCHING_Y_OVERLAP
            return y_ratio >= TOUCHING_Y_OVERLAP_LENIENT

    return y_ratio >= TOUCHING_Y_OVERLAP


def _find_touching_group(regions, seed_indices, tolerance, base_area=None):
    """Transitively find all regions connected to the seed group."""
    group = set(seed_indices)
    changed = True
    while changed:
        changed = False
        for i, region in enumerate(regions):
            if i in group or region.is_hole_only:
                continue
            for gi in list(group):
                if _regions_connected(region, regions[gi], tolerance, base_area):
                    group.add(i)
                    changed = True
                    break
    return group


def classify_regions(regions, transitive=True):
    if not regions:
        return {}

    non_holes = [r for r in regions if not r.is_hole_only]
    if not non_holes:
        return {CAT_HOLE: regions}

    base = max(non_holes, key=lambda r: r.area)
    base_idx = regions.index(base)

    # Find all regions that are part of the base (touching chain)
    if transitive:
        base_group = _find_touching_group(regions, {base_idx}, BBOX_OVERLAP_TOLERANCE, base.area)
    else:
        base_group = {base_idx}
        for i, region in enumerate(regions):
            if i == base_idx or region.is_hole_only:
                continue
            if bbox_overlap_ratio(region.bbox, base.bbox) > TOUCHING_OVERLAP_RATIO:
                base_group.add(i)

    result = {cat: [] for cat in range(6)}
    for i in base_group:
        result[CAT_BASE].append(regions[i])

    # Compute combined base group bbox for positional classification
    base_group_bboxes = [regions[i].bbox for i in base_group]
    combined_base_bbox = (
        min(b[0] for b in base_group_bboxes),
        min(b[1] for b in base_group_bboxes),
        max(b[2] for b in base_group_bboxes),
        max(b[3] for b in base_group_bboxes),
    )
    combined_base_centroid = bbox_centroid(combined_base_bbox)

    for i, region in enumerate(regions):
        if i in base_group:
            continue

        if region.is_hole_only:
            result[CAT_HOLE].append(region)
            continue

        # Check if region's x-range overlaps the combined base x-range
        x_overlaps_base = not (
            region.bbox[2] < combined_base_bbox[0] - BBOX_OVERLAP_TOLERANCE or
            region.bbox[0] > combined_base_bbox[2] + BBOX_OVERLAP_TOLERANCE
        )

        # Truly disconnected: no bbox overlap AND no x-range overlap with base
        if not bboxes_overlap(region.bbox, combined_base_bbox, BBOX_OVERLAP_TOLERANCE) and not x_overlaps_base:
            result[CAT_DISCONNECTED].append(region)
        else:
            base_width = combined_base_bbox[2] - combined_base_bbox[0]
            x_threshold = combined_base_bbox[0] + POSTBASE_X_THRESHOLD * base_width

            if region.centroid[0] > x_threshold and region.centroid[1] < combined_base_centroid[1]:
                result[CAT_POSTBASE].append(region)
            elif region.centroid[1] > combined_base_centroid[1]:
                result[CAT_ABOVE].append(region)
            else:
                result[CAT_BELOW].append(region)

    return result


# --- Layer Glyph Building ---


def extract_contours_ttf(source_glyph, contour_indices):
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


def extract_contours_ttf_reversed(source_glyph, contour_indices):
    """Extract contours with reversed point order (CCW→CW) so holes render filled."""
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

        contour_coords.reverse()
        contour_flags.reverse()

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


def extract_contours_ufo(ufo_font, glyph_name, contour_indices, reverse=False):
    glyphset = ufo_font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)

    tt_pen = TTGlyphPen(None)
    cu2qu_pen = Cu2QuPen(tt_pen, max_err=1.0, reverse_direction=reverse)
    for ci in sorted(contour_indices):
        contours[ci].draw(cu2qu_pen)
    tt_glyph = tt_pen.glyph()
    tt_glyph.recalcBounds({"glyf": None})
    return tt_glyph


# --- Main Colorization ---


def is_telugu_glyph(name):
    if not name or len(name) < 2:
        return False
    if not name.startswith("t"):
        return False
    return name[1].isupper()


def colorize_font(font, ufo_font, targets, tolerance=BBOX_OVERLAP_TOLERANCE, verbose=False, overrides=None):
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    # Pass 1: classify all glyphs and determine which layer names will be created
    glyph_plans = []

    for glyph_name in targets:
        ttf_glyph = glyf[glyph_name]
        if ttf_glyph.numberOfContours is None or ttf_glyph.numberOfContours < 1:
            continue

        # Always detect TTF regions (gives us reliable holes post-overlap-removal)
        ttf_regions = detect_regions_ttf(ttf_glyph)

        # Use UFO for region classification when it has more outer contours
        # (TTF overlap removal merged separate shapes into one)
        use_ufo = False
        ufo_regions = []
        if ufo_font:
            glyphset = ufo_font.layers.defaultLayer
            if glyph_name in glyphset:
                ufo_regions = detect_regions_ufo(ufo_font, glyph_name)
                ufo_outers = len([r for r in ufo_regions if not r.is_hole_only])
                ttf_outers = len([r for r in ttf_regions if not r.is_hole_only])
                if ufo_outers > ttf_outers:
                    use_ufo = True

        # For classification of outer regions, use UFO if it has more;
        # for holes, always use TTF (overlap removal reveals true visual holes)
        if use_ufo:
            regions = ufo_regions
        else:
            regions = ttf_regions

        if not regions:
            continue

        all_holes_count = sum(len(r.hole_indices) for r in ttf_regions)
        if len(regions) == 1 and all_holes_count == 0 and not use_ufo:
            continue
        if not use_ufo and len(ttf_regions) == 1 and all_holes_count == 0:
            continue

        classified = classify_regions(regions)

        # Apply manual overrides if present
        if overrides and glyph_name in overrides:
            classified = apply_overrides(regions, classified, overrides[glyph_name])
            if verbose:
                print(f"  {glyph_name}: overrides applied")

        # Holes always come from TTF (post-overlap-removal gives true visual holes)
        hole_contour_indices_ttf = []
        for region in ttf_regions:
            hole_contour_indices_ttf.extend(region.hole_indices)
        for region in classified.get(CAT_HOLE, []):
            if not use_ufo:
                hole_contour_indices_ttf.append(region.outer_idx)

        glyph_plans.append({
            "name": glyph_name,
            "use_ufo": use_ufo,
            "regions": regions,
            "ttf_regions": ttf_regions,
            "classified": classified,
            "hole_indices_ttf": hole_contour_indices_ttf,
        })

    # Pre-register all layer glyph names
    layer_order = [CAT_BASE, CAT_HOLE, CAT_BELOW, CAT_POSTBASE, CAT_DISCONNECTED, CAT_ABOVE]
    all_layer_names = []
    for plan in glyph_plans:
        for cat in layer_order:
            cat_regions = plan["classified"].get(cat, [])
            if cat == CAT_HOLE:
                if plan["hole_indices_ttf"]:
                    all_layer_names.append(f"{plan['name']}.{CATEGORY_NAMES[cat]}")
            elif cat_regions:
                all_layer_names.append(f"{plan['name']}.{CATEGORY_NAMES[cat]}")

    font.setGlyphOrder(font.getGlyphOrder() + all_layer_names)

    # Pass 2: build layer glyphs
    color_layers = {}
    stats = {name: 0 for name in CATEGORY_NAMES}

    for plan in glyph_plans:
        glyph_name = plan["name"]
        use_ufo = plan["use_ufo"]
        classified = plan["classified"]
        hole_contour_indices_ttf = plan["hole_indices_ttf"]
        ttf_glyph = glyf[glyph_name]

        layers_for_glyph = []
        width = hmtx[glyph_name][0]

        for cat in layer_order:
            cat_regions = classified.get(cat, [])
            if not cat_regions and cat != CAT_HOLE:
                continue

            if cat == CAT_HOLE:
                # Holes always extracted from TTF (post-overlap-removal = true visual holes)
                indices = hole_contour_indices_ttf
                if not indices:
                    continue
            elif cat == CAT_BASE:
                base_region = cat_regions[0]
                indices = [base_region.outer_idx] + base_region.hole_indices
            else:
                indices = []
                for region in cat_regions:
                    indices.append(region.outer_idx)
                    indices.extend(region.hole_indices)

            if not indices:
                continue

            layer_name = f"{glyph_name}.{CATEGORY_NAMES[cat]}"

            if cat == CAT_HOLE:
                # Holes always from TTF, reversed winding to render filled
                layer_glyph = extract_contours_ttf_reversed(ttf_glyph, indices)
            elif cat == CAT_BASE:
                # Base always from TTF (includes proper hole cutouts from overlap removal)
                ttf_base_region = plan["ttf_regions"][0] if plan["ttf_regions"] else None
                if ttf_base_region:
                    base_indices = [ttf_base_region.outer_idx] + ttf_base_region.hole_indices
                    layer_glyph = extract_contours_ttf(ttf_glyph, base_indices)
                else:
                    layer_glyph = extract_contours_ttf(ttf_glyph, indices)
            elif use_ufo:
                layer_glyph = extract_contours_ufo(ufo_font, glyph_name, indices, reverse=False)
            else:
                layer_glyph = extract_contours_ttf(ttf_glyph, indices)

            glyf[layer_name] = layer_glyph
            hmtx[layer_name] = (width, layer_glyph.xMin if hasattr(layer_glyph, 'xMin') else 0)
            layers_for_glyph.append((layer_name, cat))
            stats[CATEGORY_NAMES[cat]] += 1

        if layers_for_glyph:
            color_layers[glyph_name] = layers_for_glyph

        if verbose:
            cats_present = [CATEGORY_NAMES[cat] for _, cat in layers_for_glyph]
            src = "ufo" if use_ufo else "ttf"
            print(f"  {glyph_name} [{src}]: {', '.join(cats_present)}")

    return color_layers, stats, glyph_plans


OVERRIDES_FILENAME = "colorize_overrides.csv"


def export_classification(glyph_plans, output_path, preserve_existing=True):
    """Export auto-classification to CSV. Preserves manual edits if file exists."""
    existing_overrides = {}

    if preserve_existing and output_path.exists():
        existing_overrides = load_overrides(output_path)

    lines = ["glyph,region,category,bbox,info"]
    for plan in glyph_plans:
        glyph_name = plan["name"]
        regions = plan["regions"]
        classified = plan["classified"]

        region_cats = {}
        for cat, cat_regions in classified.items():
            for region in cat_regions:
                idx = regions.index(region)
                region_cats[idx] = CATEGORY_NAMES[cat]

        for idx in sorted(region_cats.keys()):
            region = regions[idx]
            if glyph_name in existing_overrides and idx in existing_overrides[glyph_name]:
                cat_name = existing_overrides[glyph_name][idx]
            else:
                cat_name = region_cats[idx]

            bbox_str = f"\"({region.bbox[0]:.0f},{region.bbox[1]:.0f},{region.bbox[2]:.0f},{region.bbox[3]:.0f})\""
            info = "largest" if idx == 0 and cat_name == "base" else ""
            lines.append(f"{glyph_name},{idx},{cat_name},{bbox_str},{info}")

    with open(output_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    return output_path


def load_overrides(path):
    """Load CSV overrides. Returns {glyph_name: {region_idx: category_name}}."""
    import csv
    overrides = {}
    if not path.exists():
        return overrides

    valid_cats = set(CATEGORY_NAMES)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#") or row[0] == "glyph":
                continue
            if len(row) < 3:
                continue
            glyph_name = row[0]
            try:
                region_idx = int(row[1])
            except ValueError:
                continue
            cat_name = row[2]
            if cat_name not in valid_cats:
                continue
            if glyph_name not in overrides:
                overrides[glyph_name] = {}
            overrides[glyph_name][region_idx] = cat_name
    return overrides


def apply_overrides(regions, classified, overrides_for_glyph):
    """Replace auto-classification with manual overrides for a single glyph."""
    cat_name_to_idx = {name: idx for idx, name in enumerate(CATEGORY_NAMES)}

    new_classified = {cat: [] for cat in range(6)}
    for i, region in enumerate(regions):
        if i in overrides_for_glyph:
            cat = cat_name_to_idx[overrides_for_glyph[i]]
        else:
            # Keep auto-classification
            for cat_idx, cat_regions in classified.items():
                if region in cat_regions:
                    cat = cat_idx
                    break
            else:
                cat = CAT_BASE
        new_classified[cat].append(region)

    return new_classified


def assemble_color_tables(font, color_layers):
    font["CPAL"] = buildCPAL([PALETTE])
    font["COLR"] = buildCOLR(color_layers)


def main():
    parser = argparse.ArgumentParser(
        description="Colorize Telugu font glyphs (COLR v0 + CPAL, 6-category auto-classification)"
    )
    parser.add_argument("ttf", help="Input TTF font path")
    parser.add_argument("--ufo", type=Path, help="UFO source directory")
    parser.add_argument("--output", "-o", type=Path, help="Output TTF path")
    parser.add_argument("--tolerance", type=float, default=BBOX_OVERLAP_TOLERANCE,
                        help=f"Bbox overlap tolerance for disconnected detection (default: {BBOX_OVERLAP_TOLERANCE})")
    parser.add_argument("--export", nargs="?", const=True, default=False,
                        help="Export classification to TSV (optionally specify path)")
    parser.add_argument("--overrides", type=Path,
                        help="Path to overrides TSV (auto-discovered from UFO data/ if not specified)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    font = TTFont(args.ttf)
    ufo_font = ufoLib2.Font.open(str(args.ufo)) if args.ufo else None

    # Auto-discover overrides from UFO data folder
    overrides = None
    overrides_path = args.overrides
    if not overrides_path and args.ufo:
        candidate = args.ufo / "data" / OVERRIDES_FILENAME
        if candidate.exists():
            overrides_path = candidate

    if overrides_path and overrides_path.exists() and not args.export:
        overrides = load_overrides(overrides_path)
        if overrides:
            print(f"Loaded overrides for {len(overrides)} glyphs from {overrides_path}")

    glyph_order = font.getGlyphOrder()
    targets = [n for n in glyph_order if is_telugu_glyph(n)]

    print(f"Found {len(targets)} Telugu glyphs")

    color_layers, stats, glyph_plans = colorize_font(
        font, ufo_font, targets, args.tolerance, args.verbose, overrides
    )

    # Export mode: write TSV and exit
    if args.export:
        if args.export is True:
            export_path = args.ufo / "data" / OVERRIDES_FILENAME if args.ufo else Path(OVERRIDES_FILENAME)
        else:
            export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_classification(glyph_plans, export_path)
        print(f"\nExported classification for {len(glyph_plans)} glyphs -> {export_path}")
        return

    assemble_color_tables(font, color_layers)

    if args.output:
        output_path = args.output
    else:
        p = Path(args.ttf)
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / (p.stem + "-Colorized.ttf")

    font.save(str(output_path))

    print(f"\nColorized {len(color_layers)} glyphs -> {output_path}")
    print("Layer counts:")
    for name, count in stats.items():
        if count > 0:
            print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
