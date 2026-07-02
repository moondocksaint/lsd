"""Tests for lsd.utils — slugify() and CHARS_PER_TOKEN."""

from lsd.utils import CHARS_PER_TOKEN, slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_special_chars_stripped():
    assert slugify("Hello, World!") == "hello-world"


def test_underscores_become_hyphens():
    assert slugify("my_skill_name") == "my-skill-name"


def test_consecutive_hyphens_collapsed():
    assert slugify("foo--bar") == "foo-bar"
    assert slugify("foo - - bar") == "foo-bar"


def test_leading_trailing_hyphens_stripped():
    assert slugify("-leading") == "leading"
    assert slugify("trailing-") == "trailing"
    assert slugify("-both-") == "both"


def test_truncation_at_max_len():
    long = "a" * 100
    result = slugify(long, max_len=60)
    assert len(result) == 60


def test_truncation_no_trailing_hyphen():
    # slug that would end in a hyphen at the cut point
    text = "a" * 59 + "-extra"
    result = slugify(text, max_len=60)
    assert not result.endswith("-")


def test_agentskills_reserved_words_passthrough():
    # slugify itself doesn't enforce reserved words — that's cli.py's job
    assert slugify("anthropic-skill") == "anthropic-skill"


def test_chars_per_token_is_float():
    assert isinstance(CHARS_PER_TOKEN, float)
    assert CHARS_PER_TOKEN > 0


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  {t.__name__} ok")
    print(f"All {len(tests)} assertions passed.")
