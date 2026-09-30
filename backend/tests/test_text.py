from ragnaw.text import normalize


def test_normalize_folds_names_users_type_differently():
    assert normalize("Farfetch’d") == normalize("farfetch'd") == "farfetchd"
    assert normalize("Flabébé") == "flabebe"
    assert normalize("Mr. Mime") == "mr mime"
    assert normalize("Porygon-Z") == "porygon z"
