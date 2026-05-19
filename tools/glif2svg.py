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
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen


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


def render_glyph_contours_svg(font, glyph_name):
    paths = get_contour_paths(font, glyph_name)
    if not paths:
        return None

    bounds_list = get_contour_bounds(font, glyph_name)
    overall_bounds = get_glyph_bounds(font, glyph_name)
    if not overall_bounds:
        return None

    ascender = font.info.ascender or 800
    descender = font.info.descender or -200
    total_height = ascender - descender
    glyph_width = font[glyph_name].width or (overall_bounds[2] - overall_bounds[0] + MARGIN * 2)

    vb_x = -MARGIN
    vb_w = glyph_width + MARGIN * 2
    vb_h = total_height + MARGIN * 2 + 60  # extra space for legend

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x} {-MARGIN} {vb_w} {vb_h}" width="{vb_w}" height="{vb_h}">',
        f'  <g transform="translate(0,{ascender + MARGIN}) scale(1,-1)">',
    ]

    for i, path_data in enumerate(paths):
        if not path_data:
            continue
        color = CONTOUR_VIZ_COLORS[i % len(CONTOUR_VIZ_COLORS)]
        parts.append(f'    <path d="{path_data}" fill="{color}" opacity="0.7"/>')

    parts.append('  </g>')

    # Add index labels at contour centroids (in SVG-down coordinate space)
    for i, b in enumerate(bounds_list):
        if b is None:
            continue
        xMin, yMin, xMax, yMax = b
        cx = (xMin + xMax) / 2
        cy = ascender + MARGIN - (yMin + yMax) / 2  # flip Y
        color = CONTOUR_VIZ_COLORS[i % len(CONTOUR_VIZ_COLORS)]
        parts.append(f'  <text x="{cx:.0f}" y="{cy:.0f}" font-family="monospace" font-size="36" '
                     f'fill="{color}" text-anchor="middle" font-weight="bold">{i}</text>')

    # Legend at bottom
    legend_y = total_height + MARGIN + 20
    parts.append(f'  <text x="0" y="{legend_y}" font-family="monospace" font-size="14" fill="#333">'
                 f'{glyph_name}: {len(paths)} contours</text>')
    for i in range(len(paths)):
        color = CONTOUR_VIZ_COLORS[i % len(CONTOUR_VIZ_COLORS)]
        lx = i * 80
        parts.append(f'  <rect x="{lx}" y="{legend_y + 8}" width="12" height="12" fill="{color}"/>')
        parts.append(f'  <text x="{lx + 16}" y="{legend_y + 19}" font-family="monospace" font-size="12" fill="#333">#{i}</text>')

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

        contour_paths = get_contour_paths(font, name)
        if not contour_paths:
            continue

        tx = x + 10
        ty = y + cell_size - 35

        parts.append(f'  <g transform="translate({tx},{ty}) scale({scale:.4f},{-scale:.4f})">')
        for i, path_data in enumerate(contour_paths):
            if not path_data:
                continue
            color = CONTOUR_VIZ_COLORS[i % len(CONTOUR_VIZ_COLORS)]
            parts.append(f'    <path d="{path_data}" fill="{color}" opacity="0.7"/>')
        parts.append('  </g>')
        parts.append(f'  <text x="{x + 5}" y="{y + cell_size - 5}">{name} ({len(contour_paths)})</text>')
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
    parser.add_argument("--contours", action="store_true", help="Render each contour in a distinct color with index labels")
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

    if args.specimen and args.contours:
        svg = render_contour_specimen(font, glyph_names)
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
            svg = render_glyph_contours_svg(font, name)
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
