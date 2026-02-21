"""Tests for CalledIt prediction engine — submit, resolve, duplicate checks."""

import pytest

from app.services import prediction_service
from app.utils.constants import BallOutcome, PredictionType


@pytest.mark.asyncio
class TestBallPredictions:
    async def test_create_ball_prediction(self, setup_db, setup_redis, test_user, test_match):
        pred = await prediction_service.create_ball_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            innings=1,
            over=1,
            ball=1,
            prediction=BallOutcome.FOUR.value,
        )
        assert pred["type"] == PredictionType.BALL
        assert pred["prediction"] == "4"
        assert pred["is_resolved"] is False

    async def test_duplicate_prediction_rejected(self, setup_db, setup_redis, test_user, test_match):
        await prediction_service.create_ball_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            innings=1, over=1, ball=1,
            prediction=BallOutcome.DOT.value,
        )
        with pytest.raises(ValueError, match="Already predicted"):
            await prediction_service.create_ball_prediction(
                user_id=test_user["_id"],
                match_id=test_match["_id"],
                innings=1, over=1, ball=1,
                prediction=BallOutcome.SIX.value,
            )

    async def test_confidence_boost(self, setup_db, setup_redis, test_user, test_match):
        pred = await prediction_service.create_ball_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            innings=1, over=1, ball=1,
            prediction=BallOutcome.DOT.value,
            confidence_boost=True,
        )
        assert pred["confidence_boost"] is True

    async def test_confidence_boost_limit(self, setup_db, setup_redis, test_user, test_match):
        # Use all 3 boosts
        for ball in range(1, 4):
            await prediction_service.create_ball_prediction(
                user_id=test_user["_id"],
                match_id=test_match["_id"],
                innings=1, over=1, ball=ball,
                prediction=BallOutcome.DOT.value,
                confidence_boost=True,
            )
        # 4th should fail
        with pytest.raises(ValueError, match="Maximum 3"):
            await prediction_service.create_ball_prediction(
                user_id=test_user["_id"],
                match_id=test_match["_id"],
                innings=1, over=1, ball=4,
                prediction=BallOutcome.DOT.value,
                confidence_boost=True,
            )


@pytest.mark.asyncio
class TestResolvePredictions:
    async def test_resolve_correct(self, setup_db, setup_redis, test_user, test_match):
        await prediction_service.create_ball_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            innings=1, over=1, ball=1,
            prediction=BallOutcome.FOUR.value,
        )
        count = await prediction_service.resolve_ball_predictions(
            test_match["_id"], "1.1.1", BallOutcome.FOUR.value, over=1
        )
        assert count == 1

        # Check prediction was updated
        preds = await prediction_service.get_user_match_predictions(
            test_user["_id"], test_match["_id"]
        )
        assert preds[0]["is_resolved"] is True
        assert preds[0]["is_correct"] is True
        assert preds[0]["total_points"] == 10

    async def test_resolve_incorrect(self, setup_db, setup_redis, test_user, test_match):
        await prediction_service.create_ball_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            innings=1, over=1, ball=1,
            prediction=BallOutcome.SIX.value,
        )
        await prediction_service.resolve_ball_predictions(
            test_match["_id"], "1.1.1", BallOutcome.DOT.value, over=1
        )
        preds = await prediction_service.get_user_match_predictions(
            test_user["_id"], test_match["_id"]
        )
        assert preds[0]["is_correct"] is False
        assert preds[0]["total_points"] == 0


@pytest.mark.asyncio
class TestMatchWinnerPredictions:
    async def test_create_winner_prediction(self, setup_db, setup_redis, test_user, test_match):
        pred = await prediction_service.create_match_winner_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            predicted_winner="Chennai Super Kings",
        )
        assert pred["prediction"] == "Chennai Super Kings"
        assert pred["type"] == PredictionType.MATCH_WINNER

    async def test_update_winner_prediction(self, setup_db, setup_redis, test_user, test_match):
        await prediction_service.create_match_winner_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            predicted_winner="Chennai Super Kings",
        )
        # Change prediction (allowed up to 2 times)
        pred = await prediction_service.create_match_winner_prediction(
            user_id=test_user["_id"],
            match_id=test_match["_id"],
            predicted_winner="Mumbai Indians",
        )
        assert pred["prediction"] == "Mumbai Indians"

    async def test_invalid_team(self, setup_db, setup_redis, test_user, test_match):
        with pytest.raises(ValueError, match="Invalid team"):
            await prediction_service.create_match_winner_prediction(
                user_id=test_user["_id"],
                match_id=test_match["_id"],
                predicted_winner="Nonexistent Team",
            )
