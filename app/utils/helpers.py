import hashlib
import secrets
import string
from datetime import datetime, timezone

from app.utils.constants import BallOutcome


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_nanoid(length: int = 21) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_referral_code() -> str:
    return generate_nanoid(8).upper()


def hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()


def mask_phone(phone: str) -> str:
    if len(phone) < 6:
        return "***"
    return phone[:3] + "*" * (len(phone) - 5) + phone[-2:]


def classify_delivery_outcome(delivery: dict) -> BallOutcome:
    """Classify a Cricsheet/CricAPI delivery dict into one of 7 outcomes."""
    # Check for wicket first
    if delivery.get("wickets") or delivery.get("isWicket"):
        return BallOutcome.WICKET

    # Get batter runs (exclude extras)
    batter_runs = 0
    if "runs" in delivery and isinstance(delivery["runs"], dict):
        batter_runs = delivery["runs"].get("batter", 0)
    elif "batter_runs" in delivery:
        batter_runs = delivery["batter_runs"]
    elif "batsman_run" in delivery:
        batter_runs = delivery["batsman_run"]

    mapping = {0: BallOutcome.DOT, 1: BallOutcome.ONE, 2: BallOutcome.TWO,
               3: BallOutcome.THREE, 4: BallOutcome.FOUR, 6: BallOutcome.SIX}
    return mapping.get(batter_runs, BallOutcome.DOT)


def ball_key(innings: int, over: int, ball: int) -> str:
    return f"{innings}.{over}.{ball}"


def over_key(innings: int, over: int) -> str:
    return f"{innings}.{over}"


def get_match_phase(over: int) -> str:
    """Return the match phase for a given over (1-indexed)."""
    if over <= 6:
        return "powerplay"
    elif over <= 14:
        return "middle"
    else:
        return "death"
