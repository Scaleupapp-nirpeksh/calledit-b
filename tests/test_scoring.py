"""Tests for CalledIt scoring engine — all rules, multipliers, edge cases."""

from app.services.scoring_service import (
    calculate_streak_multiplier,
    calculate_total_points,
    is_clutch_mode,
    score_ball_prediction,
    score_match_winner,
    score_milestone,
    score_over_prediction,
)


class TestBallScoring:
    def test_correct_prediction(self):
        is_correct, points = score_ball_prediction("dot", "dot")
        assert is_correct is True
        assert points == 10

    def test_incorrect_prediction(self):
        is_correct, points = score_ball_prediction("4", "dot")
        assert is_correct is False
        assert points == 0

    def test_all_outcomes(self):
        for outcome in ["dot", "1", "2", "3", "4", "6", "wicket"]:
            is_correct, points = score_ball_prediction(outcome, outcome)
            assert is_correct is True
            assert points == 10


class TestStreakMultiplier:
    def test_no_streak(self):
        assert calculate_streak_multiplier(0) == 1.0
        assert calculate_streak_multiplier(1) == 1.0
        assert calculate_streak_multiplier(2) == 1.0

    def test_3_streak(self):
        assert calculate_streak_multiplier(3) == 1.5
        assert calculate_streak_multiplier(4) == 1.5

    def test_5_streak(self):
        assert calculate_streak_multiplier(5) == 2.0
        assert calculate_streak_multiplier(9) == 2.0

    def test_10_streak(self):
        assert calculate_streak_multiplier(10) == 3.0
        assert calculate_streak_multiplier(20) == 3.0


class TestClutchMode:
    def test_not_clutch(self):
        assert is_clutch_mode(1) is False
        assert is_clutch_mode(14) is False

    def test_clutch_overs(self):
        assert is_clutch_mode(15) is True
        assert is_clutch_mode(18) is True
        assert is_clutch_mode(20) is True


class TestTotalPoints:
    def test_base_only(self):
        assert calculate_total_points(10, 1.0, False, False) == 10

    def test_zero_base(self):
        # Wrong prediction = 0 points regardless of multipliers
        assert calculate_total_points(0, 3.0, True, True) == 0

    def test_streak_multiplier(self):
        assert calculate_total_points(10, 1.5, False, False) == 15
        assert calculate_total_points(10, 2.0, False, False) == 20
        assert calculate_total_points(10, 3.0, False, False) == 30

    def test_confidence_boost(self):
        assert calculate_total_points(10, 1.0, True, False) == 20

    def test_clutch_mode(self):
        assert calculate_total_points(10, 1.0, False, True) == 20

    def test_all_multipliers(self):
        # 10 base × 3.0 streak × 2.0 confidence × 2.0 clutch = 120
        assert calculate_total_points(10, 3.0, True, True) == 120

    def test_streak_plus_clutch(self):
        # 10 × 2.0 streak × 2.0 clutch = 40
        assert calculate_total_points(10, 2.0, False, True) == 40

    def test_streak_plus_confidence(self):
        # 10 × 1.5 streak × 2.0 confidence = 30
        assert calculate_total_points(10, 1.5, True, False) == 30


class TestOverScoring:
    def test_exact_match(self):
        is_correct, points = score_over_prediction(8, 8)
        assert is_correct is True
        assert points == 25

    def test_close_within_3(self):
        is_correct, points = score_over_prediction(10, 7)
        assert is_correct is True
        assert points == 10

    def test_close_within_1(self):
        is_correct, points = score_over_prediction(8, 9)
        assert is_correct is True
        assert points == 10

    def test_too_far(self):
        is_correct, points = score_over_prediction(5, 15)
        assert is_correct is False
        assert points == 0


class TestMilestoneScoring:
    def test_correct_will_achieve(self):
        is_correct, points = score_milestone(True, True)
        assert is_correct is True
        assert points == 50

    def test_correct_wont_achieve(self):
        is_correct, points = score_milestone(False, False)
        assert is_correct is True
        assert points == 50

    def test_incorrect(self):
        is_correct, points = score_milestone(True, False)
        assert is_correct is False
        assert points == 0


class TestMatchWinnerScoring:
    def test_correct_winner(self):
        is_correct, points = score_match_winner("CSK", "CSK")
        assert is_correct is True
        assert points == 100

    def test_incorrect_winner(self):
        is_correct, points = score_match_winner("CSK", "MI")
        assert is_correct is False
        assert points == 0
