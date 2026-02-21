"""Pytest fixtures for CalledIt backend tests."""

import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.utils.helpers import generate_nanoid, generate_referral_code, hash_phone, utc_now


# Use a separate test database
TEST_DB_NAME = "calledit_test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def mongo_client():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    yield client
    # Clean up test database after all tests
    try:
        await client.drop_database(TEST_DB_NAME)
    except RuntimeError:
        pass  # Event loop may already be closed during teardown
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db(mongo_client):
    """Patch database to use test DB and clean collections before each test."""
    import app.database as db_module
    db_module._db = mongo_client[TEST_DB_NAME]

    # Clean all collections before each test
    db = mongo_client[TEST_DB_NAME]
    collections = await db.list_collection_names()
    for coll in collections:
        await db[coll].delete_many({})

    yield


@pytest_asyncio.fixture
async def setup_redis():
    """Connect Redis for tests (uses same Redis but different key prefix)."""
    from app.redis_client import connect_redis, close_redis, get_redis
    await connect_redis()
    redis = get_redis()
    yield redis
    # Clean test keys
    keys = await redis.keys("*")
    if keys:
        await redis.delete(*keys)
    await close_redis()


@pytest_asyncio.fixture
async def test_user(setup_db):
    """Create a test user."""
    import app.database as db_module
    db = db_module._db
    now = utc_now()
    user = {
        "_id": generate_nanoid(),
        "phone_hash": hash_phone("+919876543210"),
        "phone_encrypted": "+919876543210",
        "username": "testuser",
        "display_name": "Test User",
        "avatar_url": None,
        "favourite_team": "CSK",
        "favourite_players": [],
        "referral_code": generate_referral_code(),
        "referred_by": None,
        "is_onboarded": True,
        "is_admin": False,
        "stats": {
            "total_predictions": 0,
            "correct_predictions": 0,
            "accuracy": 0.0,
            "total_points": 0,
            "current_streak": 0,
            "best_streak": 0,
            "matches_played": 0,
            "clutch_correct": 0,
            "match_winners_correct": 0,
        },
        "badges": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user)
    return user


@pytest_asyncio.fixture
async def test_match(setup_db, setup_redis):
    """Create a test match in live state with prediction window open."""
    import app.database as db_module
    from app.utils.constants import MatchStatus, PREDICTION_WINDOW_SECONDS
    db = db_module._db
    now = utc_now()
    match = {
        "_id": generate_nanoid(),
        "cricapi_id": None,
        "name": "CSK vs MI - IPL 2026",
        "match_type": "T20",
        "status": MatchStatus.LIVE_1ST,
        "venue": "Chepauk",
        "date": now.isoformat(),
        "team1": "Chennai Super Kings",
        "team2": "Mumbai Indians",
        "team1_code": "CSK",
        "team2_code": "MI",
        "toss_winner": "Chennai Super Kings",
        "toss_decision": "bat",
        "innings": [],
        "ball_log": [],
        "winner": None,
        "result_text": None,
        "ai_preview": None,
        "prediction_window_open": True,
        "current_innings": 1,
        "current_over": 1,
        "current_ball": 1,
        "win_probability_timeline": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.matches.insert_one(match)
    # Also set the prediction window in Redis (match_service checks Redis, not DB)
    await setup_redis.setex(f"pred_window:{match['_id']}", PREDICTION_WINDOW_SECONDS, "open")
    return match


@pytest_asyncio.fixture
async def async_client(setup_db):
    """Create an async HTTP test client."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
