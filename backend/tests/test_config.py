from ragnaw.config import Settings


def test_providers_in_fallback_order():
    settings = Settings(_env_file=None, groq_api_key="g", gemini_api_key="m")
    assert [p.name for p in settings.llm_providers] == ["groq", "gemini"]


def test_unconfigured_providers_are_skipped():
    settings = Settings(_env_file=None, groq_api_key="", gemini_api_key="m")
    assert [p.name for p in settings.llm_providers] == ["gemini"]
