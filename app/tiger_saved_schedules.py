"""
Build API routes and database functions that let signed-in students create, save, reopen, edit, and delete schedules.
Store the schedule name, semester, and selected class sections in Supabase.
Determine ownership from the signed-in account and prevent students from accessing or modifying another student's schedules
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from tiger_auth import Session, current_session
from tiger_models import ScheduleIn, ScheduleOut

# Initialize the router for this specific module
router = APIRouter(tags=["Saved Schedules"])


def _to_out(row: dict) -> ScheduleOut:
    return ScheduleOut(
        id=row["id"],
        name=row["name"],
        semester=row["semester"],
        sections=row.get("sections") or [],
        commitments=row.get("commitments") or [],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _to_minutes(value: str) -> int:
    try:
        hours, minutes = value.split(":")
        return int(hours) * 60 + int(minutes)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Times must look like HH:MM, got '{value}'")


def _ensure_no_conflicts(schedule: ScheduleIn) -> None:
    """Reject a schedule where two meetings or commitments overlap on the same day."""
    blocks = []
    for section in schedule.sections:
        label = f"{section.department} {section.number}"
        blocks += [(label, m.days, m.start, m.end) for m in section.meetings]
    blocks += [(c.name, c.days, c.start, c.end) for c in schedule.commitments]
    spans = [(label, set(days), _to_minutes(start), _to_minutes(end)) for label, days, start, end in blocks]
    for i, (name_a, days_a, start_a, end_a) in enumerate(spans):
        for name_b, days_b, start_b, end_b in spans[i + 1:]:
            if days_a & days_b and start_a < end_b and start_b < end_a:
                raise HTTPException(status_code=409, detail=f"Schedule conflict: {name_a} overlaps {name_b}")


def _payload(schedule: ScheduleIn) -> dict:
    return {
        "name": schedule.name,
        "semester": schedule.semester,
        "sections": [s.model_dump() for s in schedule.sections],
        "commitments": [c.model_dump() for c in schedule.commitments],
    }


@router.post("/schedules")
def create_schedule(schedule: ScheduleIn, session: Session = Depends(current_session)) -> ScheduleOut:
    _ensure_no_conflicts(schedule)
    row = {**_payload(schedule), "user_id": session.user_id}
    data = session.db.table("schedules").insert(row).execute().data
    if not data:
        raise HTTPException(status_code=400, detail="Could not save schedule")
    return _to_out(data[0])


@router.get("/schedules")
def list_schedules(session: Session = Depends(current_session)) -> list[ScheduleOut]:
    data = (
        session.db.table("schedules").select("*")
        .eq("user_id", session.user_id).order("updated_at", desc=True)
        .execute().data
    )
    return [_to_out(r) for r in data]


@router.get("/schedules/{schedule_id}")
def get_schedule(schedule_id: str, session: Session = Depends(current_session)) -> ScheduleOut:
    data = (
        session.db.table("schedules").select("*")
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_out(data[0])


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: str, schedule: ScheduleIn, session: Session = Depends(current_session)) -> ScheduleOut:
    changes = {**_payload(schedule), "updated_at": datetime.now(timezone.utc).isoformat()}
    data = (
        session.db.table("schedules").update(changes)
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_out(data[0])


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, session: Session = Depends(current_session)) -> dict:
    data = (
        session.db.table("schedules").delete()
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"deleted": True}
