"""
Generate glyph name to Unicode codepoint mapping from font sources.

Reads cmap data from a compiled TTF and/or Unicode assignments from a UFO source,
and produces a JSON file mapping glyph names to their Unicode codepoints.

Usage:
    python tools/generate_unicode_map.py --ttf source/TiroTelugu-Regular.input.ttf --ufo source/TiroTelugu-Regular.ufo
    python tools/generate_unicode_map.py --ufo source/TiroTelugu-Regular.ufo -o output/unicode_map.json
    python tools/generate_unicode_map.py --ttf source/TiroTelugu-Regular.input.ttf --telugu-only
"""

import argparse
import json
import sys
from pathlib import Path

import ufoLib2
from fontTools.ttLib import TTFont


def is_telugu_glyph(name):
    if len(name) < 2:
        return False
    return name[0] == "t" and name[1].isupper()


def read_ttf_mapping(ttf_path):
    font = TTFont(str(ttf_path))
    cmap = font.getBestCmap()
    glyph_to_unicode = {}
    for codepoint, glyph_name in cmap.items():
        glyph_to_unicode.setdefault(glyph_name, []).append(codepoint)
    glyph_order = font.getGlyphOrder()
    font.close()
    return glyph_to_unicode, glyph_order


def read_ufo_mapping(ufo_path):
    ufo_font = ufoLib2.Font.open(str(ufo_path))
    glyphset = ufo_font.layers.defaultLayer
    glyph_to_unicode = {}
    all_names = []
    for glyph_name in glyphset.keys():
        all_names.append(glyph_name)
        glyph = glyphset[glyph_name]
        if glyph.unicodes:
            glyph_to_unicode[glyph_name] = list(glyph.unicodes)
    return glyph_to_unicode, all_names


def format_unicode(codepoints):
    if len(codepoints) == 1:
        return f"U+{codepoints[0]:04X}"
    return [f"U+{cp:04X}" for cp in codepoints]


def main():
    parser = argparse.ArgumentParser(
        description="Generate glyph name to Unicode codepoint mapping."
    )
    parser.add_argument("--ttf", type=Path, help="Path to compiled TTF font file")
    parser.add_argument("--ufo", type=Path, help="Path to UFO source directory")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output JSON file (defaults to stdout)"
    )
    parser.add_argument(
        "--telugu-only", action="store_true", help="Only include Telugu glyphs"
    )
    args = parser.parse_args()

    if not args.ttf and not args.ufo:
        parser.error("At least one of --ttf or --ufo must be provided")

    ttf_mapping, ttf_glyphs = {}, []
    ufo_mapping, ufo_glyphs = {}, []

    if args.ttf:
        ttf_mapping, ttf_glyphs = read_ttf_mapping(args.ttf)
    if args.ufo:
        ufo_mapping, ufo_glyphs = read_ufo_mapping(args.ufo)

    combined = {**ttf_mapping}
    combined.update(ufo_mapping)

    all_glyphs = list(dict.fromkeys(ufo_glyphs + ttf_glyphs))

    if args.telugu_only:
        combined = {k: v for k, v in combined.items() if is_telugu_glyph(k)}
        all_glyphs = [g for g in all_glyphs if is_telugu_glyph(g)]

    mapped = {}
    for name in sorted(combined.keys()):
        mapped[name] = format_unicode(combined[name])

    unmapped = [g for g in all_glyphs if g not in combined]

    source_name = "TiroTelugu-Regular"
    if args.ufo:
        source_name = args.ufo.stem.replace(".ufo", "")
    elif args.ttf:
        source_name = args.ttf.stem.replace(".input", "")

    result = {"source": source_name, "mapped": mapped, "unmapped": sorted(unmapped)}

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_json, encoding="utf-8")
        print(f"Written {len(mapped)} mapped + {len(unmapped)} unmapped glyphs to {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
