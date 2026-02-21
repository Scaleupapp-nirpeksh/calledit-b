"""CalledIt Scoring Engine — the core points calculation system."""

from app.utils.constants import (
    BALL_CORRECT_POINTS,
    CLUTCH_MULTIPLIER,
    CLUTCH_OVER_START,
    CLUTCH_OVER_END,
    CONFIDENCE_BOOST_MULTIPLIER,
    MATCH_WINNER_POINTS,
    MILESTONE_CORRECT_POINTS,
    OVER_CLOSE_POINTS,
    OVER_CLOSE_RANGE,
    OVER_EXACT_POINTS,
    STREAK_THRESHOLDS,
)


def score_ball_prediction(prediction: str, actual_outcome: str) -> tuple[bool, int]:
    """Check if ball prediction matches actual outcome.
    Returns (is_correct, base_points).
    """
    is_correct = prediction == actual_outcome
    base_points = BALL_CORRECT_POINTS if is_correct else 0
    return is_correct, base_points


def calculate_streak_multiplier(consecutive_correct: int) -> float:
    """Calculate streak multiplier based on consecutive correct predictions.
    0-2 correct → 1.0x
    3-4 correct → 1.5x
    5-9 correct → 2.0x
    10+ correct → 3.0x
    """
    multiplier = 1.0
    for threshold, mult in sorted(STREAK_THRESHOLDS.items()):
        if consecutive_correct >= threshold:
            multiplier = mult
    return multiplier


def is_clutch_mode(over: int) -> bool:
    """Check if the over is in clutch mode range (overs 15-20)."""
    return CLUTCH_OVER_START <= over <= CLUTCH_OVER_END


def calculate_total_points(
    base_points: int,
    streak_multiplier: float,
    confidence_boost: bool,
    is_clutch: bool,
) -> int:
    """Apply all multipliers to base points and return total.

    Formula: base x streak x confidence x clutch
    """
    if base_points == 0:
        return 0

    total = float(base_points)
    total *= streak_multiplier

    if confidence_boost:
        total *= CONFIDENCE_BOOST_MULTIPLIER

    if is_clutch:
        total *= CLUTCH_MULTIPLIER

    return int(total)


def score_over_prediction(predicted_runs: int, actual_runs: int) -> tuple[bool, int]:
    """Score an over total prediction.
    Exact match → 25 points
    Within ±3 → 10 points
    Otherwise → 0
    """
    diff = abs(predicted_runs - actual_runs)
    if diff == 0:
        return True, OVER_EXACT_POINTS
    elif diff <= OVER_CLOSE_RANGE:
        return True, OVER_CLOSE_POINTS
    return False, 0


def score_milestone(predicted_will_achieve: bool, actually_achieved: bool) -> tuple[bool, int]:
    """Score a milestone prediction.
    Correct → 50 points, Incorrect → 0
    """
    is_correct = predicted_will_achieve == actually_achieved
    return is_correct, MILESTONE_CORRECT_POINTS if is_correct else 0


def score_match_winner(predicted_winner: str, actual_winner: str) -> tuple[bool, int]:
    """Score a match winner prediction.
    Correct → 100 points, Incorrect → 0
    """
    is_correct = predicted_winner == actual_winner
    return is_correct, MATCH_WINNER_POINTS if is_correct else 0
