"""Language codes (ISO 639-3, as iptv-org uses) and their English names, and country codes by English name.

Entries store codes; the M3U writer shows names, the de facto `tvg-language` format ("English;Spanish").
The full list comes from iptv-org's languages.json during a build (see `load`); the built-in list below covers
offline runs and tests.
"""

from __future__ import annotations

NO_DIALOGUE = "zxx"  # ISO 639 "No linguistic content": silent films, dialogue-free animation

_BUILTIN = {
    "ara": "Arabic", "ben": "Bengali", "ces": "Czech", "dan": "Danish", "deu": "German", "ell": "Greek",
    "eng": "English", "fas": "Persian", "fin": "Finnish", "fra": "French", "heb": "Hebrew", "hin": "Hindi",
    "hun": "Hungarian", "ind": "Indonesian", "ita": "Italian", "jpn": "Japanese", "kor": "Korean",
    "nld": "Dutch", "nor": "Norwegian", "pol": "Polish", "por": "Portuguese", "ron": "Romanian", "rus": "Russian",
    "spa": "Spanish", "swe": "Swedish", "tha": "Thai", "tur": "Turkish", "ukr": "Ukrainian", "urd": "Urdu",
    "vie": "Vietnamese", "zho": "Chinese", NO_DIALOGUE: "No linguistic content",
}

# ISO 639-1 (two-letter) and 639-2/B codes that metadata often uses instead of 639-3.
_ALIASES = {
    "ar": "ara", "bn": "ben", "cs": "ces", "cze": "ces", "da": "dan", "de": "deu", "ger": "deu", "el": "ell",
    "gre": "ell", "en": "eng", "fa": "fas", "per": "fas", "fi": "fin", "fr": "fra", "fre": "fra", "he": "heb",
    "hi": "hin", "hu": "hun", "id": "ind", "it": "ita", "ja": "jpn", "jap": "jpn", "ko": "kor", "nl": "nld",
    "dut": "nld", "no": "nor", "nb": "nor", "pl": "pol", "pt": "por", "ro": "ron", "rum": "ron", "ru": "rus",
    "es": "spa", "sv": "swe", "th": "tha", "tr": "tur", "uk": "ukr", "ur": "urd", "vi": "vie", "zh": "zho",
    "chi": "zho", "silent": NO_DIALOGUE, "none": NO_DIALOGUE,
}

NAMES: dict[str, str] = dict(_BUILTIN)
_BY_NAME: dict[str, str] = {v.lower(): k for k, v in _BUILTIN.items()}


def load(entries: list[dict]) -> None:
    """Use iptv-org's language list ([{"code": "eng", "name": "English"}, ...]) for names and lookups."""
    for item in entries:
        NAMES[item["code"]] = item["name"]
        _BY_NAME.setdefault(item["name"].lower(), item["code"])


def name(code: str) -> str:
    return NAMES.get(code, code)


def normalise(value: str | None) -> str | None:
    """An ISO 639-3 code for a code or English name as metadata writes it ("en", "fre", "English", "eng")."""
    if not value:
        return None
    v = value.strip().lower().removesuffix(" language")
    if v in NAMES:
        return v
    return _ALIASES.get(v) or _BY_NAME.get(v)


def normalise_all(values) -> list[str]:
    """Codes for a value or list of values, which may themselves be ';' or ',' separated; unknowns dropped."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values:
        for part in str(value).replace(";", ",").split(","):
            code = normalise(part)
            if code and code not in out:
                out.append(code)
    return out


# --- countries ------------------------------------------------------------------------------------------------

_COUNTRIES = {
    "united states": "US", "usa": "US", "united kingdom": "GB", "great britain": "GB", "england": "GB",
    "france": "FR", "germany": "DE", "italy": "IT", "spain": "ES", "japan": "JP", "russia": "RU", "canada": "CA",
    "mexico": "MX", "netherlands": "NL", "sweden": "SE", "denmark": "DK", "india": "IN", "china": "CN",
}


def country_code(code: str) -> str:
    """ISO 3166-1 alpha-2 for a country code as iptv-org writes it: the United Kingdom is UK there, GB in ISO."""
    code = code.upper()
    return "GB" if code == "UK" else code


def load_countries(entries: list[dict]) -> None:
    """Use iptv-org's country list ([{"code": "US", "name": "United States"}, ...]) for lookups by name."""
    for item in entries:
        _COUNTRIES.setdefault(item["name"].lower(), country_code(item["code"]))


def country(name: str) -> str | None:
    """ISO 3166-1 alpha-2 code for an English country name ("the United States" -> "US")."""
    return _COUNTRIES.get(name.strip().lower().removeprefix("the "))
