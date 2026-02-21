"""Feature engineering for CalledIt ML models.

Two classes:
- TrainingFeatureExtractor: reads Cricsheet JSON → training DataFrame
- LiveFeatureExtractor: takes live match state → feature vector for inference

No encoder persistence needed — all features are computed from in-innings
statistics that work identically at training and inference time.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Outcome label mapping (7 classes for ball outcome)
OUTCOME_LABELS = {"dot": 0, "1": 1, "2": 2, "3": 3, "4": 4, "6": 5, "wicket": 6}
OUTCOME_NAMES = {v: k for k, v in OUTCOME_LABELS.items()}

# Ball model: 22 features (no encoder IDs needed)
BALL_FEATURES = [
    "innings", "over", "ball_in_over", "score", "wickets",
    "run_rate", "balls_remaining", "phase",
    "last_outcome_1", "last_outcome_2", "last_outcome_3",
    "batter_runs_so_far", "batter_balls_faced", "batter_strike_rate", "is_new_batter",
    "bowler_economy_so_far", "bowler_wickets_so_far", "bowler_balls_bowled",
    "partnership_runs", "partnership_balls",
    "is_batting_team_toss_winner", "toss_decision",
]

# Win probability model: 14 features
WIN_FEATURES = [
    "innings", "score", "wickets", "overs",
    "run_rate", "target", "required_rate",
    "balls_remaining", "phase",
    "batting_team_id", "bowling_team_id",
    "is_batting_team_toss_winner", "toss_decision",
    "wickets_in_last_5_overs",
]


class TrainingFeatureExtractor:
    """Reads Cricsheet JSON files and extracts per-delivery features.

    No encoder IDs — all features are in-innings aggregates that work at
    inference time without needing persisted mappings.
    """

    def __init__(self):
        # Team encoder for win probability model (persisted to JSON)
        self.team_encoder: dict[str, int] = {}
        self._next_team = 0

    def encode_team(self, team: str) -> int:
        """Encode team name to integer. Mappings are saved for inference."""
        if team not in self.team_encoder:
            self.team_encoder[team] = self._next_team
            self._next_team += 1
        return self.team_encoder[team]

    def extract_from_file(self, filepath: str | Path) -> list[dict]:
        """Extract feature rows from a single Cricsheet JSON file."""
        with open(filepath) as f:
            match = json.load(f)

        info = match.get("info", {})

        # Toss data
        toss = info.get("toss", {})
        toss_winner = toss.get("winner", "")
        toss_decision = 0 if toss.get("decision") == "bat" else 1

        rows = []
        for innings_idx, innings in enumerate(match.get("innings", []), start=1):
            batting_team = innings.get("team", "")
            is_batting_team_toss_winner = int(batting_team == toss_winner)

            score = 0
            wickets = 0
            balls_bowled = 0
            batter_runs_map: dict[str, int] = {}
            batter_balls_map: dict[str, int] = {}
            bowler_runs_map: dict[str, int] = {}
            bowler_balls_map: dict[str, int] = {}
            bowler_wickets_map: dict[str, int] = {}
            last_outcomes: list[int] = []
            partnership_runs = 0
            partnership_balls = 0

            for over_data in innings.get("overs", []):
                over_num = over_data["over"]  # 0-indexed

                for ball_idx, delivery in enumerate(over_data.get("deliveries", [])):
                    batter = delivery.get("batter", "")
                    bowler = delivery.get("bowler", "")

                    runs = delivery.get("runs", {})
                    batter_runs = runs.get("batter", 0)
                    total_runs = runs.get("total", 0)

                    # Check for extras (skip wides/no-balls for clean data)
                    extras_detail = delivery.get("extras", {})
                    is_wide = "wides" in extras_detail
                    is_noball = "noballs" in extras_detail
                    if is_wide or is_noball:
                        score += total_runs
                        continue

                    # Determine target label
                    has_wicket = "wickets" in delivery
                    if has_wicket:
                        label = OUTCOME_LABELS["wicket"]
                    else:
                        label = OUTCOME_LABELS.get(str(batter_runs), OUTCOME_LABELS["dot"])

                    # Phase
                    if over_num < 6:
                        phase = 0  # powerplay
                    elif over_num < 14:
                        phase = 1  # middle
                    else:
                        phase = 2  # death

                    # Batter stats (BEFORE this ball)
                    batter_total_runs = batter_runs_map.get(batter, 0)
                    batter_total_balls = batter_balls_map.get(batter, 0)
                    batter_sr = (batter_total_runs / batter_total_balls * 100) if batter_total_balls > 0 else 0.0
                    is_new_batter = batter_total_balls <= 1

                    # Bowler stats (BEFORE this ball)
                    bowler_total_runs = bowler_runs_map.get(bowler, 0)
                    bowler_total_balls = bowler_balls_map.get(bowler, 0)
                    bowler_economy = (bowler_total_runs / (bowler_total_balls / 6)) if bowler_total_balls >= 6 else 0.0
                    bowler_wkts = bowler_wickets_map.get(bowler, 0)

                    # Run rate
                    run_rate = (score / (balls_bowled / 6)) if balls_bowled >= 6 else 0.0
                    balls_remaining = 120 - balls_bowled

                    # Last 3 outcomes
                    last_3 = (last_outcomes[-3:] if len(last_outcomes) >= 3
                              else [0] * (3 - len(last_outcomes)) + last_outcomes)

                    row = {
                        "innings": innings_idx,
                        "over": over_num,
                        "ball_in_over": ball_idx,
                        "score": score,
                        "wickets": wickets,
                        "run_rate": round(run_rate, 2),
                        "balls_remaining": balls_remaining,
                        "phase": phase,
                        "last_outcome_1": last_3[0],
                        "last_outcome_2": last_3[1],
                        "last_outcome_3": last_3[2],
                        "batter_runs_so_far": batter_total_runs,
                        "batter_balls_faced": batter_total_balls,
                        "batter_strike_rate": round(batter_sr, 2),
                        "is_new_batter": int(is_new_batter),
                        "bowler_economy_so_far": round(bowler_economy, 2),
                        "bowler_wickets_so_far": bowler_wkts,
                        "bowler_balls_bowled": bowler_total_balls,
                        "partnership_runs": partnership_runs,
                        "partnership_balls": partnership_balls,
                        "is_batting_team_toss_winner": is_batting_team_toss_winner,
                        "toss_decision": toss_decision,
                        "label": label,
                    }
                    rows.append(row)

                    # Update state AFTER recording features
                    score += total_runs
                    balls_bowled += 1
                    batter_runs_map[batter] = batter_runs_map.get(batter, 0) + batter_runs
                    batter_balls_map[batter] = batter_balls_map.get(batter, 0) + 1
                    bowler_runs_map[bowler] = bowler_runs_map.get(bowler, 0) + total_runs
                    bowler_balls_map[bowler] = bowler_balls_map.get(bowler, 0) + 1
                    last_outcomes.append(label)
                    partnership_runs += batter_runs
                    partnership_balls += 1

                    if has_wicket:
                        wickets += 1
                        partnership_runs = 0
                        partnership_balls = 0
                        bowler_wickets_map[bowler] = bowler_wickets_map.get(bowler, 0) + 1

        return rows

    def extract_from_directory(self, data_dir: str | Path) -> pd.DataFrame:
        """Extract features from all JSON files in a directory."""
        data_dir = Path(data_dir)
        all_rows = []
        files = list(data_dir.glob("*.json"))
        logger.info(f"Processing {len(files)} match files...")

        for i, filepath in enumerate(files):
            try:
                rows = self.extract_from_file(filepath)
                all_rows.extend(rows)
            except Exception as e:
                logger.warning(f"Skipping {filepath.name}: {e}")

            if (i + 1) % 500 == 0:
                logger.info(f"Processed {i + 1}/{len(files)} files ({len(all_rows)} deliveries)")

        df = pd.DataFrame(all_rows)
        logger.info(f"Total: {len(df)} deliveries from {len(files)} matches")
        return df


class LiveFeatureExtractor:
    """Builds feature vectors from live match state for inference.

    All features come from match_state dict — no encoder lookups needed.
    The caller (ml_service) computes batter/bowler stats from ball_log.
    """

    def extract(self, match_state: dict) -> np.ndarray:
        """Extract feature vector from a live match state dict."""
        over = match_state.get("current_over", 0)
        if over < 6:
            phase = 0
        elif over < 14:
            phase = 1
        else:
            phase = 2

        score = match_state.get("score", 0)
        balls_bowled = match_state.get("balls_bowled", 0)
        run_rate = (score / (balls_bowled / 6)) if balls_bowled >= 6 else 0.0
        balls_remaining = 120 - balls_bowled

        last_outcomes = match_state.get("last_outcomes", [0, 0, 0])
        while len(last_outcomes) < 3:
            last_outcomes.insert(0, 0)

        features = np.array([
            match_state.get("innings", 1),
            over,
            match_state.get("ball_in_over", 0),
            score,
            match_state.get("wickets", 0),
            round(run_rate, 2),
            balls_remaining,
            phase,
            last_outcomes[-3],
            last_outcomes[-2],
            last_outcomes[-1],
            match_state.get("batter_runs_so_far", 0),
            match_state.get("batter_balls_faced", 0),
            match_state.get("batter_strike_rate", 0.0),
            int(match_state.get("is_new_batter", False)),
            match_state.get("bowler_economy_so_far", 0.0),
            match_state.get("bowler_wickets_so_far", 0),
            match_state.get("bowler_balls_bowled", 0),
            match_state.get("partnership_runs", 0),
            match_state.get("partnership_balls", 0),
            int(match_state.get("is_batting_team_toss_winner", False)),
            match_state.get("toss_decision", 0),
        ], dtype=np.float32).reshape(1, -1)

        return features

    def extract_win_probability_features(self, match_state: dict) -> np.ndarray:
        """Extract features for win probability model."""
        score = match_state.get("score", 0)
        wickets = match_state.get("wickets", 0)
        overs = match_state.get("overs", 0.0)
        run_rate = match_state.get("run_rate", 0.0)
        target = match_state.get("target", 0)
        innings = match_state.get("innings", 1)

        balls_bowled = match_state.get("balls_bowled", 0)
        balls_remaining = 120 - balls_bowled
        required_rate = 0.0
        if innings == 2 and target > 0 and balls_remaining > 0:
            runs_needed = target - score
            overs_remaining = balls_remaining / 6
            required_rate = runs_needed / overs_remaining if overs_remaining > 0 else 99.0

        if overs < 6:
            phase = 0
        elif overs < 14:
            phase = 1
        else:
            phase = 2

        features = np.array([
            innings,
            score,
            wickets,
            overs,
            run_rate,
            target,
            required_rate,
            balls_remaining,
            phase,
            match_state.get("batting_team_id", 0),
            match_state.get("bowling_team_id", 0),
            int(match_state.get("is_batting_team_toss_winner", False)),
            match_state.get("toss_decision", 0),
            match_state.get("wickets_in_last_5_overs", 0),
        ], dtype=np.float32).reshape(1, -1)

        return features
