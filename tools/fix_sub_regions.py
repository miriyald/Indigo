import json
from pathlib import Path

INPUT = Path("source/TiroTelugu-Regular.ufo/data/color_mapping.json")

data = json.loads(INPUT.read_text(encoding="utf-8"))
glyphs = data["glyphs"]
changed = 0

for name, entry in glyphs.items():
    if "sub" not in name:
        continue

    has_regions = "regions" in entry
    has_ufo_contours = "ufo_contours" in entry

    if has_regions and has_ufo_contours:
        # Remove ufo_contours and _ufo_info
        entry.pop("ufo_contours", None)
        entry.pop("_ufo_info", None)
        # Set region values: holes (.h) → 2, others → 5
        for key in entry["regions"]:
            entry["regions"][key] = 2 if ".h" in key else 5
        changed += 1

    elif has_ufo_contours and not has_regions:
        # Set all ufo_contour values to 5
        for key in entry["ufo_contours"]:
            entry["ufo_contours"][key] = 5
        changed += 1

INPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Done. {changed} glyph(s) updated.")
