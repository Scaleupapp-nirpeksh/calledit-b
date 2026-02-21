"""CalledIt ML Model Evaluation Script

Evaluates both trained XGBoost models:
1. Ball outcome classifier (7-class)
2. Win probability classifier (binary)

Produces: accuracy, per-class sensitivity/specificity, classification report, confusion matrix.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    multilabel_confusion_matrix,
)
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "app" / "ml" / "models"
BALL_MODEL_PATH = MODEL_DIR / "ball_outcome_model.json"
WIN_MODEL_PATH = MODEL_DIR / "win_probability_model.json"

# Must match feature_engineering.py BALL_FEATURES exactly
BALL_FEATURES = [
    "innings", "over", "ball_in_over", "score", "wickets",
    "run_rate", "balls_remaining", "phase",
    "last_outcome_1", "last_outcome_2", "last_outcome_3",
    "batter_runs_so_far", "batter_balls_faced", "batter_strike_rate", "is_new_batter",
    "bowler_economy_so_far", "bowler_wickets_so_far", "bowler_balls_bowled",
    "partnership_runs", "partnership_balls",
    "is_batting_team_toss_winner", "toss_decision",
]

OUTCOME_LABELS = {"dot": 0, "1": 1, "2": 2, "3": 3, "4": 4, "6": 5, "wicket": 6}
OUTCOME_NAMES = {v: k for k, v in OUTCOME_LABELS.items()}

# Must match feature_engineering.py WIN_FEATURES exactly
WIN_FEATURES = [
    "innings", "score", "wickets", "overs",
    "run_rate", "target", "required_rate",
    "balls_remaining", "phase",
    "batting_team_id", "bowling_team_id",
    "is_batting_team_toss_winner", "toss_decision",
    "wickets_in_last_5_overs",
]


# ---------------------------------------------------------------------------
# Helper: per-class sensitivity & specificity from multilabel confusion matrix
# ---------------------------------------------------------------------------
def per_class_sensitivity_specificity(y_true, y_pred, class_names):
    """Compute per-class sensitivity (recall) and specificity."""
    mcm = multilabel_confusion_matrix(y_true, y_pred)
    print("\n" + "=" * 70)
    print("PER-CLASS SENSITIVITY (RECALL) & SPECIFICITY")
    print("=" * 70)
    print(f"{'Class':<12} {'Support':>8} {'Sensitivity':>13} {'Specificity':>13}")
    print("-" * 50)
    for i, (name, cm) in enumerate(zip(class_names, mcm)):
        tn, fp, fn, tp = cm.ravel()
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        support = tp + fn
        print(f"{name:<12} {support:>8d} {sensitivity:>13.4f} {specificity:>13.4f}")
    print("-" * 50)


# ---------------------------------------------------------------------------
# 1. BALL OUTCOME MODEL EVALUATION
# ---------------------------------------------------------------------------
def evaluate_ball_outcome_model(data_dir: Path):
    print("\n")
    print("#" * 70)
    print("#  BALL OUTCOME MODEL EVALUATION (7-class)")
    print("#" * 70)

    sys.path.insert(0, str(BASE_DIR))
    from app.ml.feature_engineering import TrainingFeatureExtractor

    extractor = TrainingFeatureExtractor()
    logger.info("Extracting features from match data (ball outcome)...")
    df = extractor.extract_from_directory(data_dir)

    X = df[BALL_FEATURES].values
    y = df["label"].values

    print(f"\nTotal samples: {len(X)}")
    print(f"Features:      {len(BALL_FEATURES)}")
    print(f"Classes:       {len(np.unique(y))}")
    print(f"\nClass distribution:")
    for cls_id in sorted(np.unique(y)):
        count = int((y == cls_id).sum())
        pct = 100.0 * count / len(y)
        print(f"  {OUTCOME_NAMES.get(cls_id, str(cls_id)):<8} (label {cls_id}): {count:>8,} ({pct:5.1f}%)")

    # Same split as training
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"\nTrain size: {len(X_train):,}")
    print(f"Test  size: {len(X_test):,}")

    # Load model
    model = xgb.XGBClassifier()
    model.load_model(str(BALL_MODEL_PATH))
    logger.info(f"Loaded ball outcome model from {BALL_MODEL_PATH}")

    # Predict
    y_pred = model.predict(X_test)

    # --- Accuracy ---
    acc = accuracy_score(y_test, y_pred)
    print(f"\nOverall Accuracy: {acc:.4f} ({acc*100:.2f}%)")

    # --- Classification Report ---
    class_names_ordered = [OUTCOME_NAMES[i] for i in range(7)]
    print("\n" + "=" * 70)
    print("CLASSIFICATION REPORT")
    print("=" * 70)
    print(classification_report(
        y_test, y_pred,
        target_names=class_names_ordered,
        digits=4,
        zero_division=0,
    ))

    # --- Confusion Matrix ---
    cm = confusion_matrix(y_test, y_pred)
    print("=" * 70)
    print("CONFUSION MATRIX")
    print("=" * 70)
    header = f"{'True \\ Pred':<10}" + "".join(f"{n:>8}" for n in class_names_ordered)
    print(header)
    print("-" * len(header))
    for i, row in enumerate(cm):
        row_str = f"{class_names_ordered[i]:<10}" + "".join(f"{v:>8}" for v in row)
        print(row_str)

    # --- Per-class sensitivity & specificity ---
    per_class_sensitivity_specificity(y_test, y_pred, class_names_ordered)


# ---------------------------------------------------------------------------
# 2. WIN PROBABILITY MODEL EVALUATION
# ---------------------------------------------------------------------------
def build_win_probability_data(data_dir: Path) -> pd.DataFrame:
    """Reproduce the exact data pipeline from train_model.py for win prob."""
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

    for filepath in files:
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
                recent_wickets: list[int] = []

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

                        wkts_last_5 = sum(1 for wb in recent_wickets if wb > balls - 30)

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

    return pd.DataFrame(rows)


def evaluate_win_probability_model(data_dir: Path):
    print("\n")
    print("#" * 70)
    print("#  WIN PROBABILITY MODEL EVALUATION (binary)")
    print("#" * 70)

    df = build_win_probability_data(data_dir)

    X = df.drop("label", axis=1).values
    y = df["label"].values

    print(f"\nTotal samples: {len(X)}")
    print(f"Features:      {X.shape[1]}")
    print(f"\nClass distribution:")
    for cls in sorted(np.unique(y)):
        count = int((y == cls).sum())
        pct = 100.0 * count / len(y)
        label_name = "Batting team LOSES" if cls == 0 else "Batting team WINS"
        print(f"  {cls} ({label_name}): {count:>8,} ({pct:5.1f}%)")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"\nTrain size: {len(X_train):,}")
    print(f"Test  size: {len(X_test):,}")

    model = xgb.XGBClassifier()
    model.load_model(str(WIN_MODEL_PATH))
    logger.info(f"Loaded win probability model from {WIN_MODEL_PATH}")

    y_pred = model.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    print(f"\nOverall Accuracy: {acc:.4f} ({acc*100:.2f}%)")

    class_names = ["Loss (0)", "Win (1)"]
    print("\n" + "=" * 70)
    print("CLASSIFICATION REPORT")
    print("=" * 70)
    print(classification_report(
        y_test, y_pred,
        target_names=class_names,
        digits=4,
        zero_division=0,
    ))

    cm = confusion_matrix(y_test, y_pred)
    print("=" * 70)
    print("CONFUSION MATRIX")
    print("=" * 70)
    header = f"{'True \\ Pred':<14}" + "".join(f"{n:>12}" for n in class_names)
    print(header)
    print("-" * len(header))
    for i, row in enumerate(cm):
        row_str = f"{class_names[i]:<14}" + "".join(f"{v:>12}" for v in row)
        print(row_str)

    per_class_sensitivity_specificity(y_test, y_pred, class_names)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate CalledIt ML models")
    parser.add_argument("--data-dir", default=str(BASE_DIR / "app" / "ml" / "data"),
                        help="Directory with Cricsheet JSON files")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    print("=" * 70)
    print("  CalledIt ML Model Evaluation")
    print(f"  Data directory: {data_dir}")
    print("=" * 70)

    evaluate_ball_outcome_model(data_dir)
    evaluate_win_probability_model(data_dir)

    print("\n" + "=" * 70)
    print("  EVALUATION COMPLETE")
    print("=" * 70)
