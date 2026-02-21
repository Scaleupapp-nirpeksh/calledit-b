"""CalledIt — Export completed match data from MongoDB to Cricsheet-compatible JSON.

Exports ball_log from completed matches into the same JSON format used by
Cricsheet training data, so it can be combined with static data for retraining.

Usage: python -m scripts.export_live_data [--output-dir exports/]
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, ".")
from app.config import settings
from app.utils.constants import MatchStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _convert_ball_log_to_cricsheet(match: dict) -> dict | None:
    """Convert a CalledIt match document to Cricsheet JSON format."""
    ball_log = match.get("ball_log", [])
    if not ball_log:
        return None

    team1 = match.get("team1", "")
    team2 = match.get("team2", "")
    toss_winner = match.get("toss_winner")
    toss_decision = match.get("toss_decision")

    # Group balls by innings
    innings_map: dict[int, list[dict]] = {}
    for ball in ball_log:
        inn = ball.get("innings", 1)
        innings_map.setdefault(inn, []).append(ball)

    innings_list = []
    for inn_num in sorted(innings_map.keys()):
        balls = innings_map[inn_num]
        # Determine batting team from innings data or match innings
        match_innings = match.get("innings", [])
        if inn_num <= len(match_innings):
            batting_team = match_innings[inn_num - 1].get("batting_team", team1 if inn_num == 1 else team2)
        else:
            batting_team = team1 if inn_num == 1 else team2

        # Group by over
        overs_map: dict[int, list[dict]] = {}
        for b in balls:
            over_num = b.get("over", 1) - 1  # Convert 1-indexed back to 0-indexed
            overs_map.setdefault(over_num, []).append(b)

        overs_list = []
        for over_num in sorted(overs_map.keys()):
            deliveries = []
            for b in overs_map[over_num]:
                delivery = {
                    "batter": b.get("batter", ""),
                    "bowler": b.get("bowler", ""),
                    "non_striker": b.get("non_striker", ""),
                    "runs": {
                        "batter": b.get("batter_runs", 0),
                        "extras": b.get("extras", 0),
                        "total": b.get("total_runs", 0),
                    },
                }
                if b.get("is_wicket"):
                    delivery["wickets"] = [{
                        "player_out": b.get("player_out", ""),
                        "kind": b.get("wicket_kind", ""),
                    }]
                deliveries.append(delivery)

            overs_list.append({"over": over_num, "deliveries": deliveries})

        innings_list.append({"team": batting_team, "overs": overs_list})

    # Build Cricsheet-compatible JSON
    cricsheet_doc = {
        "info": {
            "teams": [team1, team2],
            "match_type": match.get("match_type", "T20"),
            "venue": match.get("venue", ""),
            "dates": [match.get("date", "")[:10]],
            "toss": {
                "winner": toss_winner or "",
                "decision": toss_decision or "",
            },
            "outcome": {},
        },
        "innings": innings_list,
    }

    # Add outcome
    winner = match.get("winner")
    if winner:
        cricsheet_doc["info"]["outcome"]["winner"] = winner

    return cricsheet_doc


async def export_matches(output_dir: Path):
    """Export all completed matches from MongoDB."""
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]

    output_dir.mkdir(parents=True, exist_ok=True)

    cursor = db.matches.find({
        "status": MatchStatus.COMPLETED,
        "ball_log": {"$exists": True, "$ne": []},
    })

    exported = 0
    skipped = 0

    async for match in cursor:
        match_id = match["_id"]
        cricsheet = _convert_ball_log_to_cricsheet(match)
        if not cricsheet:
            skipped += 1
            continue

        out_path = output_dir / f"live_{match_id}.json"
        with open(out_path, "w") as f:
            json.dump(cricsheet, f, indent=2, default=str)
        exported += 1

    logger.info(f"Exported {exported} matches to {output_dir} (skipped {skipped} with no ball_log)")
    client.close()
    return exported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export live match data for retraining")
    parser.add_argument("--output-dir", default="exports/live_matches",
                        help="Directory to write exported JSON files")
    args = parser.parse_args()

    asyncio.run(export_matches(Path(args.output_dir)))
