"""Bridge between ML models and the application layer."""

import logging

from app.ml.feature_engineering import LiveFeatureExtractor
from app.ml.inference import MLInference
from app.services import match_service

logger = logging.getLogger(__name__)

_inference = MLInference()
_feature_extractor = LiveFeatureExtractor()


async def initialize() -> None:
    """Load ML models at application startup."""
    _inference.load_models()
    if _inference.is_loaded:
        logger.info("ML models initialized successfully")
    else:
        logger.warning("ML models not loaded — using fallback predictions")


def _build_match_state(match: dict) -> dict:
    """Build a match_state dict from match document with computed stats.

    Computes batter/bowler in-innings stats from ball_log so the feature
    extractor gets the same features at inference as during training.
    """
    ball_log = match.get("ball_log", [])
    current_innings = match.get("current_innings", 1)

    # Filter ball_log for current innings
    innings_balls = [b for b in ball_log if b.get("innings") == current_innings]

    # Compute batter stats for current batter
    current_batter = innings_balls[-1].get("batter", "") if innings_balls else ""
    batter_runs = sum(b.get("batter_runs", 0) for b in innings_balls if b.get("batter") == current_batter)
    batter_balls = sum(1 for b in innings_balls if b.get("batter") == current_batter)
    batter_sr = (batter_runs / batter_balls * 100) if batter_balls > 0 else 0.0

    # Compute bowler stats for current bowler
    current_bowler = innings_balls[-1].get("bowler", "") if innings_balls else ""
    bowler_runs = sum(b.get("total_runs", 0) for b in innings_balls if b.get("bowler") == current_bowler)
    bowler_balls = sum(1 for b in innings_balls if b.get("bowler") == current_bowler)
    bowler_wkts = sum(1 for b in innings_balls if b.get("bowler") == current_bowler and b.get("is_wicket"))
    bowler_economy = (bowler_runs / (bowler_balls / 6)) if bowler_balls >= 6 else 0.0

    # Partnership: count from last wicket
    partnership_runs = 0
    partnership_balls = 0
    for b in reversed(innings_balls):
        if b.get("is_wicket"):
            break
        partnership_runs += b.get("batter_runs", 0)
        partnership_balls += 1

    # Score and wickets
    score = sum(b.get("total_runs", 0) for b in innings_balls)
    wickets = sum(1 for b in innings_balls if b.get("is_wicket"))
    balls_bowled = len(innings_balls)

    # Last 3 outcomes (as label codes)
    from app.ml.feature_engineering import OUTCOME_LABELS
    last_outcomes = []
    for b in innings_balls[-3:]:
        outcome = b.get("outcome", "dot")
        last_outcomes.append(OUTCOME_LABELS.get(outcome, 0))

    # Toss data
    toss_winner = match.get("toss_winner", "")
    toss_decision_str = match.get("toss_decision", "bat")
    toss_decision = 0 if toss_decision_str == "bat" else 1

    # Determine batting team from innings data
    innings_data = match.get("innings", [])
    batting_team = ""
    if innings_data and len(innings_data) >= current_innings:
        batting_team = innings_data[current_innings - 1].get("batting_team", match.get("team1", ""))

    is_batting_team_toss_winner = int(batting_team == toss_winner)

    # Target (2nd innings only)
    target = 0
    if current_innings == 2 and innings_data:
        target = innings_data[0].get("score", 0) + 1

    # Wickets in last 5 overs (30 balls)
    wkts_last_5 = sum(1 for b in innings_balls[-30:] if b.get("is_wicket"))

    last_ball = innings_balls[-1] if innings_balls else {}

    return {
        "innings": current_innings,
        "current_over": last_ball.get("over", 0),
        "ball_in_over": last_ball.get("ball", 0),
        "score": score,
        "wickets": wickets,
        "balls_bowled": balls_bowled,
        "last_outcomes": last_outcomes,
        "batter_runs_so_far": batter_runs,
        "batter_balls_faced": batter_balls,
        "batter_strike_rate": round(batter_sr, 2),
        "is_new_batter": batter_balls <= 1,
        "bowler_economy_so_far": round(bowler_economy, 2),
        "bowler_wickets_so_far": bowler_wkts,
        "bowler_balls_bowled": bowler_balls,
        "partnership_runs": partnership_runs,
        "partnership_balls": partnership_balls,
        "is_batting_team_toss_winner": is_batting_team_toss_winner,
        "toss_decision": toss_decision,
        # Win probability extras
        "overs": round(balls_bowled / 6, 1),
        "run_rate": round((score / (balls_bowled / 6)), 2) if balls_bowled >= 6 else 0.0,
        "target": target,
        "batting_team_id": _inference.get_team_id(batting_team),
        "bowling_team_id": _inference.get_team_id(
            match.get("team2", "") if batting_team == match.get("team1", "") else match.get("team1", "")
        ),
        "wickets_in_last_5_overs": wkts_last_5,
        # Metadata
        "current_ball_key": last_ball.get("ball_key", ""),
        "current_innings": current_innings,
        "team1": match.get("team1", "Team 1"),
        "team2": match.get("team2", "Team 2"),
        "innings_data": innings_data,
    }


async def get_ball_probabilities(match_id: str) -> dict:
    """Get next-ball outcome probabilities for a live match."""
    match = await match_service.get_match(match_id)
    if not match:
        return {"probabilities": {}, "error": "Match not found"}

    match_state = _build_match_state(match)
    features = _feature_extractor.extract(match_state)
    probs = _inference.predict_ball_outcome(features)

    return {
        "match_id": match_id,
        "ball_key": match_state.get("current_ball_key"),
        "probabilities": probs,
        "model_version": "v2",
    }


async def get_win_probability(match_id: str) -> dict:
    """Get current win probability for both teams."""
    match = await match_service.get_match(match_id)
    if not match:
        return {"probabilities": {}, "error": "Match not found"}

    match_state = _build_match_state(match)
    features = _feature_extractor.extract_win_probability_features(match_state)

    team1 = match_state["team1"]
    team2 = match_state["team2"]
    current_innings = match_state["current_innings"]
    innings_data = match_state.get("innings_data", [])

    if innings_data and len(innings_data) >= current_innings:
        batting_team = innings_data[current_innings - 1].get("batting_team", team1)
        bowling_team = team2 if batting_team == team1 else team1
    else:
        batting_team = team1
        bowling_team = team2

    probs = _inference.predict_win_probability(features, (batting_team, bowling_team))

    return {
        "match_id": match_id,
        "team1": team1,
        "team2": team2,
        "probabilities": probs,
        "model_version": "v2",
    }


async def get_combined_predictions(match_id: str) -> dict:
    """Get both ball probabilities and win probability."""
    ball = await get_ball_probabilities(match_id)
    win = await get_win_probability(match_id)

    return {
        "match_id": match_id,
        "ball_probabilities": ball.get("probabilities", {}),
        "win_probabilities": win.get("probabilities", {}),
        "model_version": "v2",
    }
