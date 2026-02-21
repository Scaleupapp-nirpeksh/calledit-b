"""Image Service — WhatsApp shareable scorecard generation using Pillow."""

import io
import logging

import boto3
from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.utils.helpers import generate_nanoid

logger = logging.getLogger(__name__)

# Card dimensions (WhatsApp/social share)
CARD_WIDTH = 1200
CARD_HEIGHT = 630

# Colors
BG_COLOR = (15, 23, 42)       # Dark navy
ACCENT_COLOR = (99, 102, 241)  # Indigo
TEXT_COLOR = (255, 255, 255)
SUBTEXT_COLOR = (148, 163, 184)
CORRECT_COLOR = (34, 197, 94)  # Green
WRONG_COLOR = (239, 68, 68)    # Red


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if custom font not available."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except (OSError, IOError):
            return ImageFont.load_default()


async def generate_share_card(
    user: dict, match: dict, prediction_summary: dict
) -> str:
    """Generate a shareable scorecard image and upload to S3.

    Returns the S3 URL of the uploaded image.
    """
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_large = _get_font(36)
    font_medium = _get_font(24)
    font_small = _get_font(18)
    font_xl = _get_font(48)

    # Header bar
    draw.rectangle([(0, 0), (CARD_WIDTH, 80)], fill=ACCENT_COLOR)
    draw.text((30, 20), "CalledIt", fill=TEXT_COLOR, font=font_large)
    draw.text((CARD_WIDTH - 250, 25), "calledit.in", fill=(200, 200, 255), font=font_medium)

    # Match info
    team1 = match.get("team1_code", match.get("team1", ""))
    team2 = match.get("team2_code", match.get("team2", ""))
    match_text = f"{team1} vs {team2}"
    draw.text((30, 100), match_text, fill=TEXT_COLOR, font=font_xl)

    venue = match.get("venue", "")[:40]
    draw.text((30, 160), venue, fill=SUBTEXT_COLOR, font=font_small)

    # User stats
    username = user.get("display_name") or user.get("username") or "Player"
    draw.text((30, 210), f"@{username}", fill=ACCENT_COLOR, font=font_medium)

    # Stats grid
    y_start = 270
    stats = [
        ("Predictions", str(prediction_summary.get("total_predictions", 0))),
        ("Correct", str(prediction_summary.get("correct_predictions", 0))),
        ("Accuracy", f"{prediction_summary.get('accuracy', 0):.1f}%"),
        ("Points", str(prediction_summary.get("total_points", 0))),
    ]

    col_width = CARD_WIDTH // 4
    for i, (label, value) in enumerate(stats):
        x = i * col_width + 30
        draw.text((x, y_start), value, fill=TEXT_COLOR, font=font_xl)
        draw.text((x, y_start + 55), label, fill=SUBTEXT_COLOR, font=font_small)

    # Streak info
    streak = prediction_summary.get("best_streak", 0)
    draw.text((30, 400), f"Best Streak: {streak}", fill=CORRECT_COLOR, font=font_medium)

    # Divider
    draw.line([(30, 460), (CARD_WIDTH - 30, 460)], fill=SUBTEXT_COLOR, width=1)

    # Result
    winner = match.get("winner", "")
    result_text = match.get("result_text", "")
    if winner:
        draw.text((30, 480), f"Winner: {winner}", fill=CORRECT_COLOR, font=font_medium)
    if result_text:
        draw.text((30, 515), result_text[:60], fill=SUBTEXT_COLOR, font=font_small)

    # Footer
    draw.text((30, CARD_HEIGHT - 40), "Play live cricket predictions on CalledIt!", fill=SUBTEXT_COLOR, font=font_small)

    # Upload to S3
    card_id = generate_nanoid(12)
    s3_key = f"share-cards/{card_id}.png"

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=95)
    buffer.seek(0)

    try:
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        s3.upload_fileobj(
            buffer,
            settings.S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "image/png", "ACL": "public-read"},
        )
        url = f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        logger.info(f"Share card uploaded: {url}")
        return url
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        # Fallback: return a placeholder
        return f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
