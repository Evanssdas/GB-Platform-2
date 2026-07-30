"""Standalone ENTSO-E collector command.

Usage:
    python -m gb_platform_v2.entsoe_cli --start ... --end ...
"""

from __future__ import annotations

import argparse

from .entsoe_collection import collect_entsoe_markets


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect ENTSO-E GB neighbouring-market data")
    parser.add_argument("--config", default="config/entsoe.yaml")
    parser.add_argument("--start", required=True, help="UTC start, e.g. 2026-07-01T00:00Z")
    parser.add_argument("--end", required=True, help="UTC exclusive end")
    parser.add_argument("--output", default="data/parsed/entsoe")
    args = parser.parse_args()
    paths = collect_entsoe_markets(args.config, args.start, args.end, args.output)
    print({name: str(path) for name, path in paths.items()})


if __name__ == "__main__":
    main()
