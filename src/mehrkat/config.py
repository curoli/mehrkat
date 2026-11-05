import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    api_key: str = field(default="", repr=False)
    discovery_model: str = "gpt-4.1"
    summary_model: str = "gpt-4.1"
    lookback_hours: int = 48
    discovery_ttl: int = 900
    listings_path: Path = ROOT / "data/listings.csv"
    cache_path: Path = ROOT / ".cache/mehrkat.sqlite"

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            discovery_model=os.getenv("OPENAI_DISCOVERY_MODEL", "gpt-4.1"),
            summary_model=os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4.1"),
            lookback_hours=max(1, min(168, int(os.getenv("NEWS_LOOKBACK_HOURS", "48")))),
            discovery_ttl=max(1, int(os.getenv("DISCOVERY_CACHE_TTL_SECONDS", "900"))),
            listings_path=Path(os.getenv("LISTINGS_PATH", str(ROOT / "data/listings.csv"))),
            cache_path=Path(os.getenv("CACHE_PATH", str(ROOT / ".cache/mehrkat.sqlite"))),
        )
