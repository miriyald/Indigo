# Manual Region-to-Color Mapping Workflow

## Overview

A workflow for manually assigning colors to glyph **regions** in TiroTelugu, producing a COLR v0 color font with precise artistic control.

A **region** is a visual unit: an outer contour plus any inner hole contours that cut into it. When a region is filled with a color, the holes are preserved (they aren't filled solid). This matches how font rendering actually works — the nonzero fill rule uses contour winding direction to determine inside vs. outside.

## Palette (ATS-Chikkamagaluru 9-color)

| Index | Color | Hex |
|-------|-------|-----|
| 0 | Dark outline | #1D1D1D |
| 1 | Red | #EE3441 |
| 2 | Light yellow | #F1F09A |
| 3 | Pink | #F7ACBA |
| 4 | Lavender | #BB9CD4 |
| 5 | Magenta | #EBA7D1 |
| 6 | Peach | #FBB88F |
| 7 | Green | #93D49B |
| 8 | Cyan | #76CFE9 |

## Workflow Steps

### Step 1: Visualize regions

```bash
python tools/glif2svg.py source/TiroTelugu-Regular.ufo --telugu --regions --output output/svg-contours/
python tools/glif2svg.py source/TiroTelugu-Regular.ufo --glyph tKa --regions --output output/svg-contours/
```

Each region is rendered in a distinct color with its index number labeled. Holes are correctly grouped with their parent outer contour. Use these SVGs to identify which region index corresponds to which visual element.

### Step 2: Generate mapping scaffold

```bash
python tools/generate_mapping.py --output data/color_mapping.json --auto-heuristic
```

This creates a JSON file pre-populated with all multi-region Telugu glyphs (380 glyphs with 2+ visual regions), their region areas, hole counts, and default color assignments.

### Step 3: Edit the mapping

Open `data/color_mapping.json` and assign palette indices to regions. Two formats supported:

**Per-region format (recommended):**
```json
"tKha": {
  "regions": { "0": 7, "1": 3 }
}
```

**Grouped format (when multiple regions share a color):**
```json
"tKha": {
  "groups": [
    {"regions": [0], "color": 7},
    {"regions": [1], "color": 3}
  ]
}
```

Region indices correspond to the colored labels shown in the SVG visualizations.

### Step 4: Apply to font

```bash
python tools/add_color.py --style manual --mapping data/color_mapping.json
```

Output: `output/indigo/TiroTelugu/TTF/TiroTelugu-Regular-ColorManual.ttf`

### Step 5: Verify

```bash
python tools/fonttest.py output/indigo/TiroTelugu/TTF/TiroTelugu-Regular-ColorManual.ttf
```

Open the generated HTML in Chrome/Firefox to see colors rendered.

### Step 6: Iterate

Edit the JSON, re-run steps 4-5. The input font is never modified.

## Mapping File Reference

### Defaults section

```json
"defaults": {
  "unmapped_regions": 0,
  "unmapped_glyphs": "auto:region"
}
```

- `unmapped_regions`: palette index for regions not explicitly listed (default: 0 = dark)
- `unmapped_glyphs`: strategy for glyphs not in the mapping file:
  - `"auto:region"` — size-based heuristic (largest region = 0/dark, rest = 1/red)
  - `"auto:ats"` — rotating single color per glyph
  - `"skip"` — no color layers for unmapped glyphs

### Glyph entries

- `_info` field is informational (ignored by apply tool), shows region count, areas, and hole counts
- Region indices correspond to detected visual units (outer contour + its holes)
- Palette index values: 0-8 (see palette table above)

### How regions work

A glyph like **tKha** has 4 raw contours but only **2 regions**:
- Region 0: the main body shape (outer CW contour + 2 CCW hole contours)
- Region 1: the small detached dot below

When you assign color 7 (green) to region 0, the fill covers the main body shape but correctly leaves the inner holes empty. This is the key difference from the old contour-based approach where holes would fill solid.
