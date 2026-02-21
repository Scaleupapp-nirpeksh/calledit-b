"""Score Processor — resolves predictions, awards points, checks badges."""

import logging

from app.database import get_db
from app.services import prediction_service, notification_service, leaderboard_service
from app.utils.constants import BADGES, MilestoneType

logger = logging.getLogger(__name__)


async def process_ball_result(
    match_id: str, ball_key: str, outcome: str, over: int
) -> None:
    """Process a ball result: resolve predictions, check milestones, check badges."""
    count = await prediction_service.resolve_ball_predictions(
        match_id, ball_key, outcome, over
    )
    logger.info(f"Resolved {count} ball predictions for {ball_key} (outcome: {outcome})")

    # Check milestones after each delivery
    await _check_milestones(match_id)

    # Emit leaderboard update
    entries, _ = await leaderboard_service.get_match_leaderboard(match_id, limit=10)
    from app.websocket.events import emit_leaderboard_update
    await emit_leaderboard_update(match_id, entries)


async def process_over_result(
    match_id: str, innings: int, over: int, actual_runs: int
) -> None:
    """Process over completion: resolve over predictions."""
    count = await prediction_service.resolve_over_predictions(
        match_id, innings, over, actual_runs
    )
    logger.info(f"Resolved {count} over predictions for {innings}.{over} ({actual_runs} runs)")


async def process_match_result(match_id: str, winner: str) -> None:
    """Process match completion: resolve winner predictions, check badges, snapshot."""
    count = await prediction_service.resolve_match_winner_predictions(match_id, winner)
    logger.info(f"Resolved {count} match winner predictions for {match_id} (winner: {winner})")

    # Snapshot leaderboard to MongoDB
    from app.services.leaderboard_service import _match_key, snapshot_to_mongodb
    await snapshot_to_mongodb(_match_key(match_id), "match")

    # Check badges for all participants
    await _check_post_match_badges(match_id)

    # Increment matches_played for all users who predicted
    db = get_db()
    user_ids = await db.predictions.distinct("user_id", {"match_id": match_id})
    if user_ids:
        await db.users.update_many(
            {"_id": {"$in": user_ids}},
            {"$inc": {"stats.matches_played": 1}},
        )


async def _check_milestones(match_id: str) -> None:
    """Check if any player milestones have been reached and resolve related predictions.

    Scans the ball_log to compute cumulative batter runs and bowler wickets,
    then resolves milestone predictions when a threshold is first crossed.
    Uses a Redis set to track which milestones have already been resolved
    so we don't double-resolve on subsequent balls.
    """
    from app.redis_client import get_redis
    from app.services import match_service

    match = await match_service.get_match(match_id)
    if not match:
        return

    ball_log = match.get("ball_log", [])
    if not ball_log:
        return

    redis = get_redis()
    resolved_key = f"milestones_resolved:{match_id}"

    # Accumulate batter runs and bowler wickets from ball_log
    batter_runs: dict[str, int] = {}
    bowler_wickets: dict[str, int] = {}
    team_scores: dict[int, int] = {}

    for b in ball_log:
        batter = b.get("batter", "")
        bowler = b.get("bowler", "")
        innings = b.get("innings", 1)

        if batter:
            batter_runs[batter] = batter_runs.get(batter, 0) + b.get("batter_runs", 0)
        if bowler and b.get("is_wicket"):
            bowler_wickets[bowler] = bowler_wickets.get(bowler, 0) + 1
        team_scores[innings] = team_scores.get(innings, 0) + b.get("total_runs", 0)

    # Check batter milestones
    for batter, runs in batter_runs.items():
        if runs >= 100:
            mk = f"{MilestoneType.BATTER_100}:{batter}"
            if not await redis.sismember(resolved_key, mk):
                await prediction_service.resolve_milestone_predictions(
                    match_id, MilestoneType.BATTER_100, batter, True
                )
                await redis.sadd(resolved_key, mk)
                logger.info(f"Milestone resolved: {batter} scored 100+ ({runs} runs)")

        if runs >= 50:
            mk = f"{MilestoneType.BATTER_50}:{batter}"
            if not await redis.sismember(resolved_key, mk):
                await prediction_service.resolve_milestone_predictions(
                    match_id, MilestoneType.BATTER_50, batter, True
                )
                await redis.sadd(resolved_key, mk)
                logger.info(f"Milestone resolved: {batter} scored 50+ ({runs} runs)")

    # Check bowler milestones
    for bowler, wickets in bowler_wickets.items():
        if wickets >= 5:
            mk = f"{MilestoneType.BOWLER_5W}:{bowler}"
            if not await redis.sismember(resolved_key, mk):
                await prediction_service.resolve_milestone_predictions(
                    match_id, MilestoneType.BOWLER_5W, bowler, True
                )
                await redis.sadd(resolved_key, mk)
                logger.info(f"Milestone resolved: {bowler} took 5+ wickets ({wickets}w)")

        if wickets >= 3:
            mk = f"{MilestoneType.BOWLER_3W}:{bowler}"
            if not await redis.sismember(resolved_key, mk):
                await prediction_service.resolve_milestone_predictions(
                    match_id, MilestoneType.BOWLER_3W, bowler, True
                )
                await redis.sadd(resolved_key, mk)
                logger.info(f"Milestone resolved: {bowler} took 3+ wickets ({wickets}w)")

    # Check team score milestones
    for innings, score in team_scores.items():
        if score >= 200:
            batting_team = ""
            for inn_data in match.get("innings", []):
                if isinstance(inn_data, dict) and inn_data.get("innings_number") == innings:
                    batting_team = inn_data.get("batting_team", f"Team {innings}")
                    break
            if batting_team:
                mk = f"{MilestoneType.TEAM_200}:{batting_team}"
                if not await redis.sismember(resolved_key, mk):
                    await prediction_service.resolve_milestone_predictions(
                        match_id, MilestoneType.TEAM_200, batting_team, True
                    )
                    await redis.sadd(resolved_key, mk)
                    logger.info(f"Milestone resolved: {batting_team} scored 200+ ({score})")


async def _check_post_match_badges(match_id: str) -> None:
    """Check and award badges after match completion."""
    db = get_db()

    # Get all users who participated in this match
    user_ids = await db.predictions.distinct("user_id", {"match_id": match_id})

    for user_id in user_ids:
        user = await db.users.find_one({"_id": user_id})
        if not user:
            continue

        stats = user.get("stats", {})
        existing_badges = set(user.get("badges", []))
        new_badges = []

        # First prediction
        if "first_prediction" not in existing_badges and stats.get("total_predictions", 0) >= 1:
            new_badges.append("first_prediction")

        # Streak badges
        best_streak = stats.get("best_streak", 0)
        if "streak_5" not in existing_badges and best_streak >= 5:
            new_badges.append("streak_5")
        if "streak_10" not in existing_badges and best_streak >= 10:
            new_badges.append("streak_10")

        # Century (100+ points in a match)
        summary = await prediction_service.get_user_match_summary(user_id, match_id)
        if "century" not in existing_badges and summary.get("total_points", 0) >= 100:
            new_badges.append("century")

        # Clutch master
        if "clutch_master" not in existing_badges and stats.get("clutch_correct", 0) >= 5:
            new_badges.append("clutch_master")

        # Match winner oracle
        if "match_winner_3" not in existing_badges and stats.get("match_winners_correct", 0) >= 3:
            new_badges.append("match_winner_3")

        # Matches played
        matches = stats.get("matches_played", 0) + 1  # +1 for current
        if "matches_10" not in existing_badges and matches >= 10:
            new_badges.append("matches_10")
        if "matches_50" not in existing_badges and matches >= 50:
            new_badges.append("matches_50")

        # Top 10 in match leaderboard
        rank = await leaderboard_service.get_user_rank(
            user_id, f"lb:match:{match_id}"
        )
        if "top_10" not in existing_badges and rank is not None and rank <= 10:
            new_badges.append("top_10")

        # Award new badges
        if new_badges:
            await db.users.update_one(
                {"_id": user_id},
                {"$addToSet": {"badges": {"$each": new_badges}}},
            )

            # Create notifications for each badge
            for badge_key in new_badges:
                badge_info = BADGES.get(badge_key, {})
                await notification_service.create_notification(
                    user_id=user_id,
                    type="badge",
                    title=f"Badge Earned: {badge_info.get('name', badge_key)}",
                    body=badge_info.get("description", ""),
                    data={"badge_key": badge_key},
                )

            logger.info(f"User {user_id} earned {len(new_badges)} badges: {new_badges}")


# Import here to avoid circular import
from app.services import prediction_service
