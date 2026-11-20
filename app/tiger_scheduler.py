"""Schedule APIs for saved records and the existing session-based page.

/api/saved-schedules stores schedules in Supabase for the signed-in account.
/api/schedules supports the existing prototype page and its in-memory events.
The prototype page still requires integration with the saved-schedule API.
"""

from copy import deepcopy
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from tiger_auth import Session, current_session
from tiger_catalog import load_courses
from tiger_models import (
    Classes,
    CoursePreset,
    CourseSelection,
    Schedule,
    ScheduleDefinition,
    ScheduleEvent,
    ScheduleEventData,
    ScheduleIn,
    ScheduleMetrics,
    ScheduleOut,
    SchedulePageData,
    SharedFreeTimeDay,
    SharedFreeTimePeriod,
    SharedFreeTimeRequest,
    SharedFreeTimeResponse,
    UserBase,
)

router: APIRouter = APIRouter(prefix="/api", tags=["Schedules"])


# Supabase-backed operations use their own paths to avoid colliding with the page.
def _to_out(row: dict[str, Any]) -> ScheduleOut:
    return ScheduleOut(
        id=row["id"],
        name=row["name"],
        semester=row["semester"],
        sections=row.get("sections") or [],
        commitments=row.get("commitments") or [],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _payload(schedule: ScheduleIn) -> dict[str, Any]:
    return {
        "name": schedule.name,
        "semester": schedule.semester,
        "sections": [s.model_dump() for s in schedule.sections],
        "commitments": [c.model_dump() for c in schedule.commitments],
    }


@router.post("/saved-schedules")
def create_saved_schedule(schedule: ScheduleIn, session: Session = Depends(current_session)) -> ScheduleOut:
    row = {**_payload(schedule), "user_id": session.user_id}
    data = session.db.table("schedules").insert(row).execute().data
    if not data:
        raise HTTPException(status_code=400, detail="Could not save schedule")
    return _to_out(data[0])


@router.get("/saved-schedules")
def list_saved_schedules(session: Session = Depends(current_session)) -> list[ScheduleOut]:
    data = (
        session.db.table("schedules").select("*")
        .eq("user_id", session.user_id).order("updated_at", desc=True)
        .execute().data
    )
    return [_to_out(r) for r in (data or [])]


@router.get("/saved-schedules/{schedule_id}")
def get_saved_schedule(schedule_id: str, session: Session = Depends(current_session)) -> ScheduleOut:
    data = (
        session.db.table("schedules").select("*")
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_out(data[0])


@router.put("/saved-schedules/{schedule_id}")
def update_saved_schedule(schedule_id: str, schedule: ScheduleIn, session: Session = Depends(current_session)) -> ScheduleOut:
    changes = {**_payload(schedule), "updated_at": datetime.now(timezone.utc).isoformat()}
    data = (
        session.db.table("schedules").update(changes)
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
