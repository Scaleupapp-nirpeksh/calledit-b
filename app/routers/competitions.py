"""Competition/Tournament API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_admin
from app.models.competition import CreateCompetitionRequest
from app.services import competition_service

router = APIRouter(prefix="/competitions", tags=["Competitions"])


@router.get("")
async def list_competitions(
    is_active: Optional[bool] = Query(None),
    season: Optional[str] = Query(None),
):
    """List all competitions, optionally filtered."""
    comps = await competition_service.get_competitions(
        is_active=is_active, season=season
    )
    return {
        "competitions": [_format(c) for c in comps],
        "total": len(comps),
    }


@router.get("/{competition_id}")
async def get_competition(competition_id: str):
    """Get competition details."""
    comp = await competition_service.get_competition(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    return _format(comp)


@router.get("/{competition_id}/matches")
async def get_competition_matches(competition_id: str):
    """Get all matches in a competition."""
    comp = await competition_service.get_competition(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    matches = await competition_service.get_competition_matches(competition_id)
    return {
        "competition": _format(comp),
        "matches": matches,
        "total": len(matches),
    }


@router.post("")
async def create_competition(
    body: CreateCompetitionRequest,
    admin: dict = Depends(get_current_admin),
):
    """Create a new platform-seeded competition (admin only)."""
    comp = await competition_service.create_competition(
        name=body.name,
        short_name=body.short_name,
        match_type=body.match_type,
        season=body.season,
        start_date=body.start_date,
        end_date=body.end_date,
        teams=body.teams,
    )
    return _format(comp)


def _format(comp: dict) -> dict:
    """Format competition document for API response."""
    return {
        "id": comp["_id"],
        "name": comp.get("name"),
        "short_name": comp.get("short_name"),
        "match_type": comp.get("match_type"),
        "season": comp.get("season"),
        "start_date": comp.get("start_date"),
        "end_date": comp.get("end_date"),
        "is_active": comp.get("is_active", True),
        "is_platform_seeded": comp.get("is_platform_seeded", True),
        "teams": comp.get("teams", []),
        "match_count": comp.get("match_count", 0),
        "created_at": comp.get("created_at"),
        "updated_at": comp.get("updated_at"),
    }
