"""Save and read each student's GPA forecast in the Supabase forecasts table."""

from datetime import datetime, timezone

from models.tiger_planning import PlanningResult
from models.tiger_session import Session

TABLE: str = "forecasts"


def read_forecast(session: Session) -> PlanningResult | None:
    """Read the signed-in student's saved forecast.

    Args:
        session: Verified student and their database client.

    Returns:
        The saved forecast, or None when missing, invalid or unavailable.
    """
    try:
        rows = (
            session.db.table(TABLE)
            .select("result")
            .eq("user_id", session.user_id)
            .limit(1)
            .execute()
            .data
        )
        return PlanningResult.model_validate(rows[0]["result"]) if rows else None
    except Exception:
        # Invalid or unavailable storage must never break a page.
        return None


def save_forecast(session: Session, result: PlanningResult) -> bool:
    """Store only the computed forecast for the signed-in student.

    Args:
        session: Verified student and their database client.
        result: Computed forecast; course names and raw inputs are not stored.

    Returns:
        True when saved, False when the database could not store it.
    """
    row: dict[str, object] = {
        "user_id": session.user_id,
        "result": result.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        session.db.table(TABLE).upsert(row, on_conflict="user_id").execute()
    except Exception:
        return False
    return True
