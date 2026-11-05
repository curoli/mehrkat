import csv

import pytest

from mehrkat.listings import Directory, parse_aliases


@pytest.mark.parametrize("query,ticker", [(" aApL ", "AAPL"), ("apple inc.", "AAPL"), ("microsoft", "MSFT"), (" sap   se ", "SAP"), ("SAP ADR", "SAP")])
def test_search(settings, query, ticker):
    rows = Directory(settings.listings_path).search(query)
    assert rows and rows[0].ticker == ticker


def test_ambiguous_listings_remain_separate(settings):
    directory = Directory(settings.listings_path)
    rows = directory.search("SAP")
    assert {r.exchange for r in rows} == {"XETRA", "NYSE"}
    assert len({r.listing_key for r in rows}) == 2
    assert directory.search("") == []


def test_import_and_stock_filter(settings):
    path = settings.listings_path
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["listing_key", "name", "ticker", "exchange", "asset_type", "aliases", "stock_sector"])
        writer.writeheader()
        writer.writerows([
            dict(listing_key="X:A", name="Ä company", ticker="A", exchange="X", asset_type="Stock", aliases='["Alias"]', stock_sector="Technology"),
            dict(listing_key="X:B", name="Fund", ticker="B", exchange="X", asset_type="ETF"),
        ])
    directory = Directory(path)
    assert len(directory.rows) == 1
    assert directory.search("alias")[0].sector == "Technology"
    assert directory.search("ä")[0].listing_key == "X:A"


def test_invalid_import_falls_back(settings):
    settings.listings_path.write_text("bad,data\ninvalid,row")
    assert "sample" in Directory(settings.listings_path).status


def test_aliases_do_not_evaluate_code():
    assert parse_aliases("one|two") == ["one", "two"]
    with pytest.raises(ValueError):
        parse_aliases('[{"not": "a string"}]')
