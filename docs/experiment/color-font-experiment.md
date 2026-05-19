# Color Font Experiment — TiroTelugu COLR v0

## Overview

Added color to the TiroTelugu font using the simplest color font technology: **COLR v0 + CPAL** (OpenType Color Layers). For every Telugu glyph with multiple contours, the largest contour is rendered in black (base) and smaller contours (matras, marks, decorative strokes) in red.

## Technology

| Component | Purpose |
|-----------|---------|
| **COLR v0** | Maps each colored glyph to a stack of layers, each layer referencing a glyph and a palette color index |
| **CPAL v0** | Defines color palettes (we use one palette with 2 colors) |

This is the same approach used by the ATS-Chikkamagaluru reference font in `third-party/ATS-Chikkamagaluru/`.

## How It Works

### Concept

A standard glyph like **క** (ka) may have 3 contours:
- Contour 0: the main body (largest area)
- Contour 1: a vowel mark or decorative element
- Contour 2: another secondary element

COLR v0 works by splitting these contours into separate hidden "layer" glyphs and assigning each a color from the palette:

```
Original glyph: tKa (3 contours)
    → tKa.base   (contour 0, largest)  → palette index 0 (black #000000)
    → tKa.accent (contours 1+2)        → palette index 1 (red #CC3333)
```

Renderers that support COLR draw the layers in order; those that don't fall back to the original monochrome glyph.

### Pipeline

```
TiroTelugu-Regular.ttf (compiled from UFO)
        │
        ▼
  tools/add_color.py
        │
        ▼
TiroTelugu-Regular-Color.ttf (with COLR + CPAL tables)
```

The color step is a post-processing script — it does not modify the standard build.

## Usage

### Prerequisites

The base font must already be built:

```bash
python tools/tirobuild.py indigo-telugu.yml
```

### Generate the color font

```bash
python tools/add_color.py
```

Or with explicit paths:

```bash
python tools/add_color.py input.ttf output.ttf
```

Defaults:
- Input: `output/indigo/TiroTelugu/TTF/TiroTelugu-Regular.ttf`
- Output: `output/indigo/TiroTelugu/TTF/TiroTelugu-Regular-Color.ttf`

### Test

Open `output/indigo/TiroTelugu/TTF/TiroTelugu-Regular-Color-test.html` in Chrome, Firefox, or Edge.

## Script Details — tools/add_color.py

### Algorithm

1. **Load** the compiled TTF
2. **Find targets** — all glyphs whose name starts with `t` + uppercase letter (Telugu naming convention) and have 2+ contours
3. **For each target glyph:**
   - Compute bounding-box area of each contour
   - Largest contour → `{name}.base` layer glyph
   - All remaining contours → `{name}.accent` layer glyph
   - Both layers get the same advance width as the original
4. **Build CPAL** — single palette with 2 colors
5. **Build COLR** — register layers for each colored glyph
6. **Save** the new font file

### Changing Colors

Edit the constants at the top of `tools/add_color.py`:

```python
BASE_COLOR = (0, 0, 0, 1.0)           # (R, G, B, A) floats 0-1
ACCENT_COLOR = (0.8, 0.2, 0.2, 1.0)   # red
```

### Stats

- 706 Telugu glyphs colorized
- 1,412 new layer glyphs added (2 per target)
- Output file size: ~907 KB (vs ~470 KB for the regular TTF)

## Compatibility

| Environment | Support |
|-------------|---------|
| Chrome / Edge | Yes |
| Firefox | Yes |
| Safari / macOS | Yes |
| Windows text rendering | Yes (DirectWrite) |
| Adobe apps | Partial (prefer SVG table) |
| Older apps / GDI | Falls back to monochrome |

## Reference

- ATS-Chikkamagaluru COLR font: `third-party/ATS-Chikkamagaluru/ATS-Chikkamagaluru/TTF/ATSChikkamagaluru-ColorRegularCOLR.ttf`
- OpenType COLR spec: https://learn.microsoft.com/en-us/typography/opentype/spec/colr
- OpenType CPAL spec: https://learn.microsoft.com/en-us/typography/opentype/spec/cpal

## Possible Next Steps

- **Multiple palettes** — add a dark-mode palette where base = white, accent = gold
- **COLR v1** — gradients, transforms, and compositing for richer effects
- **SVG table** — for maximum visual flexibility (but larger file size)
- **Selective coloring** — color only specific glyph classes (e.g., only vowel signs, or only conjunct forms)
- **Integration into build** — add a `color:` option in `indigo-telugu.yml` to generate color variants automatically
