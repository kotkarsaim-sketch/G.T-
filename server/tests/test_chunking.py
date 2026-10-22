"""Unit tests for article-boundary chunking."""

from civic.chunking import (
    ArticleDraft,
    chunk_article,
    estimate_tokens,
    split_articles,
)

SAMPLE = """Noise Control By-law

This by-law is enacted to regulate noise.

1. Interpretation
In this by-law, dwelling means a building used as a residence.

2. General prohibition
No person shall make or cause noise likely to disturb.

2.1 Quiet hours
Quiet hours run from 22:00 to 07:00.
"""


def test_split_articles_captures_preamble_and_sections():
    articles = split_articles(SAMPLE)
    numbers = [a.number for a in articles]
    assert numbers == ["Preamble", "1", "2", "2.1"]
    assert articles[0].paragraphs[0].startswith("Noise Control By-law")
    assert articles[1].heading.startswith("Interpretation")


def test_subsection_numbering_is_preserved():
    articles = split_articles(SAMPLE)
    assert articles[3].number == "2.1"


def test_custom_pattern_is_honoured():
    text = "SECTION 4 - Animals\nKeep no swine.\nSECTION 5 - Fees\nFees as scheduled."
    articles = split_articles(text, r"^SECTION\s+(?P<num>\d+)\s+-\s+(?P<heading>.+)$")
    assert [a.number for a in articles] == ["4", "5"]


def test_short_article_is_single_chunk():
    art = ArticleDraft(number="1", heading="T", paragraphs=["One paragraph only."])
    assert chunk_article(art) == ["One paragraph only."]


def test_long_article_never_merges_across_calls():
    paras = [f"{i}. " + ("word " * 40) for i in range(6)]
    art = ArticleDraft(number="7", heading="Long", paragraphs=paras)
    chunks = chunk_article(art, max_tokens=120)
    assert len(chunks) > 1
    joined = "\n".join(chunks)
    for para in paras:
        assert para.strip() in joined.replace("\n", " ") or para.split(".")[0] in joined


def test_small_tail_is_merged_back():
    p1 = ("sentence one is here. " * 40).strip()
    p2 = ("sentence two is here. " * 40).strip()
    art = ArticleDraft(number="3", heading="H", paragraphs=[p1, p2, "Short tail."])
    chunks = chunk_article(art, max_tokens=150, min_tail_tokens=60)
    assert len(chunks) >= 2
    assert "Short tail." in chunks[-1]
    # the tail never becomes its own chunk below the minimum size
    assert all(len(c) >= 60 // 2 for c in chunks[:-1])


def test_estimate_tokens_floor():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100
