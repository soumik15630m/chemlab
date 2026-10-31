"""Download a pinned optional CSV stock and register it without changing run defaults."""

from __future__ import annotations

import argparse
from pathlib import Path

from chemlab.evidence.stock_sources import StockCSVSpec, fetch_verified, register_csv_stock
from chemlab.records import canonical_bytes
from chemlab.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=Path("var"))
    parser.add_argument("--spec", type=Path, default=Path("configs/stocks/ursa-bbs-v1.json"))
    parser.add_argument("--alias", default="ursa-bbs-v1-identity-v1")
    parser.add_argument("--downloads", type=Path, default=Path("var/stock-downloads"))
    args = parser.parse_args()
    spec = StockCSVSpec.model_validate_json(args.spec.read_text(encoding="ascii"))
    directory = args.downloads / spec.sha256
    raw = fetch_verified(spec.url, directory / "stock.csv", spec.sha256, spec.size)
    card = fetch_verified(spec.card_url, directory / "dataset-card.md", spec.card_sha256)
    result = register_csv_stock(Store(args.store), args.alias, raw, card, spec)
    print(canonical_bytes(result).decode("ascii"))


if __name__ == "__main__":
    main()
