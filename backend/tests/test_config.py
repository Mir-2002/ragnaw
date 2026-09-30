from ragnaw.config import Settings


def test_providers_in_fallback_order():
    settings = Settings(_env_file=None, groq_api_key="g", gemini_api_key="m")
    assert [p.name for p in settings.llm_providers] == ["groq", "groq-fallback", "gemini"]
    primary, fallback, _ = settings.llm_providers
    assert fallback.model == "qwen/qwen3.8-27b"
    assert fallback.extra_body == {"reasoning_format": "hidden"}
    # gpt-oss rejects reasoning_format; only the Qwen fallback sends it.
    assert primary.extra_body == {}


def test_unconfigured_providers_are_skipped():
    settings = Settings(_env_file=None, groq_api_key="", gemini_api_key="m")
    assert [p.name for p in settings.llm_providers] == ["gemini"]
    no_fallback = Settings(_env_file=None, groq_api_key="g", groq_fallback_model="")
    assert [p.name for p in no_fallback.llm_providers] == ["groq"]
