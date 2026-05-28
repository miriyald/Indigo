# Telugu Font Coloring Logic

## Overview

`tools/colorize.py` automatically adds COLR v0 + CPAL color tables to a Telugu TTF font. It classifies each glyph's visual regions into 6 semantic categories and assigns distinct colors, producing a color font that reveals the internal structure of Telugu script.

## Categories & Palette

| Index | Category       | Color              | Hex       | Purpose                              |
|-------|----------------|--------------------|-----------|--------------------------------------|
| 0     | Base           | Dark navy          | `#1A1A2E` | Main body / largest connected stroke |
| 1     | Above          | Vermilion          | `#E64A19` | Vowel signs and marks above base     |
| 2     | Disconnected   | Emerald            | `#2ECC71` | Truly isolated floating marks        |
| 3     | Below          | Blue               | `#3498DB` | Elements below the base              |
| 4     | Post-base      | Purple             | `#9B59B6` | Right+below position (anusvara etc.) |
| 5     | Hole           | Light warm amber   | `#F5D07A` | Counter shapes / cutouts             |

## How Classification Works

### Step 1: Region Detection

Each glyph's contours are grouped into **regions** (an outer contour + its contained holes):

- **TTF source** (post-overlap-removal): Reveals true visual holes. CW winding = outer, CCW = hole.
- **UFO source** (pre-overlap-removal): Preserves original design shapes. CCW winding = outer, CW = hole.

When UFO has more outer contours than TTF (because TTF's overlap removal merged them), UFO regions are used for classification. Holes are always detected from TTF.

### Step 2: Base Identification

The region with the largest bounding box area becomes the **base seed**.

### Step 3: Transitive Touching Merge

Regions physically connected to the base are merged into it. Two regions are "connected" if:

1. Their bounding boxes overlap (with 10-unit tolerance), AND
2. Their y-ranges overlap by >= 50% of the smaller region's height

For **substantial regions** (area > 30% of base): any bbox overlap is sufficient, UNLESS the smaller region sits above the larger one's top edge (which indicates a separate mark, not a connected stroke).

All connected regions are found transitively — if A connects to B, and B connects to C, then all three merge into base.

### Step 4: Non-Base Classification

For regions not merged into base, using the **combined base group bbox**:

1. **Disconnected**: No bbox overlap AND no x-range overlap with combined base
2. **Post-base**: Centroid X > 70% of base width AND centroid Y below base centroid
3. **Above**: Centroid Y above combined base centroid
4. **Below**: Everything else

### Step 5: Hole Layer

All CCW contours from TTF (true visual holes after overlap removal) get the hole category. Their winding is reversed (CCW to CW) so they render as filled shapes in the COLR layer.

## Layer Order (bottom to top)

```
base → hole → below → postbase → disconnected → above
```

## Manual Overrides

Auto-classification can be overridden per-region via CSV:

```
source/TiroTelugu-Regular.ufo/data/colorize_overrides.csv
```

Format:
```csv
glyph,region,category,bbox,info
tNna,0,base,(415,-15,821,525),largest
tNna,1,base,(73,227,439,525),
tNna,2,below,(73,-15,389,263),
```

Only columns 1-3 (glyph, region, category) are used for import. The file is auto-discovered from the UFO data folder.

## Usage

```bash
# Full build (auto-discovers overrides from UFO)
python tools/colorize.py source/TiroTelugu-Regular.input.ttf --ufo source/TiroTelugu-Regular.ufo

# Export classification to CSV for manual editing
python tools/colorize.py source/TiroTelugu-Regular.input.ttf --ufo source/TiroTelugu-Regular.ufo --export

# Generate test page
python tools/fonttest.py output/TiroTelugu-Regular.input-Colorized.ttf
```

## Build Scripts

- `run.cmd` — Quick colorize + test page
- `build-color.cmd` — Verbose colorize + test page

Both output to `output/` directory.
