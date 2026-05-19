"""
Render .glif files from a UFO source as standalone SVG files.

Uses fontTools SVGPathPen to convert glyph outlines to SVG path data.

Usage:
    python tools/glif2svg.py source/TiroTelugu-Regular.ufo --glyph tKa
    python tools/glif2svg.py source/TiroTelugu-Regular.ufo --all --output output/svg/
    python tools/glif2svg.py source/TiroTelugu-Regular.ufo --glyph tKa --specimen
"""

import argparse
import sys
from pathlib import Path

import ufoLib2
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen


MARGIN = 50
SVG_TEMPLATE = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewBox}" width="{width}" height="{height}">
  <g transform="translate(0,{ascender}) scale(1,-1)">
    <path d="{path}" fill="{fill}" />
  </g>
</svg>
"""

CONTOUR_VIZ_COLORS = [
    "#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261",
    "#264653", "#6A0572", "#AB83A1", "#118AB2", "#06D6A0",
]

SPECIMEN_HEADER = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">
<style>
  text {{ font-family: monospace; font-size: 14px; fill: #666; }}
</style>
<rect width="100%" height="100%" fill="#fafafa"/>
"""


def get_glyph_svg_path(font, glyph_name):
    glyphset = font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    pen = SVGPathPen(glyphset)
    glyph.draw(pen)
    return pen.getCommands()


def get_glyph_bounds(font, glyph_name):
    glyphset = font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    pen = BoundsPen(glyphset)
    glyph.draw(pen)
    return pen.bounds


def render_glyph_svg(font, glyph_name, fill="#000000"):
    path_data = get_glyph_svg_path(font, glyph_name)
    if not path_data:
        return None

    bounds = get_glyph_bounds(font, glyph_name)
    if not bounds:
        return None

    xMin, yMin, xMax, yMax = bounds
    ascender = font.info.ascender or 800
    descender = font.info.descender or -200

    total_height = ascender - descender
    glyph_width = font[glyph_name].width or (xMax - xMin + MARGIN * 2)

    vb_x = -MARGIN
    vb_y = 0
    vb_w = glyph_width + MARGIN * 2
    vb_h = total_height + MARGIN * 2

    return SVG_TEMPLATE.format(
        viewBox=f"{vb_x} {-MARGIN} {vb_w} {vb_h}",
        width=vb_w,
        height=vb_h,
        ascender=ascender + MARGIN,
        path=path_data,
        fill=fill,
    )


def get_contour_paths(font, glyph_name):
    glyphset = font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    paths = []
    for contour in glyph.contours:
        pen = SVGPathPen(glyphset)
        contour.draw(pen)
        paths.append(pen.getCommands())
    return paths


def get_contour_bounds(font, glyph_name):
    glyphset = font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    bounds_list = []
    for contour in glyph.contours:
        pen = BoundsPen(glyphset)
        contour.draw(pen)
        bounds_list.append(pen.bounds)
    return bounds_list


def detect_regions_ufo(font, glyph_name):
    """Detect regions from UFO source: group outer contours with their hole children.
    Returns list of (outer_contour_idx, [hole_contour_indices])."""
    glyphset = font.layers.defaultLayer
    glyph = glyphset[glyph_name]
    contours = list(glyph.contours)
    if not contours:
        return []

    # Get bounds and winding for each contour
    info = []
    for i, contour in enumerate(contours):
        pen = BoundsPen(glyphset)
        contour.draw(pen)
        bounds = pen.bounds
        if bounds is None:
            info.append({"idx": i, "bounds": (0, 0, 0, 0), "is_outer": True, "area": 0})
            continue

        # Calculate winding via signed area of control points
        pts = []
        for pt in contour:
            pts.append((pt.x, pt.y))
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


HOLE_VIZ_COLORS = [
    "#FF6B9D", "#FFD93D", "#6BCB77", "#4D96FF", "#C9B1FF",
    "#FF8F5E", "#45CFDD", "#F038FF", "#B8E986", "#FFA8A8",
]


def _ttf_contour_to_svg_path(glyph, contour_idx):
    """Convert a single TTF contour to an SVG path string."""
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    coords = [glyph.coordinates[i] for i in range(start, end + 1)]
    flags = [glyph.flags[i] for i in range(start, end + 1)]

    if not coords:
        return ""

    # Build SVG path from TrueType quadratic contour
    n = len(coords)
    parts = []

    # Find first on-curve point to start
    first_on = -1
    for i in range(n):
        if flags[i] & 1:
            first_on = i
            break

    if first_on == -1:
        # All off-curve: implied on-curve at midpoint of first two
        mx = (coords[0][0] + coords[1][0]) / 2
        my = (coords[0][1] + coords[1][1]) / 2
        parts.append(f"M{mx:.0f} {my:.0f}")
        idx = 0
    else:
        parts.append(f"M{coords[first_on][0]:.0f} {coords[first_on][1]:.0f}")
        idx = (first_on + 1) % n

    visited = 0
    while visited < n:
        i = (first_on + 1 + visited) % n if first_on >= 0 else (visited) % n
        if first_on == -1 and visited == 0:
            i = 0
            visited += 1
            continue

        if flags[i] & 1:
            # On-curve: line to
            parts.append(f"L{coords[i][0]:.0f} {coords[i][1]:.0f}")
            visited += 1
        else:
            # Off-curve: quadratic bezier
            cx, cy = coords[i]
            next_i = (i + 1) % n
            if flags[next_i] & 1:
                # Next is on-curve: simple Q
                parts.append(f"Q{cx:.0f} {cy:.0f} {coords[next_i][0]:.0f} {coords[next_i][1]:.0f}")
                visited += 2
            else:
                # Next is also off-curve: implied on-curve at midpoint
                nx, ny = coords[next_i]
                mx = (cx + nx) / 2
                my = (cy + ny) / 2
                parts.append(f"Q{cx:.0f} {cy:.0f} {mx:.0f} {my:.0f}")
                visited += 1

    parts.append("Z")
    return "".join(parts)


def _ttf_contour_bounds(glyph, contour_idx):
    """Get bounding box of a TTF contour."""
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    xs = [glyph.coordinates[i][0] for i in range(start, end + 1)]
    ys = [glyph.coordinates[i][1] for i in range(start, end + 1)]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _ttf_contour_winding(glyph, contour_idx):
    """Signed area of a TTF contour."""
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    area = 0
    for i in range(start, end + 1):
        x1, y1 = glyph.coordinates[i]
        j = start + (i - start + 1) % (end - start + 1)
        x2, y2 = glyph.coordinates[j]
        area += (x2 - x1) * (y2 + y1)
    return area


def _detect_regions_ttf(glyph):
    """Detect regions from compiled TTF glyph."""
    num = glyph.numberOfContours
    if num is None or num < 1:
        return []

    contours = []
    for ci in range(num):
        bbox = _ttf_contour_bounds(glyph, ci)
        winding = _ttf_contour_winding(glyph, ci)
        area = 0
        if bbox:
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        contours.append({"idx": ci, "bbox": bbox, "is_outer": winding > 0, "area": area})

    outers = [c for c in contours if c["is_outer"]]
    inners = [c for c in contours if not c["is_outer"]]
    outers.sort(key=lambda c: c["area"], reverse=True)

    regions = []
    assigned = set()

    for outer in outers:
        ob = outer["bbox"]
        if ob is None:
            regions.append((outer["idx"], []))
            continue
        holes = []
        for inner in inners:
            if inner["idx"] in assigned:
                continue
            ib = inner["bbox"]
            if ib and ib[0] >= ob[0] and ib[1] >= ob[1] and ib[2] <= ob[2] and ib[3] <= ob[3]:
                holes.append(inner["idx"])
                assigned.add(inner["idx"])
        regions.append((outer["idx"], holes))

    for inner in inners:
        if inner["idx"] not in assigned:
            regions.append((inner["idx"], []))

    return regions


def render_glyph_contours_svg_from_ttf(ttf_font, glyph_name, ascender=800, descender=-200):
    """Render contour/region visualization directly from compiled TTF."""
    glyf = ttf_font["glyf"]
    if glyph_name not in glyf:
        return None
    glyph = glyf[glyph_name]
    if glyph.numberOfContours is None or glyph.numberOfContours < 1:
        return None

    regions = _detect_regions_ttf(glyph)
    if not regions:
        return None

    hmtx = ttf_font["hmtx"]
    glyph_width = hmtx[glyph_name][0] if glyph_name in hmtx else 600

    total_height = ascender - descender
    vb_x = -MARGIN
    vb_w = glyph_width + MARGIN * 2
    vb_h = total_height + MARGIN * 2 + 80

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x} {-MARGIN} {vb_w} {vb_h}" width="{vb_w}" height="{vb_h}">',
        f'  <g transform="translate(0,{ascender + MARGIN}) scale(1,-1)">',
    ]

    # Draw regions (outer + holes as cutouts)
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
        combined = _ttf_contour_to_svg_path(glyph, outer_idx)
        for hi in hole_indices:
            combined += " " + _ttf_contour_to_svg_path(glyph, hi)
        if combined:
            parts.append(f'    <path d="{combined}" fill="{color}" fill-rule="nonzero" opacity="0.6"/>')

    # Draw holes filled with distinct colors
    hole_global_idx = 0
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        for hi, contour_idx in enumerate(hole_indices):
            hole_color = HOLE_VIZ_COLORS[hole_global_idx % len(HOLE_VIZ_COLORS)]
            path = _ttf_contour_to_svg_path(glyph, contour_idx)
            if path:
                parts.append(f'    <path d="{path}" fill="{hole_color}" fill-rule="nonzero" opacity="0.85"/>')
            hole_global_idx += 1

    parts.append('  </g>')

    # Region labels
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        b = _ttf_contour_bounds(glyph, outer_idx)
        if not b:
            continue
        cx = (b[0] + b[2]) / 2
        cy = ascender + MARGIN - (b[1] + b[3]) / 2
        color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
        parts.append(f'  <text x="{cx:.0f}" y="{cy:.0f}" font-family="monospace" font-size="30" '
                     f'fill="{color}" text-anchor="middle" font-weight="bold">r{ri}</text>')

    # Hole labels
    hole_global_idx = 0
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        for hi, contour_idx in enumerate(hole_indices):
            b = _ttf_contour_bounds(glyph, contour_idx)
            if not b:
                continue
            cx = (b[0] + b[2]) / 2
            cy = ascender + MARGIN - (b[1] + b[3]) / 2
            hole_color = HOLE_VIZ_COLORS[hole_global_idx % len(HOLE_VIZ_COLORS)]
            parts.append(f'  <text x="{cx:.0f}" y="{cy:.0f}" font-family="monospace" font-size="20" '
                         f'fill="{hole_color}" text-anchor="middle" font-weight="bold">{ri}.h{hi}</text>')
            hole_global_idx += 1

    # Legend
    legend_y = total_height + MARGIN + 20
    parts.append(f'  <text x="0" y="{legend_y}" font-family="monospace" font-size="14" fill="#333">'
                 f'{glyph_name}: {len(regions)} regions</text>')

    lx = 0
    hole_global_idx = 0
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
        parts.append(f'  <rect x="{lx}" y="{legend_y + 8}" width="12" height="12" fill="{color}"/>')
        parts.append(f'  <text x="{lx + 16}" y="{legend_y + 19}" font-family="monospace" font-size="12" fill="#333">r{ri}</text>')
        lx += 60
        for hi in range(len(hole_indices)):
            hole_color = HOLE_VIZ_COLORS[hole_global_idx % len(HOLE_VIZ_COLORS)]
            parts.append(f'  <rect x="{lx}" y="{legend_y + 8}" width="12" height="12" fill="{hole_color}"/>')
            parts.append(f'  <text x="{lx + 16}" y="{legend_y + 19}" font-family="monospace" font-size="12" fill="#333">{ri}.h{hi}</text>')
            lx += 70
            hole_global_idx += 1

    parts.append('</svg>')
    return '\n'.join(parts)


def render_glyph_contours_svg(font, glyph_name):
    """Render glyph with each region (outer+holes) in a distinct color.
    Holes are shown with their own color and labeled with r0.h0 notation."""
    all_paths = get_contour_paths(font, glyph_name)
    if not all_paths:
        return None

    regions = detect_regions_ufo(font, glyph_name)
    if not regions:
        return None

    all_bounds = get_contour_bounds(font, glyph_name)
    overall_bounds = get_glyph_bounds(font, glyph_name)
    if not overall_bounds:
        return None

    ascender = font.info.ascender or 800
    descender = font.info.descender or -200
    total_height = ascender - descender
    glyph_width = font[glyph_name].width or (overall_bounds[2] - overall_bounds[0] + MARGIN * 2)

    vb_x = -MARGIN
    vb_w = glyph_width + MARGIN * 2
    vb_h = total_height + MARGIN * 2 + 80

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x} {-MARGIN} {vb_w} {vb_h}" width="{vb_w}" height="{vb_h}">',
        f'  <g transform="translate(0,{ascender + MARGIN}) scale(1,-1)">',
    ]

    # Draw each region outer (with holes as cutouts)
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
        combined_path = all_paths[outer_idx] if outer_idx < len(all_paths) else ""
        for hi in hole_indices:
            if hi < len(all_paths):
                combined_path += " " + all_paths[hi]
        if combined_path:
            parts.append(f'    <path d="{combined_path}" fill="{color}" fill-rule="nonzero" opacity="0.6"/>')

    # Draw holes filled with their own distinct colors
    hole_global_idx = 0
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        for hi, contour_idx in enumerate(hole_indices):
            if contour_idx < len(all_paths):
                hole_color = HOLE_VIZ_COLORS[hole_global_idx % len(HOLE_VIZ_COLORS)]
                parts.append(f'    <path d="{all_paths[contour_idx]}" fill="{hole_color}" fill-rule="nonzero" opacity="0.85"/>')
                hole_global_idx += 1

    parts.append('  </g>')

    # Add region labels at outer contour centroids
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        if outer_idx >= len(all_bounds) or all_bounds[outer_idx] is None:
            continue
        xMin, yMin, xMax, yMax = all_bounds[outer_idx]
        cx = (xMin + xMax) / 2
        cy = ascender + MARGIN - (yMin + yMax) / 2
        color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
        parts.append(f'  <text x="{cx:.0f}" y="{cy:.0f}" font-family="monospace" font-size="30" '
                     f'fill="{color}" text-anchor="middle" font-weight="bold">r{ri}</text>')

    # Add hole labels at hole contour centroids
    hole_global_idx = 0
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        for hi, contour_idx in enumerate(hole_indices):
            if contour_idx >= len(all_bounds) or all_bounds[contour_idx] is None:
                continue
            xMin, yMin, xMax, yMax = all_bounds[contour_idx]
            cx = (xMin + xMax) / 2
            cy = ascender + MARGIN - (yMin + yMax) / 2
            hole_color = HOLE_VIZ_COLORS[hole_global_idx % len(HOLE_VIZ_COLORS)]
            parts.append(f'  <text x="{cx:.0f}" y="{cy:.0f}" font-family="monospace" font-size="20" '
                         f'fill="{hole_color}" text-anchor="middle" font-weight="bold">{ri}.h{hi}</text>')
            hole_global_idx += 1

    # Legend
    legend_y = total_height + MARGIN + 20
    parts.append(f'  <text x="0" y="{legend_y}" font-family="monospace" font-size="14" fill="#333">'
                 f'{glyph_name}: {len(regions)} regions</text>')

    lx = 0
    hole_global_idx = 0
    for ri, (outer_idx, hole_indices) in enumerate(regions):
        color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
        parts.append(f'  <rect x="{lx}" y="{legend_y + 8}" width="12" height="12" fill="{color}"/>')
        parts.append(f'  <text x="{lx + 16}" y="{legend_y + 19}" font-family="monospace" font-size="12" fill="#333">r{ri}</text>')
        lx += 60

        for hi in range(len(hole_indices)):
            hole_color = HOLE_VIZ_COLORS[hole_global_idx % len(HOLE_VIZ_COLORS)]
            parts.append(f'  <rect x="{lx}" y="{legend_y + 8}" width="12" height="12" fill="{hole_color}"/>')
            parts.append(f'  <text x="{lx + 16}" y="{legend_y + 19}" font-family="monospace" font-size="12" fill="#333">{ri}.h{hi}</text>')
            lx += 70
            hole_global_idx += 1

    parts.append('</svg>')
    return '\n'.join(parts)


def render_contour_specimen(font, glyph_names, cols=8, cell_size=160):
    rows = (len(glyph_names) + cols - 1) // cols
    width = cols * cell_size
    height = rows * cell_size

    ascender = font.info.ascender or 800
    descender = font.info.descender or -200
    upm = font.info.unitsPerEm or 1000
    scale = (cell_size - 40) / upm

    parts = [SPECIMEN_HEADER.format(width=width, height=height)]

    for idx, name in enumerate(glyph_names):
        col = idx % cols
        row = idx // cols
        x = col * cell_size
        y = row * cell_size

        all_paths = get_contour_paths(font, name)
        if not all_paths:
            continue

        regions = detect_regions_ufo(font, name)
        if not regions:
            continue

        tx = x + 10
        ty = y + cell_size - 35

        parts.append(f'  <g transform="translate({tx},{ty}) scale({scale:.4f},{-scale:.4f})">')
        for ri, (outer_idx, hole_indices) in enumerate(regions):
            color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
            combined_path = all_paths[outer_idx] if outer_idx < len(all_paths) else ""
            for hi in hole_indices:
                if hi < len(all_paths):
                    combined_path += " " + all_paths[hi]
            if combined_path:
                parts.append(f'    <path d="{combined_path}" fill="{color}" fill-rule="nonzero" opacity="0.75"/>')
        parts.append('  </g>')
        parts.append(f'  <text x="{x + 5}" y="{y + cell_size - 5}">{name} ({len(regions)}r)</text>')
        parts.append(f'  <rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="none" stroke="#eee"/>')

    parts.append('</svg>')
    return '\n'.join(parts)


def render_specimen(font, glyph_names, cols=10, cell_size=120):
    rows = (len(glyph_names) + cols - 1) // cols
    width = cols * cell_size
    height = rows * cell_size

    ascender = font.info.ascender or 800
    descender = font.info.descender or -200
    upm = font.info.unitsPerEm or 1000
    scale = (cell_size - 30) / upm

    parts = [SPECIMEN_HEADER.format(width=width, height=height)]

    for i, name in enumerate(glyph_names):
        col = i % cols
        row = i // cols
        x = col * cell_size
        y = row * cell_size

        path_data = get_glyph_svg_path(font, name)
        if not path_data:
            continue

        tx = x + 10
        ty = y + cell_size - 25

        parts.append(f'  <g transform="translate({tx},{ty}) scale({scale:.4f},{-scale:.4f})">')
        parts.append(f'    <path d="{path_data}" fill="#000"/>')
        parts.append('  </g>')
        parts.append(f'  <text x="{x + 5}" y="{y + cell_size - 5}">{name}</text>')
        parts.append(f'  <rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="none" stroke="#eee"/>')

    parts.append('</svg>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description="Render UFO glyphs as SVG")
    parser.add_argument("ufo", help="Path to UFO source")
    parser.add_argument("--glyph", "-g", help="Specific glyph name to render")
    parser.add_argument("--all", action="store_true", help="Render all glyphs")
    parser.add_argument("--telugu", action="store_true", help="Render all Telugu glyphs (t + uppercase)")
    parser.add_argument("--output", "-o", default="output/svg", help="Output directory")
    parser.add_argument("--specimen", action="store_true", help="Generate a specimen sheet instead of individual files")
    parser.add_argument("--contours", action="store_true", help="Render regions/holes with distinct colors and labels")
    parser.add_argument("--ttf", help="Compiled TTF for region detection (default: auto-detect from output/)")
    parser.add_argument("--fill", default="#000000", help="Fill color (default: black)")
    args = parser.parse_args()

    ufo_path = Path(args.ufo)
    if not ufo_path.exists():
        print(f"Error: UFO not found at {ufo_path}")
        sys.exit(1)

    print(f"Loading {ufo_path}")
    font = ufoLib2.Font.open(str(ufo_path))

    if args.glyph:
        glyph_names = [args.glyph]
    elif args.telugu:
        glyph_names = [n for n in font.keys() if len(n) >= 2 and n[0] == 't' and n[1].isupper()]
    elif args.all:
        glyph_names = list(font.keys())
    else:
        glyph_names = [n for n in font.keys() if len(n) >= 2 and n[0] == 't' and n[1].isupper()]

    print(f"Rendering {len(glyph_names)} glyphs")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.contours:
        # Use compiled TTF for accurate region/hole detection
        if args.ttf:
            ttf_path = Path(args.ttf)
        else:
            ttf_path = Path(__file__).parent.parent / "output/indigo/TiroTelugu/TTF/TiroTelugu-Regular.ttf"
        if not ttf_path.exists():
            print(f"Error: TTF not found at {ttf_path} (needed for region detection)")
            print("  Use --ttf to specify path to compiled font")
            sys.exit(1)
        print(f"Using TTF for regions: {ttf_path}")
        ttf_font = TTFont(str(ttf_path))
        ascender = font.info.ascender or 800
        descender = font.info.descender or -200

    if args.specimen and args.contours:
        # TTF-based specimen
        glyf = ttf_font["glyf"]
        valid_names = [n for n in glyph_names if n in glyf and glyf[n].numberOfContours and glyf[n].numberOfContours >= 1]
        rows = (len(valid_names) + 7) // 8
        cell_size = 160
        width = 8 * cell_size
        height = rows * cell_size
        upm = font.info.unitsPerEm or 1000
        scale = (cell_size - 40) / upm

        parts_list = [SPECIMEN_HEADER.format(width=width, height=height)]
        for idx, name in enumerate(valid_names):
            col = idx % 8
            row = idx // 8
            x = col * cell_size
            y = row * cell_size

            glyph = glyf[name]
            regions = _detect_regions_ttf(glyph)
            if not regions:
                continue

            tx = x + 10
            ty = y + cell_size - 35

            parts_list.append(f'  <g transform="translate({tx},{ty}) scale({scale:.4f},{-scale:.4f})">')
            hole_gi = 0
            for ri, (outer_idx, hole_indices) in enumerate(regions):
                color = CONTOUR_VIZ_COLORS[ri % len(CONTOUR_VIZ_COLORS)]
                combined = _ttf_contour_to_svg_path(glyph, outer_idx)
                for hi in hole_indices:
                    combined += " " + _ttf_contour_to_svg_path(glyph, hi)
                if combined:
                    parts_list.append(f'    <path d="{combined}" fill="{color}" fill-rule="nonzero" opacity="0.6"/>')
                for hi, ci in enumerate(hole_indices):
                    hc = HOLE_VIZ_COLORS[hole_gi % len(HOLE_VIZ_COLORS)]
                    path = _ttf_contour_to_svg_path(glyph, ci)
                    if path:
                        parts_list.append(f'    <path d="{path}" fill="{hc}" fill-rule="nonzero" opacity="0.85"/>')
                    hole_gi += 1
            parts_list.append('  </g>')

            n_holes = sum(len(h) for _, h in regions)
            label = f"{name} ({len(regions)}r" + (f"+{n_holes}h)" if n_holes else ")")
            parts_list.append(f'  <text x="{x + 5}" y="{y + cell_size - 5}">{label}</text>')
            parts_list.append(f'  <rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="none" stroke="#eee"/>')

        parts_list.append('</svg>')
        svg = '\n'.join(parts_list)
        out_file = output_dir / f"{ufo_path.stem}-contours-specimen.svg"
        out_file.write_text(svg, encoding="utf-8")
        print(f"Contour specimen saved: {out_file}")
    elif args.specimen:
        svg = render_specimen(font, glyph_names)
        out_file = output_dir / f"{ufo_path.stem}-specimen.svg"
        out_file.write_text(svg, encoding="utf-8")
        print(f"Specimen saved: {out_file}")
    elif args.contours:
        count = 0
        for name in glyph_names:
            svg = render_glyph_contours_svg_from_ttf(ttf_font, name, ascender, descender)
            if svg:
                out_file = output_dir / f"{name}-contours.svg"
                out_file.write_text(svg, encoding="utf-8")
                count += 1
        print(f"Saved {count} contour SVG files to {output_dir}")
    else:
        count = 0
        for name in glyph_names:
            svg = render_glyph_svg(font, name, fill=args.fill)
            if svg:
                out_file = output_dir / f"{name}.svg"
                out_file.write_text(svg, encoding="utf-8")
                count += 1
        print(f"Saved {count} SVG files to {output_dir}")


if __name__ == "__main__":
    main()
