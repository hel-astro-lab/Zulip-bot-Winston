import datetime as dt
import json
from pathlib import Path

import pytest

from tests.conftest import dm_message, event
from winston import arxiv
from winston.features.digest import AuthorList, NameKey, abbreviate, name_key, normalize, tex_to_text

FIXTURE = Path(__file__).parent / "fixtures" / "astro-ph.rss"


def test_parse_listing_fixture():
    day, entries = arxiv.parse_listing(FIXTURE.read_text())
    assert day == dt.date(2026, 9, 18)
    assert [e.id for e in entries] == ["2609.19246", "2609.19235", "2609.17673", "2406.17234", "2504.11275", "2609.19187"]
    assert [e.announce_type for e in entries] == ["new", "new", "cross", "replace", "replace-cross", "new"]
    rubin = entries[0]
    assert rubin.title.startswith("Rubin LSST DP2")
    assert rubin.authors[2] == "\\v{Z}eljko Ivezi\\'c" and rubin.authors[3] == "Junais"
    assert len(rubin.authors) == 29
    assert entries[1].authors[1] == "Daniel L\\'opez-Cano"
    assert entries[1].categories == ("astro-ph.CO",)
    assert entries[1].abstract.startswith("High column density systems")
    assert entries[5].abs_url == "https://arxiv.org/abs/2609.19187"


@pytest.mark.parametrize(
    "tex, text",
    [
        ("Daniel L\\'opez-Cano", "Daniel Lopez-Cano"),
        ("\\v{Z}eljko Ivezi\\'c", "Zeljko Ivezic"),
        ("J. de la Cruz Rodr\\'iguez", "J. de la Cruz Rodriguez"),
        ("Bj\\o rn \\AA str\\\"om", "Bjorn Astrom"),
        ("Stra\\ss e", "Strasse"),
    ],
)
def test_tex_to_text(tex, text):
    assert tex_to_text(tex) == text


def test_normalize_folds_accents_periods_and_case():
    assert normalize("J. Nättilä") == "j nattila"
    assert normalize("Ø. Bjørn-Ålesund") == "o bjorn-alesund"
    assert normalize("\\v{Z}eljko  Ivezi\\'c") == "zeljko ivezic"


@pytest.mark.parametrize(
    "name, surname, given",
    [
        ("Joonas Nättilä", "nattila", ("joonas",)),
        ("J. Nättilä", "nattila", ("j",)),
        ("Nättilä", "nattila", ()),
        ("Nättilä, Joonas", "nattila", ("joonas",)),
        ("Nättilä, J.", "nattila", ("j",)),
        ("J. de la Cruz Rodr\\'iguez", "rodriguez", ("j", "de", "la", "cruz")),
        ("de la Cruz Rodríguez, J.", "rodriguez", ("j",)),
        ("M. Coleman Miller", "miller", ("m", "coleman")),
        ("R. Camilleri (DES Collaboration)", "camilleri", ("r",)),
        ("Junais", "junais", ()),
    ],
)
def test_name_key(name, surname, given):
    assert name_key(name) == NameKey(surname, given)


def test_name_key_empty():
    assert name_key("") is None and name_key(" , ") is None


def test_author_list_matching():
    authors = AuthorList.parse("# group\nJoonas Nättilä\nIvezić, Ž.  # colleague\nLópez-Cano\n\nK. Nättilä\n")
    assert [text for text, _ in authors.entries] == ["Joonas Nättilä", "Ivezić, Ž.", "López-Cano", "K. Nättilä"]
    assert authors.matches("J. Nattila") == "Joonas Nättilä"
    assert authors.matches("Joonas Nättilä") == "Joonas Nättilä"
    assert authors.matches("K. Nättilä") == "K. Nättilä"
    assert authors.matches("M. Nättilä") is None
    assert authors.matches("\\v{Z}eljko Ivezi\\'c") == "Ivezić, Ž."
    assert authors.matches("A. Ivezić") is None
    assert authors.matches("Daniel L\\'opez-Cano") == "López-Cano"
    assert authors.matches("X. López-Cano") == "López-Cano"
    assert authors.matches("Junais") is None
    assert AuthorList.parse("Miller, Coleman\n").matches("M. Coleman Miller") == "Miller, Coleman"
    assert AuthorList.parse("Miller, M. C.\n").matches("M. Coleman Miller") == "Miller, M. C."
    assert AuthorList.parse("Miller, M. C.\n").matches("Coleman Miller") is None
    assert AuthorList.parse("Miller, Coleman\n").matches("Andrew L. Miller") is None
    assert AuthorList.parse("Miller, Coleman\n").matches("C. Miller") == "Miller, Coleman"
    chen = AuthorList.parse("Chen, Alexander Y.\n")
    assert chen.matches("Y. Chen") is None and chen.matches("Alexander Y. Chen") and chen.matches("A. Y. Chen")
    kunz = AuthorList.parse("Kunz, Matthew\n")
    assert kunz.matches("Martin Kunz") is None and kunz.matches("M. Kunz") and kunz.matches("Matthew W. Kunz")


@pytest.mark.parametrize(
    "name, short",
    [
        ("Joonas Nättilä", "J. Nättilä"),
        ("J. Nättilä", "J. Nättilä"),
        ("Minh Ngoc Le", "M. N. Le"),
        ("Victor R. Soares da Silva", "V. R. Soares da Silva"),
        ("J. de la Cruz Rodríguez", "J. de la Cruz Rodríguez"),
        ("Ludwig van Beethoven", "L. van Beethoven"),
        ("Junais", "Junais"),
    ],
)
def test_abbreviate(name, short):
    assert abbreviate(name) == short


# ----- end to end -------------------------------------------------------------------------

DIGEST = {
    "enabled": True,
    "at": "09:00",
    "channel": "papers-test",
    "topic": "Winston's Daily Arxiv Highlights",
    "categories": ["astro-ph"],
    "authors": "authors.txt",
}

CLEAN_NAMES = {
    "2609.19246": ("Minh Ngoc Le", "Johan H. Knapen", "Željko Ivezić", "Junais") + tuple(f"Author {i}" for i in range(25)),
    "2609.19235": ("Victor R. Soares da Silva", "Daniel López-Cano", "L. Raul Abramo", "J. Chaves-Montero", "Francisco Maion"),
    "2609.17673": ("Shouyi Wang", "Fan Zou", "Elena Gallo", "Bin Luo", "W. N. Brandt", "Yuxuan Pang", "Tommaso Treu", "Others Many"),
}


@pytest.fixture
def digest_bot(make_bot, monkeypatch, tmp_path):
    (tmp_path / "authors.txt").write_text("Nättilä\nIvezić, Ž.\nDaniel López-Cano\nBrandt\nde la Cruz Rodríguez\n", encoding="utf-8")
    monkeypatch.setattr(arxiv, "fetch_listing", lambda category: arxiv.parse_listing(FIXTURE.read_text()))

    def fake_fetch_papers(ids):
        return [
            arxiv.Paper(i, "T", CLEAN_NAMES[i], "abs", "astro-ph", dt.date(2026, 9, 18)) for i in ids if i in CLEAN_NAMES
        ]

    monkeypatch.setattr(arxiv, "fetch_papers", fake_fetch_papers)
    return make_bot(digest=DIGEST)


def test_digest_posts_once_with_expected_lines(digest_bot, tmp_path):
    bot = digest_bot
    assert [f.name for f in bot.scheduled] == ["digest"]
    digest = next(f for f in bot.features if f.name == "digest")

    assert digest.post_digest(bot) == 3
    assert len(bot.client.sent) == 1
    post = bot.client.sent[0]
    assert post["to"] == "papers-test" and post["topic"] == "Winston's Daily Arxiv Highlights"
    lines = post["content"].split("\n")
    assert lines[0] == "**arXiv astro-ph, Friday 18 September 2026** — 3 papers by people on the list"
    assert lines[1] == (
        '- S. Wang, F. Zou, E. Gallo, …, **W. N. Brandt**, et al.: "Chandra Lensing-cluster Ultradeep Extragalactic '
        'Survey (CLUES) I: A 2 Ms Point-Source Catalog of the Abell 2744 Field" https://arxiv.org/abs/2609.17673'
    )
    assert lines[2] == (
        '- M. N. Le, J. H. Knapen, **Ž. Ivezić**, et al.: "Rubin LSST DP2 unveils almost-dark galaxies in the Virgo Cluster" '
        "https://arxiv.org/abs/2609.19246"
    )
    assert lines[3].startswith('- V. R. Soares da Silva, **D. López-Cano**, L. R. Abramo, J. Chaves-Montero, F. Maion: "Where the Forest')
    # the replaced paper by de la Cruz Rodríguez is not flagged
    assert "2406.17234" not in post["content"]

    assert digest.post_digest(bot) == 0
    assert len(bot.client.sent) == 1
    state = json.loads((tmp_path / "state.json").read_text())
    assert sorted(state["features"]["digest"]["posted"]) == ["2609.17673", "2609.19187", "2609.19235", "2609.19246"]


def test_digest_falls_back_to_feed_names(digest_bot, monkeypatch):
    def boom(ids):
        raise ConnectionError("api down")

    monkeypatch.setattr(arxiv, "fetch_papers", boom)
    digest = next(f for f in digest_bot.features if f.name == "digest")
    assert digest.post_digest(digest_bot) == 3
    content = digest_bot.client.sent[0]["content"]
    assert "**D. Lopez-Cano**" in content and "**Z. Ivezic**" in content


def test_digest_command_replies_with_count(digest_bot):
    digest_bot._on_event(event(dm_message(1, "digest")))
    assert digest_bot.client.sent[0]["to"] == "papers-test"
    assert digest_bot.client.sent[1] == {
        "type": "private", "to": [1], "content": "3 notable papers, filed in #**papers-test>Winston's Daily Arxiv Highlights**."
    }
    digest_bot._on_event(event(dm_message(2, "digest")))
    assert digest_bot.client.sent[2]["content"] == "Nothing to report. Even the arXiv has a rest frame."


def test_digest_header_template(make_bot, monkeypatch, tmp_path):
    (tmp_path / "authors.txt").write_text("Brandt\n")
    monkeypatch.setattr(arxiv, "fetch_listing", lambda category: arxiv.parse_listing(FIXTURE.read_text()))
    monkeypatch.setattr(arxiv, "fetch_papers", lambda ids: [])
    bot = make_bot(digest={**DIGEST, "header": "{papers} on {date} ({categories}, n={n})"})
    digest = next(f for f in bot.features if f.name == "digest")
    assert digest.post_digest(bot) == 1
    assert bot.client.sent[0]["content"].split("\n")[0] == "1 paper on Friday 18 September 2026 (astro-ph, n=1)"


def test_digest_with_empty_author_list_posts_nothing(make_bot, monkeypatch, tmp_path):
    (tmp_path / "authors.txt").write_text("# nobody yet\n")
    monkeypatch.setattr(arxiv, "fetch_listing", lambda category: arxiv.parse_listing(FIXTURE.read_text()))
    bot = make_bot(digest=DIGEST)
    digest = next(f for f in bot.features if f.name == "digest")
    assert digest.post_digest(bot) == 0 and bot.client.sent == []
