from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_staff, require_role
from app.crud.scoring import (
    submit_deduction, all_judges_submitted, get_judge_score_summary
)
from app.models.admin_user import AdminRole
from app.models.audit import AuditLog, AuditAction
from app.schemas.scoring import (
    DeductionEventCreate, DeductionEventRead, JudgeScoreSummary,
    RoundQuestionCreate, RoundQuestionRead, OfficialSheetRead,
    RubricModeUpdate, RubricModeResponse,
)
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

@router.delete("/deductions/{deduction_id}", response_model=DeductionEventRead)
async def delete_deduction_event(
    deduction_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff_data=Depends(get_current_staff),
):
    """Allows a judge or admin to undo/delete an accidental deduction."""
    from app.crud.scoring import delete_deduction
    staff, _ = staff_data
    event = await delete_deduction(db, judge_id=staff.id, deduction_id=deduction_id)

    db.add(AuditLog(
        actor_id=staff.id,
        action=AuditAction.DELETE,
        module="scoring",
        target_record_id=deduction_id,
        ip_address=request.client.host if request.client else "127.0.0.1",
        payload={
            "round_id": event.round_id,
            "student_id": event.student_id,
            "deduction_type_id": event.deduction_type_id,
            "amount": event.amount,
        },
    ))
    await db.flush()

    from app.core.websocket_manager import ws_manager
    await ws_manager.broadcast_admin({
        "type": "SCORE_UPDATED",
        "round_id": event.round_id,
        "student_id": event.student_id,
    })

    await db.commit()
    return event


@router.post("/rounds/{round_id}/students/{student_id}/questions", response_model=RoundQuestionRead)
async def set_round_question(
    round_id: int,
    student_id: int,
    data: RoundQuestionCreate,
    db: AsyncSession = Depends(get_db),
    staff_data=Depends(get_current_staff),
):
    """Saves or updates Surah, Ayah range, and Envelope number for a question."""
    from app.crud.scoring import upsert_round_question
    data.round_id = round_id
    data.student_id = student_id
    res = await upsert_round_question(db, data)
    await db.commit()
    return res


@router.get("/rounds/{round_id}/students/{student_id}/questions", response_model=list[RoundQuestionRead])
async def list_round_questions(
    round_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_staff),
):
    from app.crud.scoring import get_round_questions
    return await get_round_questions(db, round_id, student_id)


@router.get("/rounds/{round_id}/students/{student_id}/sheet", response_model=OfficialSheetRead)
async def get_official_sheet(
    round_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    staff_data=Depends(get_current_staff),
):
    """Returns all data formatted for the official Saudi Embassy / Jamia Mosque rubric sheet."""
    from app.crud.scoring import get_official_sheet_data
    staff, _ = staff_data
    return await get_official_sheet_data(db, round_id, student_id, staff.id)


from pydantic import BaseModel

class DeductionTypeOut(BaseModel):
    id: int
    name_en: str
    name_ar: str
    points_deducted: float | None
    criteria_name: str

class CriteriaListOut(BaseModel):
    rubric_mode: str = "OFFICIAL_70_30"
    deduction_types: list[DeductionTypeOut]

@router.get("/rounds/{round_id}/deduction-types", response_model=CriteriaListOut)
async def get_round_deduction_types(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_staff),
):
    from sqlmodel import select
    from app.models.round import Round
    from app.models.category import Category, ScoringCriteria, DeductionType
    from app.services.rubric_manager import get_current_rubric_mode
    
    rubric_mode = await get_current_rubric_mode(db)

    # 1. Get round
    round_ = await db.get(Round, round_id)
    if not round_:
        from fastapi import HTTPException
        raise HTTPException(404, "Round not found")
        
    # 2. Get category to find category_group
    from app.models.category import CategoryGroup
    category = await db.get(Category, round_.category_id)
    cat_group = category.category_group if category else CategoryGroup.JUZ_10_15_20
    
    # 3. Fetch all deduction types for this category group
    results = await db.execute(
        select(DeductionType, ScoringCriteria).join(
            ScoringCriteria, DeductionType.scoring_criteria_id == ScoringCriteria.id
        ).where(
            ScoringCriteria.category_group == cat_group
        )
    )
    
    out = []
    for dt, crit in results.all():
        out.append(DeductionTypeOut(
            id=dt.id,
            name_en=dt.name_en,
            name_ar=dt.name_ar,
            points_deducted=dt.points_deducted,
            criteria_name=crit.name_en
        ))
    return CriteriaListOut(rubric_mode=rubric_mode, deduction_types=out)


@router.get("/rubric-mode", response_model=RubricModeResponse)
async def get_active_rubric_mode(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_staff),
):
    """Returns the currently active competition rubric mode (OFFICIAL_70_30 or TRADITIONAL_TIERED)."""
    from app.services.rubric_manager import get_current_rubric_mode
    mode = await get_current_rubric_mode(db)
    return RubricModeResponse(rubric_mode=mode)


@router.post("/rubric-mode", response_model=RubricModeResponse)
async def set_active_rubric_mode(
    data: RubricModeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff_data=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """
    SuperAdmin/Moderator toggles between OFFICIAL_70_30 and TRADITIONAL_TIERED rubrics.
    Synchronizes criteria and deduction types and broadcasts real-time change.
    """
    from app.services.rubric_manager import set_rubric_mode
    staff = staff_data
    mode = await set_rubric_mode(db, data.rubric_mode)

    db.add(AuditLog(
        actor_id=staff.id,
        action=AuditAction.UPDATE,
        module="scoring",
        target_record_id=0,
        ip_address=request.client.host if request.client else "127.0.0.1",
        payload={"action": "CHANGE_RUBRIC_MODE", "rubric_mode": mode},
    ))
    await db.commit()
    return RubricModeResponse(rubric_mode=mode)

