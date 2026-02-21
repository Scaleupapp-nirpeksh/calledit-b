"""Filter T20-only matches from Cricsheet data dump.

Usage: python -m scripts.filter_t20_data --source app/ml/raw_data --target app/ml/data
"""

import argparse
import json
import logging
import shutil
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Filter T20 matches from Cricsheet JSON data")
    parser.add_argument("--source", default="app/ml/raw_data", help="Source directory with all Cricsheet JSON files")
    parser.add_argument("--target", default="app/ml/data", help="Target directory for T20-only files")
    parser.add_argument("--clear-target", action="store_true", help="Clear target directory before copying")
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)

    if not source.exists():
        logger.error(f"Source directory not found: {source}")
        return

    target.mkdir(parents=True, exist_ok=True)

    if args.clear_target:
        existing = list(target.glob("*.json"))
        if existing:
            logger.info(f"Clearing {len(existing)} existing files from {target}")
            for f in existing:
                f.unlink()

    files = list(source.glob("*.json"))
    logger.info(f"Scanning {len(files)} files in {source}...")

    stats = Counter()
    tournaments = Counter()
    copied = 0

    for i, f in enumerate(files):
        try:
            with open(f) as fh:
                data = json.load(fh)

            info = data.get("info", {})
            match_type = info.get("match_type", "unknown")
            stats[match_type] += 1

            if match_type == "T20":
                event_name = info.get("event", {}).get("name", "Unknown Tournament")
                tournaments[event_name] += 1
                shutil.copy2(f, target / f.name)
                copied += 1
        except Exception:
            stats["error"] += 1

        if (i + 1) % 5000 == 0:
            logger.info(f"  Scanned {i + 1}/{len(files)} files ({copied} T20 so far)")

    logger.info(f"\n{'='*50}")
    logger.info("Match type breakdown:")
    for k, v in stats.most_common():
        logger.info(f"  {k:>10}: {v:,}")

    logger.info(f"\nT20 tournaments found:")
    for k, v in tournaments.most_common(20):
        logger.info(f"  {k}: {v}")

    logger.info(f"\nTotal T20 files copied to {target}: {copied:,}")


if __name__ == "__main__":
    main()
