import logging

from app.database import get_db
from app.redis_client import get_redis
from app.services import match_service, scoring_service, leaderboard_service
from app.utils.constants import (
    CONFIDENCE_BOOSTS_PER_MATCH,
    MAX_WINNER_CHANGES,
    PredictionType,
    MatchStatus,
)
from app.utils.helpers import ball_key, generate_nanoid, utc_now

logger = logging.getLogger(__name__)


# ── Ball Predictions ──────────────────────────────────────────────

async def create_ball_prediction(
    user_id: str,
    match_id: str,
    innings: int,
    over: int,
    ball: int,
    prediction: str,
    confidence_boost: bool = False,
) -> dict:
    """Create a ball-by-ball prediction. Validates window, duplicates, boost budget."""
    match = await match_service.get_match(match_id)
    if not match:
        raise ValueError("Match not found")
    if match["status"] not in (MatchStatus.LIVE_1ST, MatchStatus.LIVE_2ND):
        raise ValueError("Match is not live")

    if not await match_service.is_prediction_window_open(match_id):
        raise ValueError("Prediction window is closed")

    bk = ball_key(innings, over, ball)
    db = get_db()
    existing = await db.predictions.find_one({
        "user_id": user_id,
        "match_id": match_id,
        "ball_key": bk,
        "type": PredictionType.BALL,
    })
    if existing:
        raise ValueError("Already predicted for this ball")

    if confidence_boost:
        boosts_used = await db.predictions.count_documents({
            "user_id": user_id,
            "match_id": match_id,
            "confidence_boost": True,
        })
        if boosts_used >= CONFIDENCE_BOOSTS_PER_MATCH:
            raise ValueError(f"Maximum {CONFIDENCE_BOOSTS_PER_MATCH} confidence boosts per match")

    now = utc_now()
    pred_doc = {
        "_id": generate_nanoid(),
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.BALL,
        "innings": innings,
        "over": over,
        "ball": ball,
        "ball_key": bk,
        "prediction": prediction,
        "confidence_boost": confidence_boost,
        "is_resolved": False,
        "is_correct": None,
        "actual_outcome": None,
        "base_points": 0,
        "streak_multiplier": 1.0,
        "confidence_multiplier": 1.0,
        "clutch_multiplier": 1.0,
        "total_points": 0,
        "created_at": now,
        "resolved_at": None,
    }
    await db.predictions.insert_one(pred_doc)
    return pred_doc


# ── Over Predictions ──────────────────────────────────────────────

async def create_over_prediction(
    user_id: str,
    match_id: str,
    innings: int,
    over: int,
    predicted_runs: int,
) -> dict:
    """Create an over total prediction."""
    match = await match_service.get_match(match_id)
    if not match:
        raise ValueError("Match not found")
    if match["status"] not in (MatchStatus.LIVE_1ST, MatchStatus.LIVE_2ND):
        raise ValueError("Match is not live")

    db = get_db()
    ok = f"{innings}.{over}"
    existing = await db.predictions.find_one({
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.OVER,
        "ball_key": ok,
    })
    if existing:
        raise ValueError("Already predicted for this over")

    now = utc_now()
    pred_doc = {
        "_id": generate_nanoid(),
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.OVER,
        "innings": innings,
        "over": over,
        "ball": None,
        "ball_key": ok,
        "prediction": str(predicted_runs),
        "confidence_boost": False,
        "is_resolved": False,
        "is_correct": None,
        "actual_outcome": None,
        "base_points": 0,
        "streak_multiplier": 1.0,
        "confidence_multiplier": 1.0,
        "clutch_multiplier": 1.0,
        "total_points": 0,
        "created_at": now,
        "resolved_at": None,
    }
    await db.predictions.insert_one(pred_doc)
    return pred_doc


# ── Milestone Predictions ────────────────────────────────────────

async def create_milestone_prediction(
    user_id: str,
    match_id: str,
    milestone_type: str,
    player_name: str,
    will_achieve: bool,
) -> dict:
    """Create a milestone prediction (batter 50/100, bowler 3w/5w)."""
    match = await match_service.get_match(match_id)
    if not match:
        raise ValueError("Match not found")

    db = get_db()
    milestone_key = f"{milestone_type}:{player_name}"
    existing = await db.predictions.find_one({
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.MILESTONE,
        "ball_key": milestone_key,
    })
    if existing:
        raise ValueError("Already predicted this milestone")

    now = utc_now()
    pred_doc = {
        "_id": generate_nanoid(),
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.MILESTONE,
        "innings": None,
        "over": None,
        "ball": None,
        "ball_key": milestone_key,
        "prediction": str(will_achieve),
        "confidence_boost": False,
        "is_resolved": False,
        "is_correct": None,
        "actual_outcome": None,
        "base_points": 0,
        "streak_multiplier": 1.0,
        "confidence_multiplier": 1.0,
        "clutch_multiplier": 1.0,
        "total_points": 0,
        "created_at": now,
        "resolved_at": None,
    }
    await db.predictions.insert_one(pred_doc)
    return pred_doc


# ── Match Winner Predictions ─────────────────────────────────────

async def create_match_winner_prediction(
    user_id: str,
    match_id: str,
    predicted_winner: str,
) -> dict:
    """Create or update match winner prediction (max 2 changes allowed)."""
    match = await match_service.get_match(match_id)
    if not match:
        raise ValueError("Match not found")
    if match["status"] == MatchStatus.COMPLETED:
        raise ValueError("Match already completed")

    if predicted_winner not in (match["team1"], match["team2"]):
        raise ValueError("Invalid team name")

    db = get_db()
    existing = await db.predictions.find_one({
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.MATCH_WINNER,
    })

    now = utc_now()

    if existing:
        changes = existing.get("winner_changes", 0)
        if changes >= MAX_WINNER_CHANGES:
            raise ValueError(f"Maximum {MAX_WINNER_CHANGES} winner prediction changes allowed")
        await db.predictions.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {"prediction": predicted_winner, "updated_at": now},
                "$inc": {"winner_changes": 1},
            },
        )
        existing["prediction"] = predicted_winner
        return existing

    pred_doc = {
        "_id": generate_nanoid(),
        "user_id": user_id,
        "match_id": match_id,
        "type": PredictionType.MATCH_WINNER,
        "innings": None,
        "over": None,
        "ball": None,
        "ball_key": f"winner:{match_id}",
        "prediction": predicted_winner,
        "confidence_boost": False,
        "is_resolved": False,
        "is_correct": None,
        "actual_outcome": None,
        "base_points": 0,
        "streak_multiplier": 1.0,
        "confidence_multiplier": 1.0,
        "clutch_multiplier": 1.0,
        "total_points": 0,
        "winner_changes": 0,
        "created_at": now,
        "resolved_at": None,
    }
    await db.predictions.insert_one(pred_doc)
    return pred_doc


# ── Resolution ───────────────────────────────────────────────────

async def _get_competition_id(match_id: str) -> str | None:
    """Get competition_id for a match (used for leaderboard scoping)."""
    match = await match_service.get_match(match_id)
    return match.get("competition_id") if match else None


async def resolve_ball_predictions(
    match_id: str,
    bk: str,
    actual_outcome: str,
    over: int,
) -> int:
    """Resolve all ball predictions for a specific ball. Returns count resolved."""
    db = get_db()
    redis = get_redis()

    cursor = db.predictions.find({
        "match_id": match_id,
        "ball_key": bk,
        "type": PredictionType.BALL,
        "is_resolved": False,
    })
    predictions = await cursor.to_list(length=10000)
    count = 0

    for pred in predictions:
        user_id = pred["user_id"]
        is_correct, base_points = scoring_service.score_ball_prediction(
            pred["prediction"], actual_outcome
        )

        # Get streak from Redis
        streak_key = f"streak:{user_id}:{match_id}"
        if is_correct:
            streak = await redis.incr(streak_key)
        else:
            streak = 0
            await redis.set(streak_key, 0)

        streak_mult = scoring_service.calculate_streak_multiplier(streak if is_correct else 0)
        is_clutch = scoring_service.is_clutch_mode(over)
        total_points = scoring_service.calculate_total_points(
            base_points, streak_mult, pred.get("confidence_boost", False), is_clutch
        )

        now = utc_now()
        await db.predictions.update_one(
            {"_id": pred["_id"]},
            {
                "$set": {
                    "is_resolved": True,
                    "is_correct": is_correct,
                    "actual_outcome": actual_outcome,
                    "base_points": base_points,
                    "streak_multiplier": streak_mult,
                    "confidence_multiplier": 2.0 if pred.get("confidence_boost") else 1.0,
                    "clutch_multiplier": 2.0 if is_clutch else 1.0,
                    "total_points": total_points,
                    "resolved_at": now,
                }
            },
        )

        # Update user stats atomically
        update_ops = {
            "$inc": {
                "stats.total_predictions": 1,
                "stats.total_points": total_points,
            }
        }
        if is_correct:
            update_ops["$inc"]["stats.correct_predictions"] = 1
            if is_clutch:
                update_ops["$inc"]["stats.clutch_correct"] = 1

        await db.users.update_one({"_id": user_id}, update_ops)

        # Update best streak
        if is_correct:
            await db.users.update_one(
                {"_id": user_id, "stats.best_streak": {"$lt": streak}},
                {"$set": {"stats.best_streak": streak}},
            )

        # Update leaderboards
        if total_points > 0:
            from app.services.league_service import get_user_league_ids
            league_ids = await get_user_league_ids(user_id)
            comp_id = await _get_competition_id(match_id)
            await leaderboard_service.update_score(
                user_id, match_id, total_points, league_ids,
                competition_id=comp_id,
            )

        count += 1

    return count


async def resolve_over_predictions(
    match_id: str,
    innings: int,
    over: int,
    actual_runs: int,
) -> int:
    """Resolve all over total predictions for a specific over."""
    db = get_db()
    ok = f"{innings}.{over}"

    cursor = db.predictions.find({
        "match_id": match_id,
        "ball_key": ok,
        "type": PredictionType.OVER,
        "is_resolved": False,
    })
    predictions = await cursor.to_list(length=10000)
    count = 0

    for pred in predictions:
        user_id = pred["user_id"]
        predicted_runs = int(pred["prediction"])
        is_correct, base_points = scoring_service.score_over_prediction(
            predicted_runs, actual_runs
        )

        now = utc_now()
        await db.predictions.update_one(
            {"_id": pred["_id"]},
            {
                "$set": {
                    "is_resolved": True,
                    "is_correct": is_correct,
                    "actual_outcome": str(actual_runs),
                    "base_points": base_points,
                    "total_points": base_points,
                    "resolved_at": now,
                }
            },
        )

        if base_points > 0:
            await db.users.update_one(
                {"_id": user_id},
                {"$inc": {"stats.total_points": base_points}},
            )
            from app.services.league_service import get_user_league_ids
            league_ids = await get_user_league_ids(user_id)
            comp_id = await _get_competition_id(match_id)
            await leaderboard_service.update_score(
                user_id, match_id, base_points, league_ids,
                competition_id=comp_id,
            )

        count += 1

    return count


async def resolve_milestone_predictions(
    match_id: str,
    milestone_type: str,
    player_name: str,
    actually_achieved: bool,
) -> int:
    """Resolve all milestone predictions for a specific player/milestone. Returns count resolved."""
    db = get_db()
    milestone_key = f"{milestone_type}:{player_name}"

    cursor = db.predictions.find({
        "match_id": match_id,
        "ball_key": milestone_key,
        "type": PredictionType.MILESTONE,
        "is_resolved": False,
    })
    predictions = await cursor.to_list(length=10000)
    count = 0

    for pred in predictions:
        user_id = pred["user_id"]
        predicted_will_achieve = pred["prediction"] == "True"
        is_correct, base_points = scoring_service.score_milestone(
            predicted_will_achieve, actually_achieved
        )

        now = utc_now()
        await db.predictions.update_one(
            {"_id": pred["_id"]},
            {
                "$set": {
                    "is_resolved": True,
                    "is_correct": is_correct,
                    "actual_outcome": str(actually_achieved),
                    "base_points": base_points,
                    "total_points": base_points,
                    "resolved_at": now,
                }
            },
        )

        if base_points > 0:
            await db.users.update_one(
                {"_id": user_id},
                {"$inc": {"stats.total_points": base_points}},
            )
            from app.services.league_service import get_user_league_ids
            league_ids = await get_user_league_ids(user_id)
            comp_id = await _get_competition_id(match_id)
            await leaderboard_service.update_score(
                user_id, match_id, base_points, league_ids,
                competition_id=comp_id,
            )

        count += 1

    return count


async def resolve_match_winner_predictions(match_id: str, actual_winner: str) -> int:
    """Resolve all match winner predictions."""
    db = get_db()

    cursor = db.predictions.find({
        "match_id": match_id,
        "type": PredictionType.MATCH_WINNER,
        "is_resolved": False,
    })
    predictions = await cursor.to_list(length=100000)
    count = 0

    for pred in predictions:
        user_id = pred["user_id"]
        is_correct, base_points = scoring_service.score_match_winner(
            pred["prediction"], actual_winner
        )

        now = utc_now()
        await db.predictions.update_one(
            {"_id": pred["_id"]},
            {
                "$set": {
                    "is_resolved": True,
                    "is_correct": is_correct,
                    "actual_outcome": actual_winner,
                    "base_points": base_points,
                    "total_points": base_points,
                    "resolved_at": now,
                }
            },
        )

        if is_correct:
            await db.users.update_one(
                {"_id": user_id},
                {
                    "$inc": {
                        "stats.total_points": base_points,
                        "stats.match_winners_correct": 1,
                    }
                },
            )

        if base_points > 0:
            from app.services.league_service import get_user_league_ids
            league_ids = await get_user_league_ids(user_id)
            comp_id = await _get_competition_id(match_id)
            await leaderboard_service.update_score(
                user_id, match_id, base_points, league_ids,
                competition_id=comp_id,
            )

        count += 1

    return count


# ── Queries ──────────────────────────────────────────────────────

async def get_user_match_predictions(user_id: str, match_id: str) -> list[dict]:
    """Get all predictions by a user for a match."""
    db = get_db()
    cursor = db.predictions.find({
        "user_id": user_id,
        "match_id": match_id,
    }).sort("created_at", 1)
    return await cursor.to_list(length=10000)


async def get_user_match_summary(user_id: str, match_id: str) -> dict:
    """Get prediction summary for a user in a match."""
    preds = await get_user_match_predictions(user_id, match_id)

    total = len(preds)
    correct = sum(1 for p in preds if p.get("is_correct"))
    total_points = sum(p.get("total_points", 0) for p in preds)
    boosts_used = sum(1 for p in preds if p.get("confidence_boost"))

    redis = get_redis()
    streak_key = f"streak:{user_id}:{match_id}"
    current_streak = int(await redis.get(streak_key) or 0)

    best_streak = 0
    streak = 0
    for p in preds:
        if p.get("type") == PredictionType.BALL and p.get("is_resolved"):
            if p.get("is_correct"):
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 0

    return {
        "match_id": match_id,
        "user_id": user_id,
        "total_predictions": total,
        "correct_predictions": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0.0,
        "total_points": total_points,
        "current_streak": current_streak,
        "best_streak": best_streak,
        "confidence_boosts_used": boosts_used,
        "confidence_boosts_remaining": CONFIDENCE_BOOSTS_PER_MATCH - boosts_used,
        "predictions": preds,
    }


async def get_prediction_history(
    user_id: str, page: int = 1, limit: int = 20
) -> tuple[list[dict], int]:
    """Get paginated prediction history for a user."""
    db = get_db()
    query = {"user_id": user_id}
    total = await db.predictions.count_documents(query)
    offset = (page - 1) * limit
    cursor = db.predictions.find(query).sort("created_at", -1).skip(offset).limit(limit)
    preds = await cursor.to_list(length=limit)
    return preds, total


async def get_prediction_stats(user_id: str) -> dict:
    """Get overall prediction stats for a user."""
    db = get_db()
    pipeline = [
        {"$match": {"user_id": user_id, "is_resolved": True}},
        {
            "$group": {
                "_id": "$type",
                "total": {"$sum": 1},
                "correct": {"$sum": {"$cond": ["$is_correct", 1, 0]}},
                "points": {"$sum": "$total_points"},
            }
        },
    ]
    results = await db.predictions.aggregate(pipeline).to_list(length=10)

    by_type = {}
    grand_total = 0
    grand_correct = 0
    grand_points = 0
    for r in results:
        by_type[r["_id"]] = {
            "total": r["total"],
            "correct": r["correct"],
            "accuracy": round(r["correct"] / r["total"] * 100, 1) if r["total"] > 0 else 0.0,
            "points": r["points"],
        }
        grand_total += r["total"]
        grand_correct += r["correct"]
        grand_points += r["points"]

    user = await db.users.find_one({"_id": user_id})
    matches_played = user.get("stats", {}).get("matches_played", 0) if user else 0
    best_streak = user.get("stats", {}).get("best_streak", 0) if user else 0

    return {
        "total_predictions": grand_total,
        "correct_predictions": grand_correct,
        "accuracy": round(grand_correct / grand_total * 100, 1) if grand_total > 0 else 0.0,
        "total_points": grand_points,
        "best_streak": best_streak,
        "matches_played": matches_played,
        "by_type": by_type,
    }
