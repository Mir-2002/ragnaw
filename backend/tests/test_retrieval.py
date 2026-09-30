import pytest


def top_titles(index, query, k=2):
    return [h.doc["title"] for h in index.search(query, k=k)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("pokemon that stores electricity in its cheeks", "Pikachu"),
        ("ability that makes it immune to ground moves", "Levitate"),
        ("ghost pokemon that hides under a cloth", "Mimikyu"),
        # Exact names: dense search alone ranked Sirfetch'd first.
        ("Farfetch'd", "Farfetch’d"),
        ("what does mr mime do", "Mr. Mime"),
        ("Flabebe", "Flabébé"),
        # Typos
        ("tell me about pikachoo", "Pikachu"),
        ("bulbsaur", "Bulbasaur"),
    ],
)
def test_top_result(index, query, expected):
    assert top_titles(index, query)[0] == expected


def test_common_words_are_not_typo_corrected_into_names(index):
    # "ground" is one edit from the move Round.
    assert "round" not in index.mentioned_titles("immune to ground moves")


def test_caps_chunks_per_entity(index):
    titles = top_titles(index, "pikachu", k=5)
    assert titles.count("Pikachu") <= 2


def test_filters_by_kind(index):
    hits = index.search("burns the target", k=5, kinds={"move"})
    assert hits and all(h.doc["kind"] == "move" for h in hits)
