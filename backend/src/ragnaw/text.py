import re
import unicodedata

_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_DROP = re.compile(r"['.]")  # Farfetch'd -> farfetchd, Mr. Mime -> mr mime
_SEPARATORS = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Fold text for matching: accents, curly quotes, case and punctuation.

    PokeAPI names use curly apostrophes and accents (Farfetch’d, Flabébé); users type
    neither. Hyphens and other separators become spaces (Porygon-Z -> porygon z).
    """
    text = unicodedata.normalize("NFKD", text.translate(_QUOTES))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return _SEPARATORS.sub(" ", _DROP.sub("", text)).strip()
