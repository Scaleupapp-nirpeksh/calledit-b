"""AI Content Service — Claude API integration for match content generation."""

import logging
import time

import anthropic

from app.config import settings
from app.database import get_db
from app.services import match_service
from app.utils.helpers import generate_nanoid, utc_now

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (USD) — update as pricing changes
_COST_PER_1M_TOKENS = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}

_client: anthropic.AsyncAnthropic | None = None


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a Claude API call."""
    rates = _COST_PER_1M_TOKENS.get(model, {"input": 3.0, "output": 15.0})
    return round(
        (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000,
        6,
    )


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def generate_pre_match_brief(match_id: str) -> dict:
    """Generate a pre-match brief using Claude Sonnet (300-500 words)."""
    match = await match_service.get_match(match_id)
    if not match:
        raise ValueError("Match not found")

    prompt = f"""You are a cricket analyst for the CalledIt prediction app.
Write a pre-match brief for the following T20 match:

Match: {match['team1']} vs {match['team2']}
Venue: {match.get('venue', 'TBD')}
Date: {match.get('date', 'TBD')}
Competition: {match.get('competition_id', 'T20')}

Include:
- Key players to watch from each team
- Head-to-head record if known
- Venue conditions and likely pitch behavior
- Prediction tips for CalledIt users (what outcomes to expect)
- Which team has the edge and why

Keep it 300-500 words, engaging, and useful for prediction game players.
Use a conversational but knowledgeable tone."""

    start = time.monotonic()
    client = _get_client()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    content = response.content[0].text
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    tokens_used = input_tokens + output_tokens
    cost_usd = _estimate_cost("claude-sonnet-4-20250514", input_tokens, output_tokens)

    # Save to DB
    db = get_db()
    now = utc_now()
    ai_doc = {
        "_id": generate_nanoid(),
        "match_id": match_id,
        "type": "pre_match_brief",
        "content": content,
        "model_used": "claude-sonnet-4-20250514",
        "tokens_used": tokens_used,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "generation_time_ms": elapsed_ms,
        "created_at": now,
    }
    await db.ai_content.insert_one(ai_doc)

    # Update match with preview
    await db.matches.update_one(
        {"_id": match_id},
        {"$set": {"ai_preview": content, "updated_at": now}},
    )

    logger.info(f"Pre-match brief generated for {match_id}: {tokens_used} tokens, ${cost_usd}, {elapsed_ms}ms")
    return ai_doc


async def generate_post_match_report(match_id: str) -> dict:
    """Generate a post-match report using Claude Sonnet (500-800 words)."""
    match = await match_service.get_match(match_id)
    if not match:
        raise ValueError("Match not found")

    innings_summary = _build_innings_summary(match)
    scorecard_summary = _build_scorecard_summary(match)

    prompt = f"""You are a cricket analyst for the CalledIt prediction app.
Write a post-match report for the following completed T20 match:

Match: {match['team1']} vs {match['team2']}
Venue: {match.get('venue', '')}
Winner: {match.get('winner', 'TBD')}
Result: {match.get('result_text', '')}
Toss: {match.get('toss_winner', 'N/A')} won and chose to {match.get('toss_decision', 'N/A')}

{innings_summary}
{scorecard_summary}

Include:
- Match highlights and turning points
- Key performances (batting and bowling) — reference actual player stats
- Momentum shifts during the match
- How prediction patterns played out
- Fun stats (most predicted correctly, surprise outcomes)

Keep it 500-800 words, engaging post-match analysis style."""

    start = time.monotonic()
    client = _get_client()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    content = response.content[0].text
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    tokens_used = input_tokens + output_tokens
    cost_usd = _estimate_cost("claude-sonnet-4-20250514", input_tokens, output_tokens)

    db = get_db()
    now = utc_now()
    ai_doc = {
        "_id": generate_nanoid(),
        "match_id": match_id,
        "type": "post_match_report",
        "content": content,
        "model_used": "claude-sonnet-4-20250514",
        "tokens_used": tokens_used,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "generation_time_ms": elapsed_ms,
        "created_at": now,
    }
    await db.ai_content.insert_one(ai_doc)

    logger.info(f"Post-match report generated for {match_id}: {tokens_used} tokens, ${cost_usd}, {elapsed_ms}ms")
    return ai_doc


async def generate_ball_commentary(
    _match_id: str, ball_entry: dict, ml_probs: dict
) -> str:
    """Generate AI commentary for a significant ball using Claude Haiku (1-2 sentences)."""
    prompt = f"""You are a cricket commentator for the CalledIt prediction app.
Write 1-2 punchy sentences about this delivery:

Batter: {ball_entry.get('batter', '')}
Bowler: {ball_entry.get('bowler', '')}
Outcome: {ball_entry.get('outcome', '')}
Over: {ball_entry.get('over', '')}.{ball_entry.get('ball', '')}
{f"Wicket: {ball_entry.get('wicket_kind', '')} - {ball_entry.get('player_out', '')}" if ball_entry.get('is_wicket') else ""}

AI predicted probabilities: {ml_probs}

Make it exciting, mention the AI prediction angle if interesting. Keep under 50 words."""

    start = time.monotonic()
    client = _get_client()
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    commentary = response.content[0].text
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    tokens_used = input_tokens + output_tokens
    cost_usd = _estimate_cost("claude-haiku-4-5-20251001", input_tokens, output_tokens)

    logger.info(f"Ball commentary generated: {tokens_used} tokens, ${cost_usd}, {elapsed_ms}ms")
    return commentary


async def generate_over_summary(
    _match_id: str, innings: int, over: int, balls: list[dict]
) -> str:
    """Generate a summary for a completed over."""
    runs_in_over = sum(b.get("total_runs", 0) for b in balls)
    wickets_in_over = sum(1 for b in balls if b.get("is_wicket"))
    outcomes = [b.get("outcome", "dot") for b in balls]

    prompt = f"""Summarize this cricket over in 1-2 sentences:
Over {over}, Innings {innings}
Runs: {runs_in_over}, Wickets: {wickets_in_over}
Ball-by-ball outcomes: {', '.join(outcomes)}
Bowler: {balls[0].get('bowler', '') if balls else 'unknown'}

Be concise and insightful. Under 40 words."""

    client = _get_client()
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


def _build_innings_summary(match: dict) -> str:
    """Build a text summary of innings from match data."""
    lines = []
    # Try internal innings first, fall back to CricAPI score
    for i, innings in enumerate(match.get("innings", []), start=1):
        if isinstance(innings, dict):
            team = innings.get("batting_team", f"Team {i}")
            score = innings.get("score", 0)
            wickets = innings.get("wickets", 0)
            overs = innings.get("overs", 0)
            lines.append(f"Innings {i}: {team} - {score}/{wickets} in {overs} overs")
    if not lines:
        for s in match.get("score", []):
            lines.append(f"{s.get('inning', '?')}: {s.get('r', 0)}/{s.get('w', 0)} in {s.get('o', 0)} overs")
    return "\n".join(lines) if lines else "Innings data not available"


def _build_scorecard_summary(match: dict) -> str:
    """Build a text summary of batting/bowling from CricAPI scorecard."""
    scorecard = match.get("scorecard")
    if not scorecard:
        return ""

    lines = []
    for inn in scorecard:
        inning_label = inn.get("inning", "")
        lines.append(f"\n--- {inning_label} ---")

        # Top batters (30+ runs)
        for b in inn.get("batting", []):
            runs = b.get("r", 0)
            if runs >= 30:
                name = b.get("batsman", {}).get("name", "?")
                balls = b.get("b", 0)
                fours = b.get("4s", 0)
                sixes = b.get("6s", 0)
                sr = b.get("sr", 0)
                lines.append(f"  {name}: {runs}({balls}) [{fours}x4, {sixes}x6] SR {sr}")

        # Key bowlers (1+ wickets)
        for b in inn.get("bowling", []):
            wickets = b.get("w", 0)
            if wickets >= 1:
                name = b.get("bowler", {}).get("name", "?")
                overs = b.get("o", 0)
                runs = b.get("r", 0)
                eco = b.get("eco", 0)
                lines.append(f"  {name}: {wickets}/{runs} in {overs}ov (eco {eco})")

    return "\n".join(lines) if lines else ""
