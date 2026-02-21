"""CalledIt ML Training Pipeline

Trains two XGBoost models from Cricsheet historical data:
1. Ball outcome classifier (7 classes: dot, 1, 2, 3, 4, 6, wicket)
2. Win probability classifier (binary: batting team wins)

Saves models as native XGBoost JSON + team encoder for inference.

Usage: python -m scripts.train_model [--data-dir app/ml/data]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
MODEL_DIR = Path("app/ml/models")

# Feature columns for ball outcome model (must match feature_engineering.py)
BALL_FEATURES = [
    "innings", "over", "ball_in_over", "score", "wickets",
    "run_rate", "balls_remaining", "phase",
    "last_outcome_1", "last_outcome_2", "last_outcome_3",
    "batter_runs_so_far", "batter_balls_faced", "batter_strike_rate", "is_new_batter",
    "bowler_economy_so_far", "bowler_wickets_so_far", "bowler_balls_bowled",
    "partnership_runs", "partnership_balls",
    "is_batting_team_toss_winner", "toss_decision",
]


def train_ball_outcome_model(df: pd.DataFrame) -> None:
    """Train XGBoost multi-class classifier for ball outcomes."""
    logger.info("=== Training Ball Outcome Model ===")

    X = df[BALL_FEATURES].values
    y = df["label"].values

    logger.info(f"Dataset: {len(X)} samples, {len(BALL_FEATURES)} features, {len(np.unique(y))} classes")
    logger.info(f"Class distribution:\n{pd.Series(y).value_counts().sort_index()}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Compute balanced sample weights to fix class imbalance
    sample_weights = compute_sample_weight("balanced", y_train)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=7,
        learning_rate=0.05,
        objective="multi:softprob",
        num_class=7,
        eval_metric="mlogloss",
        tree_method="hist",
        random_state=42,
        n_jobs=-1,
        min_child_weight=5,
        subsample=0.8,
        colsample_bytree=0.8,
    )

    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    # Evaluate
    accuracy = model.score(X_test, y_test)
    logger.info(f"Test accuracy: {accuracy:.4f}")

    # Save as native XGBoost JSON
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    native_path = MODEL_DIR / "ball_outcome_model.json"
    model.save_model(str(native_path))
    logger.info(f"Ball model saved to {native_path}")


def train_win_probability_model(data_dir: Path) -> None:
    """Train XGBoost binary classifier for win probability."""
    logger.info("=== Training Win Probability Model ===")

    # Team encoder — persisted for inference
    team_encoder: dict[str, int] = {}
    next_team = 0

    def encode_team(name: str) -> int:
        nonlocal next_team
        if name not in team_encoder:
            team_encoder[name] = next_team
            next_team += 1
        return team_encoder[name]

    rows = []
    files = list(data_dir.glob("*.json"))
    logger.info(f"Processing {len(files)} match files for win probability...")

    for i, filepath in enumerate(files):
        try:
            with open(filepath) as f:
                match = json.load(f)

            info = match.get("info", {})
            outcome = info.get("outcome", {})
            winner = outcome.get("winner")
            if not winner:
                continue

            teams = info.get("teams", [])
            if len(teams) != 2:
                continue

            # Toss data
            toss = info.get("toss", {})
            toss_winner = toss.get("winner", "")
            toss_decision_val = 0 if toss.get("decision") == "bat" else 1

            for innings_idx, innings in enumerate(match.get("innings", []), start=1):
                batting_team = innings.get("team", "")
                bowling_team = teams[1] if batting_team == teams[0] else teams[0]
                batting_team_wins = int(batting_team == winner)
                is_batting_team_toss_winner = int(batting_team == toss_winner)

                batting_team_id = encode_team(batting_team)
                bowling_team_id = encode_team(bowling_team)

                score = 0
                wickets = 0
                balls = 0
                target = 0
                recent_wickets: list[int] = []  # ball numbers where wickets fell

                # For 2nd innings, calculate target from 1st innings
                if innings_idx == 2 and len(match.get("innings", [])) >= 1:
                    first_innings = match["innings"][0]
                    for od in first_innings.get("overs", []):
                        for d in od.get("deliveries", []):
                            target += d.get("runs", {}).get("total", 0)
                    target += 1

                for over_data in innings.get("overs", []):
                    over_num = over_data["over"]
                    for delivery in over_data.get("deliveries", []):
                        runs = delivery.get("runs", {})
                        total_runs = runs.get("total", 0)

                        extras_detail = delivery.get("extras", {})
                        is_wide = "wides" in extras_detail
                        is_noball = "noballs" in extras_detail

                        score += total_runs
                        if not is_wide and not is_noball:
                            balls += 1

                        has_wicket = "wickets" in delivery
                        if has_wicket:
                            wickets += 1
                            recent_wickets.append(balls)

                        overs = balls / 6
                        run_rate = (score / overs) if overs > 0 else 0.0
                        balls_remaining = 120 - balls

                        required_rate = 0.0
                        if innings_idx == 2 and target > 0 and balls_remaining > 0:
                            runs_needed = target - score
                            overs_rem = balls_remaining / 6
                            required_rate = runs_needed / overs_rem if overs_rem > 0 else 99.0

                        if over_num < 6:
                            phase = 0
                        elif over_num < 14:
                            phase = 1
                        else:
                            phase = 2

                        # Wickets in last 5 overs (30 balls)
                        wkts_last_5 = sum(1 for wb in recent_wickets if wb > balls - 30)

                        # Sample every 6th delivery
                        if balls % 6 == 0 and balls > 0:
                            rows.append({
                                "innings": innings_idx,
                                "score": score,
                                "wickets": wickets,
                                "overs": round(overs, 1),
                                "run_rate": round(run_rate, 2),
                                "target": target,
                                "required_rate": round(required_rate, 2),
                                "balls_remaining": balls_remaining,
                                "phase": phase,
                                "batting_team_id": batting_team_id,
                                "bowling_team_id": bowling_team_id,
                                "is_batting_team_toss_winner": is_batting_team_toss_winner,
                                "toss_decision": toss_decision_val,
                                "wickets_in_last_5_overs": wkts_last_5,
                                "label": batting_team_wins,
                            })
        except Exception as e:
            logger.warning(f"Skipping {filepath.name}: {e}")

        if (i + 1) % 500 == 0:
            logger.info(f"  Processed {i + 1}/{len(files)} files ({len(rows)} samples)")

    df = pd.DataFrame(rows)
    logger.info(f"Win probability dataset: {len(df)} samples")
    logger.info(f"Teams encoded: {len(team_encoder)}")

    if len(df) < 100:
        logger.error("Not enough data for win probability model")
        return

    X = df.drop("label", axis=1).values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=42,
        n_jobs=-1,
        min_child_weight=5,
        subsample=0.8,
        colsample_bytree=0.8,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    accuracy = model.score(X_test, y_test)
    logger.info(f"Win probability test accuracy: {accuracy:.4f}")

    # Save model
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    native_path = MODEL_DIR / "win_probability_model.json"
    model.save_model(str(native_path))
    logger.info(f"Win probability model saved to {native_path}")

    # Save team encoder for inference
    encoder_path = MODEL_DIR / "team_encoder.json"
    with open(encoder_path, "w") as f:
        json.dump(team_encoder, f, indent=2)
    logger.info(f"Team encoder saved to {encoder_path} ({len(team_encoder)} teams)")


def main():
    parser = argparse.ArgumentParser(description="Train CalledIt ML models")
    parser.add_argument("--data-dir", default="app/ml/data", help="Directory with Cricsheet JSON files")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    logger.info("CalledIt ML Training Pipeline")
    logger.info(f"Data directory: {data_dir}")

    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)

    json_files = list(data_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} match files")

    if not json_files:
        logger.error("No JSON files found in data directory")
        sys.exit(1)

    # 1. Train ball outcome model
    sys.path.insert(0, ".")
    from app.ml.feature_engineering import TrainingFeatureExtractor

    extractor = TrainingFeatureExtractor()
    df = extractor.extract_from_directory(data_dir)
    train_ball_outcome_model(df)

    # 2. Train win probability model
    train_win_probability_model(data_dir)

    logger.info("Training complete!")


if __name__ == "__main__":
    main()
