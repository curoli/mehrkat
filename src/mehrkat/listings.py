"""Local venue-level directory; no network during lookup."""
import csv
import json
from pathlib import Path

from .models import Listing

# Independently curated illustrative facts, not an upstream data snapshot.
SAMPLE = [
    Listing(listing_key="NASDAQ:AAPL", ticker="AAPL", exchange="NASDAQ", name="Apple Inc.", country="United States", sector="Technology", aliases=["Apple"], isin="US0378331005"),
    Listing(listing_key="NASDAQ:MSFT", ticker="MSFT", exchange="NASDAQ", name="Microsoft Corporation", country="United States", sector="Technology", aliases=["Microsoft"], isin="US5949181045"),
    Listing(listing_key="XETRA:SAP", ticker="SAP", exchange="XETRA", name="SAP SE", country="Germany", sector="Technology", aliases=["SAP"], isin="DE0007164600"),
    Listing(listing_key="NYSE:SAP", ticker="SAP", exchange="NYSE", name="SAP SE", country="Germany", sector="Technology", aliases=["SAP", "SAP ADR"]),
]


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def parse_aliases(value: str) -> list[str]:
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
            raise ValueError("Aliases must be a list of strings")
        return parsed
    return [part.strip() for part in value.split("|") if part.strip()]


class Directory:
    def __init__(self, path: Path):
        self.status = "Demonstrative sample directory (4 listings; not a market database)"
        self.rows = SAMPLE
        if path.exists():
            try:
                with path.open(encoding="utf-8-sig", newline="") as source:
                    rows = [Listing(
                        listing_key=r["listing_key"], ticker=r["ticker"], exchange=r["exchange"],
                        name=r["name"], country=r.get("country", ""),
                        sector=r.get("stock_sector", ""), aliases=parse_aliases(r.get("aliases", "")),
                        isin=r.get("isin") or None,
                    ) for r in csv.DictReader(source) if r.get("asset_type") == "Stock"]
                if not rows:
                    raise ValueError("No stock listings")
                self.rows = rows
                self.status = f"Local imported directory ({len(rows)} stock listings)"
            except (ValueError, KeyError, OSError):
                self.status += "; import unavailable or invalid"
        self.by_key = {row.listing_key: row for row in self.rows}

    def search(self, query: str) -> list[Listing]:
        q = normalize(query)
        if not q:
            return []
        matches = []
        for row in self.rows:
            fields = [normalize(row.name), *(normalize(a) for a in row.aliases)]
            ticker = normalize(row.ticker)
            rank = 0 if ticker == q else 1 if any(f.startswith(q) for f in fields) else 2
            if q in ticker or any(q in f for f in fields):
                matches.append((rank, row.name, row.exchange, row))
        return [m[3] for m in sorted(matches, key=lambda m: m[:3])[:25]]
