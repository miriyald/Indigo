"""Generate an HTML font test page for a given font file.

Usage:
    python tools/fonttest.py path/to/font.ttf
    python tools/fonttest.py path/to/font.otf --output test.html
"""

import argparse
from pathlib import Path

SIZES = [24, 36]

def _generate_telugu_comprehensive_test():
    """Generate systematic Telugu character coverage test.
    Returns OrderedDict of {group_name: [items]}.
    """
    from collections import OrderedDict
    groups = OrderedDict()

    groups["Text"] = [
        "ఆంతరంగిక, కుటుంబ, గృహ, లేఖావ్యవహారములలో, విధి విరుద్ధమయిన జోక్యమునకుగాని, గౌరవప్రతిష్థలను భంగపరచు ప్రచారములకుగాని యెవరిని గురిచేయరాదు.",
        "ప్రతి వ్యక్తికిని భావస్వాతంత్ర్య, అంతఃకరణస్వాతంత్ర్య, మతస్వాతంత్ర్యములకు హక్కు గలదు.",
    ]

    vowels = [chr(c) for c in range(0x0C05, 0x0C15)]
    vowels += [chr(c) for c in range(0x0C61, 0x0C64)]
    groups["Vowels (U+0C05–0C14, U+0C61–0C63)"] = vowels

    special = [f"◌{chr(c)}" for c in range(0x0C00, 0x0C05)]
    groups["Special Marks (U+0C00–0C04)"] = special

    consonants = [chr(c) for c in range(0x0C15, 0x0C3A)]
    consonants += [chr(0x0C58), chr(0x0C59)]
    groups["Consonants (U+0C15–0C39, U+0C58, U+0C59)"] = consonants

    extenders = [chr(c) for c in range(0x0C3E, 0x0C4E)]
    extenders += [chr(0x0C55), chr(0x0C56)]
    extenders += [chr(0x0C5D)]
    groups["Extenders (U+0C3E–0C4D, U+0C55, U+0C56, U+0C5D)"] = [f"◌{e}" for e in extenders]

    numbers = [chr(c) for c in range(0x0C66, 0x0C70)]
    groups["Numbers (U+0C66–0C6F)"] = numbers

    siddham = [chr(c) for c in range(0x0C77, 0x0C80)]
    groups["Siddham (U+0C77–0C7F)"] = siddham

    for cons in consonants:
        combos = [f"{cons}{ext}" for ext in extenders]
        groups[f"Composites: {cons}"] = combos

    virama = chr(0x0C4D)
    for c1 in consonants:
        conjuncts = [f"{c1}{virama}{c2}" for c2 in consonants]
        groups[f"Conjuncts: {c1}+్"] = conjuncts

    return groups


def _generate_latin_comprehensive_test():
    """Generate systematic Latin character coverage test.
    Returns OrderedDict of {group_name: [items]}.
    """
    from collections import OrderedDict
    groups = OrderedDict()

    groups["Uppercase (A–Z)"] = [chr(c) for c in range(0x41, 0x5B)]
    groups["Lowercase (a–z)"] = [chr(c) for c in range(0x61, 0x7B)]
    groups["Digits (0–9)"] = [chr(c) for c in range(0x30, 0x3A)]

    punct = [chr(c) for c in range(0x21, 0x30)]
    punct += [chr(c) for c in range(0x3A, 0x41)]
    punct += [chr(c) for c in range(0x5B, 0x61)]
    punct += [chr(c) for c in range(0x7B, 0x7F)]
    groups["Punctuation & Symbols"] = punct

    ligatures = ["fi", "fl", "ff", "ffi", "ffl"]
    typo = [chr(0x2014), chr(0x2013), chr(0x201E) + chr(0x201C), chr(0x201C) + chr(0x201D), chr(0x2018) + chr(0x2019), chr(0xAB) + chr(0xBB)]
    groups["Ligatures & Typographic"] = ligatures + typo

    groups["Latin Extended-A (U+0100–017F)"] = [chr(c) for c in range(0x0100, 0x0180)]
    groups["Latin Extended-B (U+0180–024F)"] = [chr(c) for c in range(0x0180, 0x0250)]

    return groups


SAMPLE_TEXT = {
    "Telu": _generate_telugu_comprehensive_test(),
    "Deva": {
        "Text": [
            "सभी मनुष्यों को गौरव और अधिकारों के मामले में जन्मजात स्वतन्त्रता और समानता प्राप्त है।",
            "उन्हें बुद्धि और अन्तरात्मा की देन प्राप्त है और परस्पर उन्हें भाईचारे के भाव से बर्ताव करना चाहिए।",
        ],
        "Consonants": list("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह"),
        "Vowels": list("अआइईउऊऋॠएऐओऔ") + ["अं", "अः"],
        "Digits": list("०१२३४५६७८९"),
    },
    "Beng": {
        "Text": [
            "সমস্ত মানুষ স্বাধীনভাবে সমান মর্যাদা এবং অধিকার নিয়ে জন্মগ্রহণ করে।",
            "তাঁদের বিবেক এবং বুদ্ধি আছে; সুতরাং সকলেরই একে অপরের প্রতি ভ্রাতৃত্বসুলভ মনোভাব নিয়ে আচরণ করা উচিত।",
        ],
        "Consonants": list("কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ"),
        "Vowels": list("অআইঈউঊঋএঐওঔ") + ["অং", "অঃ"],
        "Digits": list("০১২৩৪৫৬৭৮৯"),
    },
    "Taml": {
        "Text": [
            "மனிதப் பிறிவியினர் சகலரும் சுதந்திரமாகவே பிறக்கின்றனர்.",
            "அவர்கள் மதிப்பிலும் உரிமைகளிலும் சமமானவர்கள்.",
        ],
        "Consonants": list("கஙசஞடணதநபமயரலவழளறன") + list("ஜஷஸஹ"),
        "Vowels": list("அஆஇஈஉஊஎஏஐஒஓஔ"),
        "Digits": list("௦௧௨௩௪௫௬௭௮௯"),
    },
    "Knda": {
        "Text": [
            "ಎಲ್ಲಾ ಮಾನವರೂ ಸ್ವತಂತ್ರರಾಗಿಯೇ ಜನಿಸಿದ್ಧಾರೆ.",
            "ಹಾಗೂ ಘನತೆ ಮತ್ತು ಹಕ್ಕುಗಳಲ್ಲಿ ಸಮಾನರಾಗಿದ್ದಾರೆ.",
        ],
        "Consonants": list("ಕಖಗಘಙಚಛಜಝಞಟಠಡಢಣತಥದಧನಪಫಬಭಮಯರಲವಶಷಸಹಳ"),
        "Vowels": list("ಅಆಇಈಉಊಋಎಏಐಒಓಔ") + ["ಅಂ", "ಅಃ"],
        "Digits": list("೦೧೨೩೪೫೬೭೮೯"),
    },
    "Guru": {
        "Text": [
            "ਸਾਰਾ ਮਨੁੱਖੀ ਪਰਿਵਾਰ ਆਪਣੀ ਮਹਿਮਾ, ਸ਼ਾਨ ਅਤੇ ਹੱਕਾਂ ਦੇ ਪੱਖੋਂ ਬਰਾਬਰ ਹੈ।",
            "ਉਨ੍ਹਾਂ ਨੂੰ ਤਰਕ ਅਤੇ ਜ਼ਮੀਰ ਦੀ ਸੌਗ਼ਾਤ ਮਿਲੀ ਹੋਈ ਹੈ ਅਤੇ ਉਨ੍ਹਾਂ ਨੂੰ ਭਰਾਤਰੀਭਾਵ ਦੀ ਭਾਵਨਾ ਰਖਣੀ ਚਾਹੀਦੀ ਹੈ।",
        ],
        "Consonants": list("ਕਖਗਘਙਚਛਜਝਞਟਠਡਢਣਤਥਦਧਨਪਫਬਭਮਯਰਲਵ") + ["ਸ਼", "ਸ", "ਹ"],
        "Digits": list("੦੧੨੩੪੫੬੭੮੯"),
    },
    "Latn": _generate_latin_comprehensive_test(),
}

SCRIPT_TAG_MAP = {
    "telugu": "Telu",
    "telu": "Telu",
    "devanagari": "Deva",
    "deva": "Deva",
    "hindi": "Deva",
    "marathi": "Deva",
    "sanskrit": "Deva",
    "bengali": "Beng",
    "bangla": "Beng",
    "beng": "Beng",
    "tamil": "Taml",
    "taml": "Taml",
    "kannada": "Knda",
    "knda": "Knda",
    "gurmukhi": "Guru",
    "guru": "Guru",
    "latin": "Latn",
    "latn": "Latn",
}


def detect_script(font_path):
    name = font_path.stem.lower()
    for key, tag in SCRIPT_TAG_MAP.items():
        if key in name:
            return tag
    return "Latn"


def font_src_url(font_path, output_path):
    """Return a relative URL from the output HTML to the font file."""
    try:
        rel = font_path.relative_to(output_path.parent)
    except ValueError:
        rel = Path(font_path.name)
    return str(rel).replace("\\", "/")


def generate_html(font_path, output_path=None, download_link=None, author=None, project_url=None):
    font_path = Path(font_path).resolve()
    if not font_path.exists():
        raise FileNotFoundError(f"Font not found: {font_path}")

    script = detect_script(font_path)
    font_name = font_path.stem

    if output_path is None:
        resolved_output = font_path.parent / f"{font_name}-test.html"
    else:
        resolved_output = Path(output_path).resolve()

    font_url = font_src_url(font_path, resolved_output)

    script_data = SAMPLE_TEXT.get(script, SAMPLE_TEXT["Latn"])
    if script != "Latn":
        latn_data = SAMPLE_TEXT.get("Latn", {})
    else:
        latn_data = {}

    header_extra = ""
    if author:
        author_html = author
        if project_url:
            author_html = f'<a href="{project_url}">{author}</a>'
        header_extra += f'<p class="author">Color Font by {author_html}</p>\n'
    if download_link:
        header_extra += f'<p class="download"><a href="{download_link}" download>Download {font_path.name}</a></p>\n'

    def _render_groups(groups, size):
        html = ""
        for group_name, items in groups.items():
            html += f'<h3>{group_name}</h3>\n'
            is_text = all(len(item) > 5 for item in items)
            if is_text:
                for item in items:
                    html += f'<p style="font-size: {size}px;">{item}</p>\n'
            else:
                html += f'<div class="grid" style="font-size: {size}px;">\n'
                for item in items:
                    html += f'<span class="cell">{item}</span>\n'
                html += '</div>\n'
        return html

    samples_html = ""
    for size in SIZES:
        samples_html += f'<div class="size-block">\n'
        samples_html += f'<h2>{size}pt</h2>\n'
        samples_html += _render_groups(script_data, size)
        if latn_data:
            samples_html += "<hr>\n"
            samples_html += _render_groups(latn_data, size)
        samples_html += "</div>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Font Test — {font_name}</title>
<style>
@font-face {{
    font-family: "TestFont";
    src: url("{font_url}");
}}
body {{
    font-family: "TestFont", serif;
    margin: 20px;
    padding: 0;
    background: #fff;
    color: #000;
}}
h1 {{
    font-family: system-ui, sans-serif;
    font-size: 16px;
    color: #555;
    border-bottom: 1px solid #ccc;
    padding-bottom: 8px;
}}
.author {{
    font-family: system-ui, sans-serif;
    font-size: 14px;
    color: #333;
    margin: 8px 0;
}}
.author a {{
    color: #0366d6;
    text-decoration: none;
}}
.download {{
    font-family: system-ui, sans-serif;
    margin: 12px 0;
}}
.download a {{
    display: inline-block;
    padding: 8px 16px;
    background: #0366d6;
    color: #fff;
    border-radius: 4px;
    text-decoration: none;
    font-size: 14px;
}}
.download a:hover {{
    background: #0250a3;
}}
h2 {{
    font-family: system-ui, sans-serif;
    font-size: 13px;
    color: #888;
    margin: 32px 0 8px;
}}
h3 {{
    font-family: system-ui, sans-serif;
    font-size: 12px;
    color: #666;
    margin: 20px 0 4px;
    font-weight: normal;
}}
.grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    margin: 4px 0;
}}
.cell {{
    display: flex;
    align-items: center;
    justify-content: center;
    width: 3em;
    height: 3em;
    border: 1px solid #eee;
    box-sizing: border-box;
}}
.cell:hover {{
    background: #f5f5f5;
    border-color: #ccc;
}}
.row-label {{
    font-family: system-ui, sans-serif;
    font-size: 12px !important;
    color: #999;
    margin: 8px 0 2px;
}}
hr {{
    border: none;
    border-top: 1px dashed #ddd;
    margin: 12px 0;
}}
.size-block {{
    margin-bottom: 40px;
}}
@media print {{
    body {{ margin: 10px; }}
    .cell {{ border-color: #ddd; }}
}}
</style>
</head>
<body>
<h1>{font_name} &mdash; {font_path.name} &mdash; Script: {script}</h1>
{header_extra}{samples_html}
</body>
</html>
"""

    resolved_output.write_text(html, encoding="utf-8")
    print(f"Generated: {resolved_output}")
    return resolved_output


def main():
    parser = argparse.ArgumentParser(description="Generate an HTML font test page.")
    parser.add_argument("font", type=Path, help="Path to font file (.ttf, .otf, .woff, .woff2)")
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path (default: <font>-test.html)")
    parser.add_argument("-s", "--script", help="Override script detection (e.g. Telu, Deva, Beng, Taml, Knda, Guru, Latn)")
    parser.add_argument("--download-link", help="URL or path for font download button")
    parser.add_argument("--author", help="Author name to display on the page")
    parser.add_argument("--project-url", help="Project URL to link from author name")
    args = parser.parse_args()

    if args.script:
        tag = SCRIPT_TAG_MAP.get(args.script.lower(), args.script)
        global detect_script
        original_detect = detect_script
        detect_script = lambda p: tag

    generate_html(args.font, args.output, args.download_link, args.author, args.project_url)


if __name__ == "__main__":
    main()
