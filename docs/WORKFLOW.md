# Indigo Color Font Workflow

A step-by-step guide for designers working with the Tiro font family color pipeline.
All output artifacts land next to the compiled TTF for a clean, self-contained workspace.

---

## Overview

```
Source (UFO) --> Build (TTF) --> View Glyphs --> Generate Mapping --> Edit Colors --> Apply Color --> Test Font
    |                              (from UFO)      (from UFO)                       (UFO layers     |
    +-----------------------------------------------------------------------------------------------+
                                                                     Port to another language <------+
```

---

## Tools at a Glance

| # | Tool | Purpose | Input | Output |
|---|------|---------|-------|--------|
| 1 | `tirobuild.py` | Compile UFO sources into production TTF/OTF | `.yml` project file | `output/<family>/<font>/TTF/*.ttf` |
| 2 | `glif2svg.py` | Visualize glyphs as SVG (individual, specimen, or region maps) | UFO source + compiled TTF | `svg/` or `svg-contours/` next to TTF |
| 3 | `generate_mapping.py` | Generate a color mapping scaffold JSON with smart heuristic defaults | UFO source or compiled TTF | `color_mapping.json` in UFO data/ |
| 4 | `generate_viewer.py` | Interactive HTML viewer for reviewing/editing color assignments | Compiled TTF | `*-viewer.html` next to TTF |
| 5 | `add_color.py` | Apply COLR v0 + CPAL color tables to produce a color font | TTF + mapping JSON | `*-Color*.ttf` next to input |
| 6 | `fonttest.py` | Generate an HTML test page showing the font at multiple sizes | Any font file | `*-test.html` next to font |
| 7 | `remap_font.py` | Port a color font from one Indic script to another (e.g., Kannada to Telugu) | Color TTF | Remapped TTF in `output/` |

---

## Step-by-Step Workflow

### Step 1: Build the Font from Source

Compile the UFO source into a production-ready TTF:

```bash
python tools/tirobuild.py indigo-telugu.yml
```

This reads the project configuration (source UFO, OTL tables from input TTF, glyph renaming) and produces compiled fonts under `output/indigo-telugu/TiroTelugu/TTF/`.

**What it does:**
- Opens the UFO source (glyph outlines, metrics, features)
- Copies GDEF/GSUB/GPOS tables from the pre-compiled `.input.ttf`
- Applies autohinting, overlap removal, CFF optimization
- Outputs static TTF instances

---

### Step 2: View the Glyphs

Inspect glyph outlines and understand the region/hole structure before assigning colors.

**Simple SVG rendering (black outlines):**
```bash
python tools/glif2svg.py source/TiroTelugu-Regular.ufo --telugu --specimen
```

**Region visualization (colored regions + labeled holes):**
```bash
python tools/glif2svg.py source/TiroTelugu-Regular.ufo --telugu --regions --specimen
```

**Single glyph detail view:**
```bash
python tools/glif2svg.py source/TiroTelugu-Regular.ufo --glyph tKa --regions
```

**Output:** SVG files in `output/indigo-telugu/TiroTelugu/TTF/svg-contours/`

The region view shows:
- Each **region** (outer contour + its holes) in a distinct color
- **Holes** highlighted with their own color and labeled `r0.h0`, `r0.h1`, etc.
- A legend showing region/hole counts

This is your map for understanding which parts of each glyph can be independently colored.

---

### Step 3: Generate the Color Mapping

Create a JSON scaffold that assigns default colors using a position/shape heuristic.
Use the UFO source as input to see original contours (before overlap removal merges them):

```bash
python tools/generate_mapping.py source/TiroTelugu-Regular.ufo
```

**Output:** `source/TiroTelugu-Regular.ufo/data/color_mapping.json`

You can also generate from the compiled TTF (fewer contours due to overlap removal):
```bash
python tools/generate_mapping.py output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf
```

The smart heuristic assigns:
| Region/Hole type | Palette index | Color |
|-----------------|---------------|-------|
| Base region (largest) | 0 | Dark |
| Region above base | 5 | Magenta |
| Region below base | 3 | Pink |
| Circular holes (aspect < 1.5) | 2 | Yellow |
| Elliptical holes (aspect >= 1.5) | 4 | Purple |

**Re-running is safe:** `generate_mapping.py` preserves existing manual edits (both `regions` and `ufo_contours` values) when re-run — it only fills in defaults for new glyphs.

The JSON structure:
```json
{
  "_meta": { "palette": "ats", ... },
  "defaults": { "unmapped_glyphs": "auto:region" },
  "glyphs": {
    "tKa": {
      "_info": "3 regions: r0(area=222480), r1(area=25857), r2(area=71224)",
      "regions": { "0": 0, "1": 5, "2": 5 }
    },
    "tJha": {
      "_info": "2 regions: r0(area=957971+1 holes), r1(area=15480)",
      "regions": { "0": 0, "0.h0": 2, "1": 3 },
      "ufo_contours": { "0": 0, "1": 5, "2": 5, "3": 3, "4": 3, "5": 5, "6": 3 },
      "_ufo_info": "7 contours: uc0(287820),uc1(166530),..."
    }
  }
}
```

Glyphs where overlap removal merged UFO contours get both `regions` (TTF topology) and `ufo_contours` (per-contour from UFO source). When `--ufo` is passed to `add_color.py`, the `ufo_contours` mapping takes priority, giving finer color control.

---

### Step 4: Review and Edit Colors (Interactive Viewer)

Launch the interactive HTML viewer for visual review and editing:

```bash
python tools/generate_viewer.py
```

**Output:** `output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular-viewer.html`

Open in a browser. Features:
- Navigate glyphs with arrow keys or Prev/Next buttons
- Search by glyph name
- See regions/holes colored and labeled on the left
- **TTF/UFO toggle** — for glyphs where overlap removal merged contours, switch between TTF region view and UFO per-contour view to choose your coloring granularity
- **Edit the JSON directly** in the right panel (changes persist as you navigate)
- Copy single glyph or full mapping to clipboard (exports correct format per view: `regions` for TTF, `_source: ufo` + `contours` for UFO)
- Palette reference bar showing all 9 ATS colors

**Editing workflow:**
1. Navigate to a glyph
2. Change color indices in the JSON textarea (e.g., `"0.h0": 2` to `"0.h0": 7`)
3. Move to next glyph (edits auto-save)
4. When done, click "Copy All" to get the complete mapping
5. Paste into `color_mapping.json`

---

### Step 5: Apply Color to Build the Color Font

Apply the COLR v0 + CPAL color tables using your mapping:

```bash
# Using the manual mapping with UFO source for layer extraction (recommended):
python tools/add_color.py --style manual --ufo source/TiroTelugu-Regular.ufo

# Without UFO (only colors contours that survive in the compiled TTF):
python tools/add_color.py --style manual

# Or use automatic styles for quick previews:
python tools/add_color.py --style ats        # rotating fill colors
python tools/add_color.py --style region     # largest=black, rest=red
```

**Output:** `*-ColorManual.ttf`, `*-ColorATS.ttf`, or `*-Color.ttf` next to input

The `--ufo` flag extracts layer glyph outlines from the original UFO source, which
preserves contours that would otherwise be merged by overlap removal during TTF compilation.
This is essential for glyphs like `tKa` where the top marks and body share boundaries.

The `manual` style reads `color_mapping.json` and:
- Creates separate layer glyphs for each color group
- Builds COLR v0 layered color records
- Builds CPAL with the 9-color ATS palette
- Unmapped glyphs fall back to the `defaults` strategy

---

### Step 6: Test the Color Font

Generate an HTML test page to see the color font rendered at various sizes:

```bash
python tools/fonttest.py output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular-ColorManual.ttf
```

**Output:** `TiroTelugu-Regular-ColorManual-test.html` next to the font

The test page:
- Embeds the font as a data URI (self-contained, no server needed)
- Shows Telugu sample text at 12pt through 96pt
- Auto-detects script from font filename
- Includes Latin samples for comparison

---

### Step 7: Port to Another Language (Optional)

Remap an existing color font from one Indic script to another:

```bash
python tools/remap_font.py third-party/ATS-Chikkamagaluru/.../ATSChikkamagaluru-ColorRegularCOLR.ttf output/ATSChikkamagaluru-Telugu-Color.ttf
```

This:
- Shifts cmap entries from source script Unicode range to target range
- Renames glyph names (e.g., `*KNDA` to `*TELU`)
- Updates name table and OS/2 unicode range bits
- Preserves all COLR/CPAL color data intact

---

## ATS 9-Color Palette Reference

| Index | Name | Hex | Use |
|-------|------|-----|-----|
| 0 | Dark | `#1D1D1D` | Outline / base region |
| 1 | Red | `#EE3441` | Accent |
| 2 | Yellow | `#F1F09A` | Circular holes |
| 3 | Pink | `#F7ACBA` | Regions below base |
| 4 | Lavender | `#BB9CD4` | Elliptical holes |
| 5 | Magenta | `#EBA7D1` | Regions above base |
| 6 | Peach | `#FBB88F` | Alternate fill |
| 7 | Green | `#93D49B` | Alternate fill |
| 8 | Cyan | `#76CFE9` | Alternate fill |

---

## File Layout (after full pipeline run)

```
output/indigo-telugu/TiroTelugu/TTF/
  TiroTelugu-Regular.ttf                    # compiled base font
  TiroTelugu-Italic.ttf                     # compiled italic
  TiroTelugu-Regular-ColorATS.ttf           # ATS rotating color
  TiroTelugu-Regular-ColorManual.ttf        # manual mapping color
  TiroTelugu-Regular-ColorManual-test.html  # font test page
  TiroTelugu-Regular-viewer.html            # interactive viewer
  color_mapping.json                        # editable color assignments
  svg-contours/                             # per-glyph region visualizations
    TiroTelugu-Regular-contours-specimen.svg
    tKa-contours.svg
    tKha-contours.svg
    ... (812 files)
```

---

## Quick Reference: Run the Full Pipeline

```bash
TTF=output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf
UFO=source/TiroTelugu-Regular.ufo

# 1. Build
python tools/tirobuild.py indigo-telugu.yml

# 2. Visualize (region specimen + individual SVGs)
python tools/glif2svg.py $UFO --telugu --regions --specimen --ttf $TTF
python tools/glif2svg.py $UFO --telugu --regions --ttf $TTF

# 3. Generate mapping (from UFO to see all original contours)
python tools/generate_mapping.py $UFO

# 4. Review (open in browser)
python tools/generate_viewer.py $TTF

# 5. Apply color (with UFO for layer extraction)
python tools/add_color.py --style manual --ufo $UFO $TTF

# 6. Test
python tools/fonttest.py output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular-ColorManual.ttf
```
