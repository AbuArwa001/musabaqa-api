import re

with open("app/api/v1/routes/results.py", "r") as f:
    content = f.read()

# Replace the dependency
content = content.replace("from app.api.deps import get_db, require_role",
                          "from app.api.deps import get_db, require_role, get_current_actor\nfrom app.models.student import Student")

old_func = """@router.get("/students/{student_id}", response_model=list[RoundResultRead])
async def get_student_results(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    return (await db.execute(
        select(RoundResult).where(RoundResult.student_id == student_id)
    )).scalars().all()"""

new_func = """@router.get("/students/{student_id}", response_model=list[RoundResultRead])
async def get_student_results(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_actor),
):
    scope, user = actor
    if scope == "institution":
        # Check if the student belongs to the institution
        student = await db.get(Student, student_id)
        from fastapi import HTTPException
        if not student or student.institution_id != user.id:
            raise HTTPException(403, "You can only view results for your own students")
    elif scope == "staff":
        if user.role not in (AdminRole.SUPERADMIN, AdminRole.MODERATOR):
            from fastapi import HTTPException
            raise HTTPException(403, "Requires SUPERADMIN or MODERATOR role")
            
    return (await db.execute(
        select(RoundResult).where(RoundResult.student_id == student_id)
    )).scalars().all()"""

content = content.replace(old_func, new_func)

with open("app/api/v1/routes/results.py", "w") as f:
    f.write(content)
