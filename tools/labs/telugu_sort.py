"""
Logical sort order for Telugu glyph names.

Groups glyphs into categories following the traditional Telugu aksharamala order:
1. Signs (Candrabindu, Anusvara, Visarga, etc.)
2. Vowels (A, Aa, I, Ii, U, Uu, VocalicR, VocalicL, E, Ee, Ai, O, Oo, Au)
3. Vowel signs (dependent matras: SignAa, SignIi, etc.)
4. Consonants grouped by varga, each with full vowel paradigm:
   Ka-varga, Ca-varga, Tta-varga, Ta-varga, Pa-varga, then Ya-group
5. Conjuncts (KSs, Ts, Dz, Rrr, etc.)
6. Digits
7. Miscellaneous / special forms
"""


# Halant bases in traditional Telugu order
CONSONANT_ORDER = [
    'K', 'Kh', 'G', 'Gh', 'Ng',
    'C', 'Ch', 'J', 'Jh', 'Ny',
    'Tt', 'Tth', 'Dd', 'Ddh', 'Nn',
    'T', 'Th', 'D', 'Dh', 'N',
    'P', 'Ph', 'B', 'Bh', 'M',
    'Y', 'R', 'Rr', 'L', 'Ll', 'Lll', 'V', 'Sh', 'Ss', 'S', 'H',
]

# Additional consonants / conjuncts (placed after main consonants)
EXTRA_CONSONANTS = ['Dz', 'Ts', 'Rrr', 'KSs']

ALL_BASES = CONSONANT_ORDER + EXTRA_CONSONANTS

# Vowel forms in syllabic order ('' = halant/virama form)
VOWEL_FORMS = ['a', 'aa', 'i', 'ii', 'u', 'uu', 'e', 'ee', 'ai', 'o', 'oo', 'au', '']

# Positional variant suffixes in display order
SUFFIX_ORDER = ['', 'post', 'post2', 'sub', 'presub', 'pssp', 'pssp2', 'pvsp', 'ss01', 'ss02', 'ss03', 'ss04', 'sups']

# Standalone vowels in Unicode order
VOWEL_ORDER = ['A', 'Aa', 'I', 'Ii', 'U', 'Uu', 'VocalicR', 'VocalicRr', 'VocalicL', 'VocalicLl', 'E', 'Ee', 'Ai', 'O', 'Oo', 'Au']

# Signs in Unicode order
SIGN_ORDER = ['Candrabindu', 'Anusvara', 'AnusvaraAbove', 'Visarga', 'NakaaraPollu', 'Nukta', 'Virama', 'AiLengthMark', 'Tuumu']

# Vowel signs (dependent forms) in Unicode order
VOWEL_SIGN_ORDER = ['SignAa', 'SignIi', 'SignUu', 'SignVocalicR', 'SignVocalicRr', 'SignVocalicL', 'SignVocalicLl', 'SignEe', 'SignAi', 'SignO', 'SignOo', 'SignAu']

# Digits in numeric order
DIGIT_NAMES = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']

# Special digit forms
SPECIAL_DIGIT_NAMES = ['ZeroForOddPowersOfFour', 'TwoForOddPowersOfFour', 'ThreeForOddPowersOfFour']


def _sort_key(name):
    """
    Return a tuple sort key for a Telugu glyph name.

    Key structure: (category, group_index, vowel_index, suffix_index, name)
    Categories:
      0 = Signs
      1 = Vowels
      2 = Vowel signs
      3 = Consonants (main)
      4 = Extra consonants / conjuncts
      5 = Digits
      6 = Special digits
      9 = Fallback
    """
    rest = name[1:]  # strip 't' prefix
    suffix = ''
    if '.' in rest:
        rest, suffix = rest.split('.', 1)

    suffix_idx = SUFFIX_ORDER.index(suffix) if suffix in SUFFIX_ORDER else len(SUFFIX_ORDER)

    # Signs
    if rest in SIGN_ORDER:
        return (0, SIGN_ORDER.index(rest), 0, suffix_idx, name)

    # Standalone vowels
    if rest in VOWEL_ORDER:
        return (1, VOWEL_ORDER.index(rest), 0, suffix_idx, name)

    # Vowel signs
    if rest in VOWEL_SIGN_ORDER:
        return (2, VOWEL_SIGN_ORDER.index(rest), 0, suffix_idx, name)

    # Consonants (try longest base first to avoid partial matches)
    for base_list, category in [(CONSONANT_ORDER, 3), (EXTRA_CONSONANTS, 4)]:
        for base in sorted(base_list, key=len, reverse=True):
            if rest.startswith(base):
                form = rest[len(base):]
                if form in VOWEL_FORMS:
                    base_idx = base_list.index(base)
                    vowel_idx = VOWEL_FORMS.index(form)
                    return (category, base_idx, vowel_idx, suffix_idx, name)

    # Digits (check before consonant sub-form fallback to avoid false matches)
    for i, d in enumerate(DIGIT_NAMES):
        if rest == d:
            return (5, i, 0, suffix_idx, name)

    # Special digit forms
    if rest in SPECIAL_DIGIT_NAMES:
        return (6, SPECIAL_DIGIT_NAMES.index(rest), 0, suffix_idx, name)

    # Reph special case
    if rest == 'Reph':
        return (3, CONSONANT_ORDER.index('R'), len(VOWEL_FORMS) + 1, suffix_idx, name)

    # Consonant cluster subscript forms (KRa, TRa, TtRa, etc.)
    for base in sorted(ALL_BASES, key=len, reverse=True):
        if rest.startswith(base):
            base_idx = ALL_BASES.index(base)
            category = 3 if base in CONSONANT_ORDER else 4
            if category == 3:
                base_idx = CONSONANT_ORDER.index(base)
            else:
                base_idx = EXTRA_CONSONANTS.index(base)
            return (category, base_idx, len(VOWEL_FORMS), suffix_idx, name)

    # Fallback
    return (9, 0, 0, suffix_idx, name)


def sort_telugu_glyphs(glyph_names):
    """Sort a list of Telugu glyph names in logical order."""
    return sorted(glyph_names, key=_sort_key)
