from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_staff, require_role
from app.crud.scoring import (
    submit_deduction, all_judges_submitted, get_judge_score_summary
)
from app.models.admin_user import AdminRole
from app.models.audit import AuditLog, AuditAction
from app.schemas.scoring import DeductionEventCreate, DeductionEventRead, JudgeScoreSummary
from app.services.ranking_engine import finalize_and_broadcast

router = APIRouter(prefix="/scoring", tags=["Scoring"])


@router.post("/deductions", response_model=DeductionEventRead, status_code=201)
async def submit_deduction_event(
    data: DeductionEventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff_data=Depends(get_current_staff),
):
    """
    Submit a deduction event as a judge.

    After successful submission:
    - If ALL assigned judges for this round+student have now submitted → ranking
      engine fires automatically and WebSocket broadcast is sent.
    - Score visibility: judge cannot see panel results until all have submitted.
    """
    staff, token_payload = staff_data

    # Judges can only score their assigned rounds (enforced via token claim)
    if staff.role == AdminRole.JUDGE:
        assigned_rounds = token_payload.get("assigned_round_ids", [])
        if data.round_id not in assigned_rounds:
            from fastapi import HTTPException
            raise HTTPException(403, "You are not assigned to this round")

    event = await submit_deduction(db, judge_id=staff.id, data=data)

    # Audit every scoring action
    db.add(AuditLog(
        actor_id=staff.id,
        action=AuditAction.CREATE,
        module="scoring",
        target_record_id=event.id,
        ip_address=request.client.host,
        payload={
            "round_id": data.round_id,
            "student_id": data.student_id,
            "deduction_type_id": data.deduction_type_id,
            "amount": event.amount,
        },
    ))
    await db.flush()

    # Check if this was the last judge — trigger ranking engine if so
    if await all_judges_submitted(db, data.round_id, data.student_id):
        await finalize_and_broadcast(db, data.round_id, data.student_id)

    # Always broadcast a real-time update to moderators/admins
    from app.core.websocket_manager import ws_manager
    await ws_manager.broadcast_admin({
        "type": "SCORE_UPDATED",
        "round_id": data.round_id,
        "student_id": data.student_id,
    })

    await db.commit()
    return event


@router.get(
    "/rounds/{round_id}/students/{student_id}/my-score",
    response_model=JudgeScoreSummary,
)
async def get_my_score(
    round_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    staff_data=Depends(get_current_staff),
):
    """
    Returns the requesting judge's own score breakdown.
    panel_score is ONLY included when ALL assigned judges have submitted.
    Other judges' scores are never revealed until then.
    """
    staff, _ = staff_data
    return await get_judge_score_summary(db, round_id, student_id, staff.id)
