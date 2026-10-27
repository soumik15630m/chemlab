"""Download official, licensed checkpoints without replacing existing artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


def fetch(url: str, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    request = Request(url, headers={"User-Agent": "ChemLab/0.1"})
    with urlopen(request, timeout=120) as response, partial.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    partial.rename(destination)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "models"
    root.mkdir(exist_ok=True)
    for article_id, name in [(31150195, "generator"), (32994914, "checker")]:
        metadata_path = root / f"{name}-source.json"
        fetch(f"https://api.figshare.com/v2/articles/{article_id}", metadata_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata["license"]["name"] != "MIT":
            raise ValueError("Checkpoint license changed; inspect before proceeding")
        destination = root / name
        if destination.exists():
            print(f"Preserving existing {name} directory", flush=True)
            continue
        archive = metadata["files"][0]
        zip_path = root / archive["name"]
        print(f"Downloading {name}: {archive['size']} bytes", flush=True)
        fetch(archive["download_url"], zip_path)
        checksum = hashlib.md5(usedforsecurity=False)
        with zip_path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                checksum.update(block)
        if (
            zip_path.stat().st_size != archive["size"]
            or checksum.hexdigest() != archive["computed_md5"]
        ):
            raise ValueError("Official archive integrity check failed")
        staging = root / f"{name}-extracting"
        if staging.exists():
            raise FileExistsError("Prior extraction is incomplete; preserve it for inspection")
        staging.mkdir()
        with zipfile.ZipFile(zip_path) as archive_file:
            for member in archive_file.infolist():
                path = (staging / member.filename).resolve()
                if not path.is_relative_to(staging.resolve()):
                    raise ValueError("Unsafe archive path")
            archive_file.extractall(staging)
        staging.rename(destination)
        print(f"Extracted {name}", flush=True)
    stock = root / "paroutes-n1-stock.txt"
    fetch("https://zenodo.org/records/7341155/files/stock_n1.txt?download=1", stock)
    print(f"Stock snapshot downloaded: {stock}", flush=True)
    metadata_path = root / "openretro-train-source.json"
    fetch(
        "https://api.github.com/repos/coleygroup/openretro/contents/data/USPTO_50k/raw/raw_train.csv",
        metadata_path,
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["sha"] != "7f5f61c901d637061dc77ab785e570d9c0d14c22":
        raise ValueError("Public training corpus changed; inspect and register a new version")
    fetch(metadata["download_url"], root / "openretro-train.csv")
    print("Public training corpus downloaded; ingestion verifies its Git blob", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
