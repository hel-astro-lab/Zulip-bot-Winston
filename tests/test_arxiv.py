import datetime as dt
from pathlib import Path

from winston import arxiv

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_two_papers.atom"


def test_extract_ids_from_links_and_prefixes():
    text = (
        "see https://arxiv.org/abs/2406.01234v2 and http://arxiv.org/pdf/astro-ph/0601001 "
        "also arXiv:1234.5678, ar5iv.labs.arxiv.org/html/2101.00001 and "
        "export.arxiv.org/abs/2406.01234 again"
    )
    assert arxiv.extract_ids(text) == ["2406.01234", "astro-ph/0601001", "1234.5678", "2101.00001"]


def test_extract_ids_ignores_bare_numbers():
    assert arxiv.extract_ids("call me at 2406.01234 or 1234567") == []


def test_extract_ids_strips_version_and_trailing_punctuation():
    assert arxiv.extract_ids("(https://arxiv.org/abs/2406.01234v3).") == ["2406.01234"]
    assert arxiv.extract_ids("[paper](https://www.arxiv.org/pdf/2406.01234)") == ["2406.01234"]


def test_parse_feed_fixture():
    papers = arxiv.parse_feed(FIXTURE.read_text())
    assert [p.id for p in papers] == ["2406.01234", "astro-ph/0601001"]
    first = papers[0]
    assert first.title == "Achieving Tractable Minimax Optimal Regret in Average Reward MDPs"
    assert first.authors == ("Victor Boone", "Zihan Zhang")
    assert first.primary_category == "cs.LG"
    assert first.published == dt.date(2024, 6, 3)
    assert first.abs_url == "https://arxiv.org/abs/2406.01234"
    assert "\n" not in first.abstract and first.abstract.startswith("In recent years")
    assert papers[1].authors[0] == "Andrew Gould"


def test_parse_feed_skips_error_entries():
    feed = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<id>https://arxiv.org/api/errors#incorrect_id_format_for_x</id><title>Error</title>"
        "</entry></feed>"
    )
    assert arxiv.parse_feed(feed) == []


def test_format_paper_truncates_long_author_lists():
    paper = arxiv.Paper(
        id="2406.01234",
        title="A Title",
        authors=tuple(f"A{i}" for i in range(12)),
        abstract="The abstract.",
        primary_category="astro-ph.HE",
        published=dt.date(2024, 6, 3),
    )
    card = arxiv.format_paper(paper)
    assert card.startswith(
        "**A Title**\n[arXiv:2406.01234](https://arxiv.org/abs/2406.01234) · astro-ph.HE · 2024-06-03\n"
    )
    assert "A9, et al. (12 authors)" in card
    assert "A10" not in card
    assert card.endswith("```spoiler Abstract\nThe abstract.\n```")


def test_format_paper_short_author_list():
    paper = arxiv.Paper("1.1", "T", ("X", "Y"), "abs", "cs.LG", dt.date(2024, 1, 1))
    assert "\nX, Y\n" in arxiv.format_paper(paper)
