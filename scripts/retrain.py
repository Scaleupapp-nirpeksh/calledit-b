"""CalledIt — Retraining Pipeline Orchestrator.

Steps:
1. Export completed match data from MongoDB → Cricsheet-format JSON
2. Combine with static Cricsheet training data
3. Train new models
4. Evaluate new models
5. Archive old models and deploy new ones

Usage: python -m scripts.retrain [--include-live] [--data-dir app/ml/data]
"""

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "app" / "ml" / "models"
ARCHIVE_DIR = BASE_DIR / "app" / "ml" / "model_archive"
LIVE_EXPORT_DIR = BASE_DIR / "exports" / "live_matches"


def archive_current_models():
    """Archive current models before overwriting."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / timestamp
    archive_path.mkdir(parents=True, exist_ok=True)

    for model_file in MODEL_DIR.glob("*.json"):
        dest = archive_path / model_file.name
        shutil.copy2(model_file, dest)
        logger.info(f"  Archived {model_file.name} → {dest}")

    logger.info(f"Models archived to {archive_path}")
    return archive_path


def export_live_data():
    """Export completed matches from MongoDB."""
    logger.info("Step 1: Exporting live match data from MongoDB...")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.export_live_data",
         "--output-dir", str(LIVE_EXPORT_DIR)],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        logger.error(f"Export failed: {result.stderr}")
        return False
    logger.info(result.stdout.strip())
    return True


def combine_data(data_dir: Path):
    """Copy live exported data into the training data directory."""
    if not LIVE_EXPORT_DIR.exists():
        logger.info("No live export data to combine")
        return 0

    live_files = list(LIVE_EXPORT_DIR.glob("*.json"))
    if not live_files:
        logger.info("No live match files to add")
        return 0

    data_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in live_files:
        dest = data_dir / f.name
        if not dest.exists():
            shutil.copy2(f, dest)
            copied += 1

    logger.info(f"Step 2: Added {copied} live match files to training data ({len(live_files)} total available)")
    return copied


def train_models(data_dir: Path):
    """Run training script."""
    logger.info("Step 3: Training new models...")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.train_model",
         "--data-dir", str(data_dir)],
        capture_output=True, text=True, cwd=str(BASE_DIR),
        timeout=600,
    )
    print(result.stdout)
    if result.returncode != 0:
        logger.error(f"Training failed: {result.stderr}")
        return False
    logger.info("Training complete")
    return True


def evaluate_models(data_dir: Path):
    """Run evaluation script."""
    logger.info("Step 4: Evaluating new models...")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_models",
         "--data-dir", str(data_dir)],
        capture_output=True, text=True, cwd=str(BASE_DIR),
        timeout=600,
    )
    print(result.stdout)
    if result.returncode != 0:
        logger.error(f"Evaluation failed: {result.stderr}")
        return False
    logger.info("Evaluation complete")
    return True


def main():
    parser = argparse.ArgumentParser(description="CalledIt ML Retraining Pipeline")
    parser.add_argument("--data-dir", default=str(BASE_DIR / "app" / "ml" / "data"),
                        help="Training data directory (Cricsheet JSON files)")
    parser.add_argument("--include-live", action="store_true",
                        help="Export and include live match data from MongoDB")
    parser.add_argument("--skip-archive", action="store_true",
                        help="Skip archiving current models")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    print("=" * 70)
    print("  CalledIt ML Retraining Pipeline")
    print(f"  Data directory: {data_dir}")
    print(f"  Include live data: {args.include_live}")
    print("=" * 70)

    # Step 0: Archive
    if not args.skip_archive:
        logger.info("Step 0: Archiving current models...")
        archive_current_models()

    # Step 1-2: Export + combine live data
    if args.include_live:
        if not export_live_data():
            logger.error("Aborting: live data export failed")
            return 1
        combine_data(data_dir)
    else:
        logger.info("Skipping live data export (use --include-live to include)")

    # Step 3: Train
    if not train_models(data_dir):
        logger.error("Aborting: training failed")
        return 1

    # Step 4: Evaluate
    if not evaluate_models(data_dir):
        logger.warning("Evaluation failed — models were still saved, review manually")
        return 1

    print("\n" + "=" * 70)
    print("  RETRAINING COMPLETE")
    print("  New models deployed to app/ml/models/")
    print("  Restart the server to load the new models")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
