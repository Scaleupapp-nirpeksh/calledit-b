"""Tests for CalledIt leaderboard system — Redis sorted sets."""

import pytest

from app.services import leaderboard_service


@pytest.mark.asyncio
class TestLeaderboardUpdates:
    async def test_update_score(self, setup_db, setup_redis, test_user, test_match):
        await leaderboard_service.update_score(
            test_user["_id"], test_match["_id"], 50
        )
        entries, total = await leaderboard_service.get_match_leaderboard(test_match["_id"])
        assert total == 1
        assert entries[0]["user_id"] == test_user["_id"]
        assert entries[0]["total_points"] == 50

    async def test_score_accumulates(self, setup_db, setup_redis, test_user, test_match):
        await leaderboard_service.update_score(test_user["_id"], test_match["_id"], 30)
        await leaderboard_service.update_score(test_user["_id"], test_match["_id"], 20)

        entries, _ = await leaderboard_service.get_match_leaderboard(test_match["_id"])
        assert entries[0]["total_points"] == 50

    async def test_ordering(self, setup_db, setup_redis, test_match):
        # Create two users in the leaderboard
        from app.utils.helpers import generate_nanoid, utc_now
        import app.database as db_module
        db = db_module._db
        now = utc_now()

        user_a = generate_nanoid()
        user_b = generate_nanoid()

        for uid, username in [(user_a, "player_a"), (user_b, "player_b")]:
            await db.users.insert_one({
                "_id": uid,
                "username": username,
                "display_name": username,
                "stats": {"correct_predictions": 0, "accuracy": 0.0},
                "created_at": now,
                "updated_at": now,
            })

        await leaderboard_service.update_score(user_a, test_match["_id"], 30)
        await leaderboard_service.update_score(user_b, test_match["_id"], 50)

        entries, _ = await leaderboard_service.get_match_leaderboard(test_match["_id"])
        assert entries[0]["user_id"] == user_b  # Higher score first
        assert entries[1]["user_id"] == user_a

    async def test_user_rank(self, setup_db, setup_redis, test_user, test_match):
        await leaderboard_service.update_score(test_user["_id"], test_match["_id"], 100)
        key = f"lb:match:{test_match['_id']}"
        rank = await leaderboard_service.get_user_rank(test_user["_id"], key)
        assert rank == 1

    async def test_league_scoping(self, setup_db, setup_redis, test_user, test_match):
        league_id = "test_league_001"
        await leaderboard_service.update_score(
            test_user["_id"], test_match["_id"], 75, league_ids=[league_id]
        )

        # Match leaderboard should have the score
        entries, _ = await leaderboard_service.get_match_leaderboard(test_match["_id"])
        assert entries[0]["total_points"] == 75

        # League leaderboard should also have the score
        entries, _ = await leaderboard_service.get_league_leaderboard(league_id)
        assert entries[0]["total_points"] == 75

        # League-match leaderboard too
        entries, _ = await leaderboard_service.get_league_match_leaderboard(
            league_id, test_match["_id"]
        )
        assert entries[0]["total_points"] == 75


@pytest.mark.asyncio
class TestLeaderboardNeighbours:
    async def test_get_neighbours(self, setup_db, setup_redis, test_match):
        from app.utils.helpers import generate_nanoid, utc_now
        import app.database as db_module
        db = db_module._db
        now = utc_now()

        users = []
        for i in range(5):
            uid = generate_nanoid()
            await db.users.insert_one({
                "_id": uid,
                "username": f"player_{i}",
                "display_name": f"Player {i}",
                "stats": {"correct_predictions": 0, "accuracy": 0.0},
                "created_at": now,
                "updated_at": now,
            })
            await leaderboard_service.update_score(uid, test_match["_id"], (i + 1) * 10)
            users.append(uid)

        # Get neighbours for middle user (3rd place)
        key = f"lb:match:{test_match['_id']}"
        neighbours = await leaderboard_service.get_user_neighbours(users[2], key, span=1)
        assert len(neighbours) == 3  # user above, self, user below
