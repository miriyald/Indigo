"""
Generate an interactive HTML viewer for color mapping review.

Reads the compiled TTF, extracts region/hole data for each Telugu glyph,
and produces a self-contained HTML file with:
- One glyph at a time with regions/holes colored and labeled
- ATS palette reference bar
- JSON snippet with default mapping, ready to copy
- Prev/next navigation and search

Usage:
    python tools/generate_viewer.py [input.ttf] --output output/color-mapping-viewer.html
"""

import argparse
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from add_color import is_telugu_glyph, contour_bbox_area, detect_regions, classify_regions_smart, ATS_PALETTE


def ttf_contour_to_svg_path(glyph, contour_idx):
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    coords = [glyph.coordinates[i] for i in range(start, end + 1)]
    flags = [glyph.flags[i] for i in range(start, end + 1)]

    if not coords:
        return ""

    n = len(coords)
    parts = []

    first_on = -1
    for i in range(n):
        if flags[i] & 1:
            first_on = i
            break

    if first_on == -1:
        mx = (coords[0][0] + coords[1][0]) / 2
        my = (coords[0][1] + coords[1][1]) / 2
        parts.append(f"M{mx:.0f} {my:.0f}")
    else:
        parts.append(f"M{coords[first_on][0]:.0f} {coords[first_on][1]:.0f}")

    visited = 0
    while visited < n:
        i = (first_on + 1 + visited) % n if first_on >= 0 else visited % n
        if first_on == -1 and visited == 0:
            visited += 1
            continue

        if flags[i] & 1:
            parts.append(f"L{coords[i][0]:.0f} {coords[i][1]:.0f}")
            visited += 1
        else:
            cx, cy = coords[i]
            next_i = (i + 1) % n
            if flags[next_i] & 1:
                parts.append(f"Q{cx:.0f} {cy:.0f} {coords[next_i][0]:.0f} {coords[next_i][1]:.0f}")
                visited += 2
            else:
                nx, ny = coords[next_i]
                mx = (cx + nx) / 2
                my = (cy + ny) / 2
                parts.append(f"Q{cx:.0f} {cy:.0f} {mx:.0f} {my:.0f}")
                visited += 1

    parts.append("Z")
    return "".join(parts)


def contour_bounds(glyph, contour_idx):
    start = 0 if contour_idx == 0 else glyph.endPtsOfContours[contour_idx - 1] + 1
    end = glyph.endPtsOfContours[contour_idx]
    xs = [glyph.coordinates[i][0] for i in range(start, end + 1)]
    ys = [glyph.coordinates[i][1] for i in range(start, end + 1)]
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def extract_glyph_data(font):
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    glyph_order = font.getGlyphOrder()

    glyphs_data = []

    for name in glyph_order:
        if not is_telugu_glyph(name):
            continue
        glyph = glyf[name]
        if glyph.numberOfContours is None or glyph.numberOfContours < 1:
            continue

        regions = detect_regions(glyph)
        has_holes = any(len(holes) > 0 for _, holes in regions)
        if not has_holes:
            continue

        try:
            width = hmtx[name][0]
        except (KeyError, IndexError):
            width = 600

        # Extract SVG paths and bounds for each contour
        contour_paths = []
        contour_bounds_list = []
        for ci in range(glyph.numberOfContours):
            contour_paths.append(ttf_contour_to_svg_path(glyph, ci))
            contour_bounds_list.append(contour_bounds(glyph, ci))

        # Build region data
        region_data = []
        for outer_idx, hole_indices in regions:
            region_data.append({
                "outer": outer_idx,
                "holes": hole_indices
            })

        # Build default mapping using smart position/shape heuristic
        default_mapping = classify_regions_smart(glyph)

        # Build _info string (same format as generate_mapping.py)
        region_info_parts = []
        for ri, (outer_idx, hole_indices) in enumerate(regions):
            area = contour_bbox_area(glyph, outer_idx)
            holes_str = f"+{len(hole_indices)} holes" if hole_indices else ""
            region_info_parts.append(f"r{ri}(area={area}{holes_str})")
        info_str = f"{len(regions)} regions: {', '.join(region_info_parts)}"

        glyphs_data.append({
            "name": name,
            "width": width,
            "contourPaths": contour_paths,
            "contourBounds": contour_bounds_list,
            "regions": region_data,
            "defaultMapping": default_mapping,
            "info": info_str
        })

    return glyphs_data


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Color Mapping Viewer — TiroTelugu</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* Palette bar */
.palette-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    background: #16213e;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
}
.palette-bar label { font-size: 13px; color: #999; margin-right: 8px; }
.swatch {
    width: 36px; height: 28px;
    border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: bold;
    border: 2px solid transparent;
    cursor: default;
}
.swatch span { mix-blend-mode: difference; }

/* Nav bar */
.nav-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 20px;
    background: #0f3460;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
}
.nav-bar button {
    padding: 6px 14px;
    border: 1px solid #555;
    border-radius: 4px;
    background: #1a1a2e;
    color: #e0e0e0;
    cursor: pointer;
    font-size: 13px;
}
.nav-bar button:hover { background: #2a2a4e; }
.nav-bar .counter { font-size: 14px; font-weight: 600; min-width: 180px; text-align: center; }
.nav-bar input[type="text"] {
    padding: 5px 10px;
    border: 1px solid #555;
    border-radius: 4px;
    background: #1a1a2e;
    color: #e0e0e0;
    font-size: 13px;
    width: 160px;
}

/* Main content */
.main {
    display: flex;
    flex: 1;
    overflow: hidden;
}

/* SVG panel */
.svg-panel {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    background: #0d1117;
    position: relative;
}
.svg-panel svg {
    max-width: 100%;
    max-height: 100%;
}

/* JSON panel */
.json-panel {
    width: 380px;
    display: flex;
    flex-direction: column;
    border-left: 1px solid #333;
    background: #16213e;
}
.json-panel-header {
    padding: 10px 16px;
    border-bottom: 1px solid #333;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
}
.json-panel-header h3 { font-size: 13px; flex: 1; }
.json-panel-header button {
    padding: 4px 10px;
    border: 1px solid #555;
    border-radius: 3px;
    background: #1a1a2e;
    color: #e0e0e0;
    cursor: pointer;
    font-size: 12px;
}
.json-panel-header button:hover { background: #2a2a4e; }
.json-panel-header button.copied { background: #2a9d8f; border-color: #2a9d8f; }
.json-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
}
.json-content textarea {
    font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre;
    color: #c9d1d9;
    background: transparent;
    border: none;
    outline: none;
    resize: none;
    width: 100%;
    height: 100%;
    min-height: 200px;
}
.json-content textarea:focus {
    background: rgba(255,255,255,0.03);
}

/* Legend in SVG panel */
.legend {
    position: absolute;
    bottom: 10px;
    left: 10px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 12px;
    font-family: monospace;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
}
.legend-color {
    width: 14px; height: 14px;
    border-radius: 2px;
}

/* Toast */
.toast {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 8px 16px;
    background: #2a9d8f;
    color: #fff;
    border-radius: 4px;
    font-size: 13px;
    opacity: 0;
    transition: opacity 0.3s;
    pointer-events: none;
}
.toast.show { opacity: 1; }
</style>
</head>
<body>

<div class="palette-bar">
    <label>Palette:</label>
    <div class="swatch" id="sw0" style="background:#1D1D1D;color:#fff"><span>0</span></div>
    <div class="swatch" id="sw1" style="background:#EE3441;color:#fff"><span>1</span></div>
    <div class="swatch" id="sw2" style="background:#F1F09A;color:#000"><span>2</span></div>
    <div class="swatch" id="sw3" style="background:#F7ACBA;color:#000"><span>3</span></div>
    <div class="swatch" id="sw4" style="background:#BB9CD4;color:#000"><span>4</span></div>
    <div class="swatch" id="sw5" style="background:#EBA7D1;color:#000"><span>5</span></div>
    <div class="swatch" id="sw6" style="background:#FBB88F;color:#000"><span>6</span></div>
    <div class="swatch" id="sw7" style="background:#93D49B;color:#000"><span>7</span></div>
    <div class="swatch" id="sw8" style="background:#76CFE9;color:#000"><span>8</span></div>
</div>

<div class="nav-bar">
    <button id="btn-prev">&larr; Prev</button>
    <button id="btn-next">Next &rarr;</button>
    <span class="counter" id="counter">...</span>
    <input type="text" id="search" placeholder="Search glyph name...">
</div>

<div class="main">
    <div class="svg-panel">
        <svg id="glyph-svg" xmlns="http://www.w3.org/2000/svg"></svg>
        <div class="legend" id="legend"></div>
    </div>
    <div class="json-panel">
        <div class="json-panel-header">
            <h3>Mapping JSON</h3>
            <button id="btn-copy">Copy</button>
            <button id="btn-copy-all">Copy All</button>
        </div>
        <div class="json-content">
            <textarea id="json-output" spellcheck="false"></textarea>
        </div>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
const GLYPHS = __GLYPHS_DATA__;

const PALETTE = [
    "#1D1D1D", "#EE3441", "#F1F09A", "#F7ACBA",
    "#BB9CD4", "#EBA7D1", "#FBB88F", "#93D49B", "#76CFE9"
];

const REGION_COLORS = [
    "#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261",
    "#264653", "#6A0572", "#AB83A1", "#118AB2", "#06D6A0"
];
const HOLE_COLORS = [
    "#FF6B9D", "#FFD93D", "#6BCB77", "#4D96FF", "#C9B1FF",
    "#FF8F5E", "#45CFDD", "#F038FF", "#B8E986", "#FFA8A8"
];

let currentIdx = 0;

function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 1500);
}

function saveCurrentEdits() {
    const ta = document.getElementById("json-output");
    const g = GLYPHS[currentIdx];
    try {
        const parsed = JSON.parse(ta.value);
        const entry = parsed[g.name];
        if (entry && entry.regions) {
            g.defaultMapping = entry.regions;
        }
    } catch(e) {}
}

function renderGlyph(idx) {
    if (idx < 0 || idx >= GLYPHS.length) return;
    saveCurrentEdits();
    currentIdx = idx;

    const g = GLYPHS[idx];
    document.getElementById("counter").textContent = `${g.name} (${idx + 1}/${GLYPHS.length})`;

    // Build SVG
    const ascender = 800;
    const margin = 50;
    const totalH = 1000; // ascender - descender
    const vbW = g.width + margin * 2;
    const vbH = totalH + margin * 2;

    let svg = `<svg id="glyph-svg" xmlns="http://www.w3.org/2000/svg" viewBox="${-margin} ${-margin} ${vbW} ${vbH}" width="${vbW}" height="${vbH}">`;
    svg += `<g transform="translate(0,${ascender + margin}) scale(1,-1)">`;

    // Draw regions (outer + holes as cutouts)
    let holeGlobalIdx = 0;
    for (let ri = 0; ri < g.regions.length; ri++) {
        const region = g.regions[ri];
        const color = REGION_COLORS[ri % REGION_COLORS.length];
        let path = g.contourPaths[region.outer] || "";
        for (const hi of region.holes) {
            path += " " + (g.contourPaths[hi] || "");
        }
        if (path) {
            svg += `<path d="${path}" fill="${color}" fill-rule="nonzero" opacity="0.55"/>`;
        }
        // Draw holes filled
        for (let hi = 0; hi < region.holes.length; hi++) {
            const holeColor = HOLE_COLORS[holeGlobalIdx % HOLE_COLORS.length];
            const holePath = g.contourPaths[region.holes[hi]] || "";
            if (holePath) {
                svg += `<path d="${holePath}" fill="${holeColor}" fill-rule="nonzero" opacity="0.85"/>`;
            }
            holeGlobalIdx++;
        }
    }

    svg += `</g>`;

    // Labels (in SVG-down space)
    holeGlobalIdx = 0;
    for (let ri = 0; ri < g.regions.length; ri++) {
        const region = g.regions[ri];
        const b = g.contourBounds[region.outer];
        if (b) {
            const cx = (b[0] + b[2]) / 2;
            const cy = ascender + margin - (b[1] + b[3]) / 2;
            const color = REGION_COLORS[ri % REGION_COLORS.length];
            svg += `<text x="${cx}" y="${cy}" font-family="monospace" font-size="28" fill="${color}" text-anchor="middle" font-weight="bold">r${ri}</text>`;
        }
        for (let hi = 0; hi < region.holes.length; hi++) {
            const hb = g.contourBounds[region.holes[hi]];
            if (hb) {
                const cx = (hb[0] + hb[2]) / 2;
                const cy = ascender + margin - (hb[1] + hb[3]) / 2;
                const holeColor = HOLE_COLORS[holeGlobalIdx % HOLE_COLORS.length];
                svg += `<text x="${cx}" y="${cy}" font-family="monospace" font-size="18" fill="${holeColor}" text-anchor="middle" font-weight="bold">${ri}.h${hi}</text>`;
            }
            holeGlobalIdx++;
        }
    }

    svg += `</svg>`;
    document.getElementById("glyph-svg").outerHTML = svg;

    // Legend
    let legendHtml = "";
    holeGlobalIdx = 0;
    for (let ri = 0; ri < g.regions.length; ri++) {
        const color = REGION_COLORS[ri % REGION_COLORS.length];
        legendHtml += `<span class="legend-item"><span class="legend-color" style="background:${color}"></span>r${ri}</span>`;
        for (let hi = 0; hi < g.regions[ri].holes.length; hi++) {
            const hc = HOLE_COLORS[holeGlobalIdx % HOLE_COLORS.length];
            legendHtml += `<span class="legend-item"><span class="legend-color" style="background:${hc}"></span>${ri}.h${hi}</span>`;
            holeGlobalIdx++;
        }
    }
    document.getElementById("legend").innerHTML = legendHtml;

    // JSON
    const jsonObj = {};
    jsonObj[g.name] = { "_info": g.info, "regions": g.defaultMapping };
    document.getElementById("json-output").value = JSON.stringify(jsonObj, null, 2);
}

function buildFullMapping() {
    const mapping = {
        "_meta": {
            "palette": "ats",
            "description": "Manual region-to-color mapping for TiroTelugu COLR v0",
            "note": "Each region is an outer contour + its holes. Fill respects holes."
        },
        "defaults": { "unmapped_regions": 0, "unmapped_glyphs": "auto:region" },
        "glyphs": {}
    };
    for (const g of GLYPHS) {
        mapping.glyphs[g.name] = { "_info": g.info, "regions": g.defaultMapping };
    }
    return mapping;
}

// Navigation
document.getElementById("btn-prev").addEventListener("click", () => renderGlyph(currentIdx - 1));
document.getElementById("btn-next").addEventListener("click", () => renderGlyph(currentIdx + 1));

document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.key === "ArrowLeft") renderGlyph(currentIdx - 1);
    if (e.key === "ArrowRight") renderGlyph(currentIdx + 1);
});

// Search
document.getElementById("search").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    if (!q) return;
    const idx = GLYPHS.findIndex(g => g.name.toLowerCase().includes(q));
    if (idx >= 0) renderGlyph(idx);
});

// Copy
document.getElementById("btn-copy").addEventListener("click", () => {
    saveCurrentEdits();
    const g = GLYPHS[currentIdx];
    const obj = {};
    obj[g.name] = { "_info": g.info, "regions": g.defaultMapping };
    navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
    showToast("Copied " + g.name);
});

document.getElementById("btn-copy-all").addEventListener("click", () => {
    saveCurrentEdits();
    const mapping = buildFullMapping();
    navigator.clipboard.writeText(JSON.stringify(mapping, null, 2));
    showToast("Copied full mapping (" + GLYPHS.length + " glyphs)");
});

// Init
renderGlyph(0);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Generate interactive color mapping viewer HTML")
    parser.add_argument("input", nargs="?", help="Input TTF path")
    parser.add_argument("--output", "-o", help="Output HTML path (default: next to input TTF)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    input_path = Path(args.input) if args.input else base_dir / "output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf"
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / (input_path.stem + "-viewer.html")

    print(f"Loading {input_path}")
    font = TTFont(str(input_path))

    print("Extracting glyph data...")
    glyphs_data = extract_glyph_data(font)
    print(f"  {len(glyphs_data)} glyphs with holes")

    # Generate HTML
    glyphs_json = json.dumps(glyphs_data, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__GLYPHS_DATA__", glyphs_json)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Saved viewer: {output_path}")
    print(f"  Open in browser to use")


if __name__ == "__main__":
    main()
