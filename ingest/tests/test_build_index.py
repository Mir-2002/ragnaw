from ingest.build_index import SPECIAL_TOKENS, pack


def words(text: str) -> int:
    return len(text.split())


def test_every_chunk_starts_with_header_and_fits():
    header = "Pikachu (Electric type)."
    pieces = ["one two three", "four five", "six seven eight nine"]
    max_tokens = 10  # budget: 10 - 2 special - 3 header = 5 words
    chunks = pack(header, pieces, words, max_tokens)
    assert chunks == [
        "Pikachu (Electric type). one two three four five",
        "Pikachu (Electric type). six seven eight nine",
    ]
    assert all(words(c) + SPECIAL_TOKENS <= max_tokens for c in chunks)


def test_splits_a_piece_longer_than_the_budget():
    chunks = pack("H.", ["a b c d e f g"], words, max_tokens=6)  # budget: 3 words
    assert chunks == ["H. a b c", "H. d e f", "H. g"]
