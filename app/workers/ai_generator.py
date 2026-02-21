"""AI Generator — background tasks for AI content generation."""

import logging

from app.services import ai_content_service

logger = logging.getLogger(__name__)


async def generate_pre_match_content(match_id: str) -> None:
    """Generate pre-match AI brief. Called before match starts."""
    try:
        result = await ai_content_service.generate_pre_match_brief(match_id)
        logger.info(f"Pre-match content generated for {match_id}: {result['_id']}")
    except Exception as e:
        logger.error(f"Pre-match content generation failed for {match_id}: {e}")


async def generate_ball_commentary(
    match_id: str, ball_entry: dict, ml_probs: dict
) -> str | None:
    """Generate AI commentary for a significant ball."""
    try:
        commentary = await ai_content_service.generate_ball_commentary(
            match_id, ball_entry, ml_probs
        )
        return commentary
    except Exception as e:
        logger.error(f"Ball commentary generation failed: {e}")
        return None


async def generate_post_match_content(match_id: str) -> None:
    """Generate post-match AI report. Called after match completion."""
    try:
        result = await ai_content_service.generate_post_match_report(match_id)
        logger.info(f"Post-match content generated for {match_id}: {result['_id']}")
    except Exception as e:
        logger.error(f"Post-match content generation failed for {match_id}: {e}")
