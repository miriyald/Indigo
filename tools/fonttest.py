"""Generate an HTML font test page for a given font file.

Usage:
    python tools/fonttest.py path/to/font.ttf
    python tools/fonttest.py path/to/font.otf --output test.html
"""

import argparse
import base64
import mimetypes
from pathlib import Path

SIZES = [12, 18, 24, 36, 48, 72, 96]

SAMPLE_TEXT = {
    "Telu": [
        "అందరూ స్వతంత్రులై సమానమైన గౌరవం మరియు హక్కులతో జన్మించారు.",
        "వారికి హేతువు మరియు అంతరాత్మ ఉన్నాయి మరియు వారు ఒకరినొకరు సోదరభావంతో మెలగాలి.",
        "తెలుగు భాష భారతదేశంలోని ద్రావిడ భాషా కుటుంబానికి చెందిన భాష.",
        "క ఖ గ ఘ ఙ చ ఛ జ ఝ ఞ ట ఠ డ ఢ ణ త థ ద ధ న ప ఫ బ భ మ య ర ల వ శ ష స హ ళ",
        "అ ఆ ఇ ఈ ఉ ఊ ఋ ౠ ఎ ఏ ఐ ఒ ఓ ఔ అం అః",
        "౦ ౧ ౨ ౩ ౪ ౫ ౬ ౭ ౮ ౯",
    ],
    "Deva": [
        "सभी मनुष्यों को गौरव और अधिकारों के मामले में जन्मजात स्वतन्त्रता और समानता प्राप्त है।",
        "उन्हें बुद्धि और अन्तरात्मा की देन प्राप्त है और परस्पर उन्हें भाईचारे के भाव से बर्ताव करना चाहिए।",
        "क ख ग घ ङ च छ ज झ ञ ट ठ ड ढ ण त थ द ध न प फ ब भ म य र ल व श ष स ह",
        "अ आ इ ई उ ऊ ऋ ॠ ए ऐ ओ औ अं अः",
        "० १ २ ३ ४ ५ ६ ७ ८ ९",
    ],
    "Beng": [
        "সমস্ত মানুষ স্বাধীনভাবে সমান মর্যাদা এবং অধিকার নিয়ে জন্মগ্রহণ করে।",
        "তাঁদের বিবেক এবং বুদ্ধি আছে; সুতরাং সকলেরই একে অপরের প্রতি ভ্রাতৃত্বসুলভ মনোভাব নিয়ে আচরণ করা উচিত।",
        "ক খ গ ঘ ঙ চ ছ জ ঝ ঞ ট ঠ ড ঢ ণ ত থ দ ধ ন প ফ ব ভ ম য র ল শ ষ স হ",
        "অ আ ই ঈ উ ঊ ঋ এ ঐ ও ঔ অং অঃ",
        "০ ১ ২ ৩ ৪ ৫ ৬ ৭ ৮ ৯",
    ],
    "Taml": [
        "மனிதப் பிறிவியினர் சகலரும் சுதந்திரமாகவே பிறக்கின்றனர்.",
        "அவர்கள் மதிப்பிலும் உரிமைகளிலும் சமமானவர்கள்.",
        "க ங ச ஞ ட ண த ந ப ம ய ர ல வ ழ ள ற ன ஜ ஷ ஸ ஹ",
        "அ ஆ இ ஈ உ ஊ எ ஏ ஐ ஒ ஓ ஔ",
        "௦ ௧ ௨ ௩ ௪ ௫ ௬ ௭ ௮ ௯",
    ],
    "Knda": [
        "ಎಲ್ಲಾ ಮಾನವರೂ ಸ್ವತಂತ್ರರಾಗಿಯೇ ಜನಿಸಿದ್ಧಾರೆ.",
        "ಹಾಗೂ ಘನತೆ ಮತ್ತು ಹಕ್ಕುಗಳಲ್ಲಿ ಸಮಾನರಾಗಿದ್ದಾರೆ.",
        "ಕ ಖ ಗ ಘ ಙ ಚ ಛ ಜ ಝ ಞ ಟ ಠ ಡ ಢ ಣ ತ ಥ ದ ಧ ನ ಪ ಫ ಬ ಭ ಮ ಯ ರ ಲ ವ ಶ ಷ ಸ ಹ ಳ",
        "ಅ ಆ ಇ ಈ ಉ ಊ ಋ ಎ ಏ ಐ ಒ ಓ ಔ ಅಂ ಅಃ",
        "೦ ೧ ೨ ೩ ೪ ೫ ೬ ೭ ೮ ೯",
    ],
    "Guru": [
        "ਸਾਰਾ ਮਨੁੱਖੀ ਪਰਿਵਾਰ ਆਪਣੀ ਮਹਿਮਾ, ਸ਼ਾਨ ਅਤੇ ਹੱਕਾਂ ਦੇ ਪੱਖੋਂ ਬਰਾਬਰ ਹੈ।",
        "ਉਨ੍ਹਾਂ ਨੂੰ ਤਰਕ ਅਤੇ ਜ਼ਮੀਰ ਦੀ ਸੌਗ਼ਾਤ ਮਿਲੀ ਹੋਈ ਹੈ ਅਤੇ ਉਨ੍ਹਾਂ ਨੂੰ ਭਰਾਤਰੀਭਾਵ ਦੀ ਭਾਵਨਾ ਰਖਣੀ ਚਾਹੀਦੀ ਹੈ।",
        "ਕ ਖ ਗ ਘ ਙ ਚ ਛ ਜ ਝ ਞ ਟ ਠ ਡ ਢ ਣ ਤ ਥ ਦ ਧ ਨ ਪ ਫ ਬ ਭ ਮ ਯ ਰ ਲ ਵ ਸ਼ ਸ ਹ",
        "੦ ੧ ੨ ੩ ੪ ੫ ੬ ੭ ੮ ੯",
    ],
    "Latn": [
        "The quick brown fox jumps over the lazy dog.",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz",
        "0123456789 !@#$%^&*() .,;:?!\"'",
        "fi fl ff ffi ffl — – „“ “” ‘’ «»",
    ],
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


def font_to_data_uri(font_path):
    suffix = font_path.suffix.lower()
    mime_map = {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    mime = mime_map.get(suffix, "font/ttf")
    data = font_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def generate_html(font_path, output_path=None):
    font_path = Path(font_path).resolve()
    if not font_path.exists():
        raise FileNotFoundError(f"Font not found: {font_path}")

    script = detect_script(font_path)
    font_name = font_path.stem
    data_uri = font_to_data_uri(font_path)

    texts = SAMPLE_TEXT.get(script, SAMPLE_TEXT["Latn"])
    if script != "Latn" and "Latn" in SAMPLE_TEXT:
        texts = texts + [""] + SAMPLE_TEXT["Latn"]

    samples_html = ""
    for size in SIZES:
        samples_html += f'<div class="size-block">\n'
        samples_html += f'<h2>{size}pt</h2>\n'
        for line in texts:
            if line == "":
                samples_html += "<hr>\n"
            else:
                samples_html += f'<p style="font-size: {size}px;">{line}</p>\n'
        samples_html += "</div>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Font Test — {font_name}</title>
<style>
@font-face {{
    font-family: "TestFont";
    src: url("{data_uri}");
}}
body {{
    font-family: "TestFont", serif;
    margin: 40px auto;
    max-width: 900px;
    padding: 0 20px;
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
h2 {{
    font-family: system-ui, sans-serif;
    font-size: 13px;
    color: #888;
    margin: 32px 0 8px;
}}
p {{
    margin: 4px 0;
    line-height: 1.4;
}}
hr {{
    border: none;
    border-top: 1px dashed #ddd;
    margin: 12px 0;
}}
.size-block {{
    margin-bottom: 40px;
    page-break-inside: avoid;
}}
@media print {{
    body {{ margin: 20px; max-width: 100%; }}
    h1 {{ font-size: 12px; }}
    .size-block {{ page-break-inside: avoid; }}
}}
</style>
</head>
<body>
<h1>{font_name} &mdash; {font_path.name} &mdash; Script: {script}</h1>
{samples_html}
</body>
</html>
"""

    if output_path is None:
        output_path = font_path.parent / f"{font_name}-test.html"
    else:
        output_path = Path(output_path)

    output_path.write_text(html, encoding="utf-8")
    print(f"Generated: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate an HTML font test page.")
    parser.add_argument("font", type=Path, help="Path to font file (.ttf, .otf, .woff, .woff2)")
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path (default: <font>-test.html)")
    parser.add_argument("-s", "--script", help="Override script detection (e.g. Telu, Deva, Beng, Taml, Knda, Guru, Latn)")
    args = parser.parse_args()

    if args.script:
        tag = SCRIPT_TAG_MAP.get(args.script.lower(), args.script)
        global detect_script
        original_detect = detect_script
        detect_script = lambda p: tag

    generate_html(args.font, args.output)


if __name__ == "__main__":
    main()
