"""Explicit local-only download. Review upstream source terms before use."""
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/adanos-software/free-ticker-database/main/data/listings.csv"


def main():
    with urlopen(URL, timeout=60) as response:
        raw = response.read(100_000_001)
    if len(raw) > 100_000_000:
        raise SystemExit("Download exceeds 100 MB limit")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"listing_key", "ticker", "exchange", "name", "asset_type"} <= set(reader.fieldnames or []):
        raise SystemExit("Unexpected upstream schema; existing directory preserved")
    path = Path("data")
    path.mkdir(exist_ok=True)
    temporary = path / "listings.csv.tmp"
    temporary.write_bytes(raw)
    temporary.replace(path / "listings.csv")
    (path / "provenance.json").write_text(json.dumps({
        "url": URL, "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "rights": "Local use only; review upstream source-specific terms before redistribution",
    }, indent=2))
    print("Downloaded local directory. Restart mehrkat to load it.")


if __name__ == "__main__":
    main()
