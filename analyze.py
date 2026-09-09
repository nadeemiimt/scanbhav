from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer import analyze_stock


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a stock JSON document against your book RAG.")
    parser.add_argument("input", type=Path, help="path to a stock JSON file")
    args = parser.parse_args()
    with args.input.open() as file:
        stock = json.load(file)
    print(json.dumps(analyze_stock(stock), indent=2))


if __name__ == "__main__":
    main()
