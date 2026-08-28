import re

with open("app/crud/scoring.py", "r") as f:
    content = f.read()

# We need to change the logic in get_judge_score_summary
old_logic = """    panel_score = None
    if all_submitted:
        # Compute panel average from all judges
        all_judge_ids = await get_all_assigned_judge_ids(db, round_id)
        judge_totals = []
        for jid in all_judge_ids:
            j_events = await get_judge_deductions_for_student(db, round_id, student_id, jid)
            j_deductions: dict[int, float] = defaultdict(float)
            for e in j_events:
                j_deductions[e.deduction_type_id] += e.amount
            j_total = 0.0
            for crit_id, (_, max_pts) in crit_max.items():
                deducted = sum(
                    amt for dt_id, amt in j_deductions.items()
                    if dt_to_crit.get(dt_id) == crit_id
                )
                j_total += max(0.0, max_pts - deducted)
            judge_totals.append(j_total)
        panel_score = sum(judge_totals) / len(judge_totals) if judge_totals else None"""

new_logic = """    from app.models.admin_user import AdminUser, AdminRole
    user = await db.get(AdminUser, requesting_judge_id)
    is_moderator = user and user.role in (AdminRole.SUPERADMIN, AdminRole.MODERATOR)

    panel_score = None
    if all_submitted or is_moderator:
        # Compute panel average from all judges
        all_judge_ids = await get_all_assigned_judge_ids(db, round_id)
        judge_totals = []
        for jid in all_judge_ids:
            j_events = await get_judge_deductions_for_student(db, round_id, student_id, jid)
            j_deductions: dict[int, float] = defaultdict(float)
            for e in j_events:
                j_deductions[e.deduction_type_id] += e.amount
            j_total = 0.0
            for crit_id, (_, max_pts) in crit_max.items():
                deducted = sum(
                    amt for dt_id, amt in j_deductions.items()
                    if dt_to_crit.get(dt_id) == crit_id
                )
                j_total += max(0.0, max_pts - deducted)
            judge_totals.append(j_total)
        panel_score = sum(judge_totals) / len(judge_totals) if judge_totals else None
        
        if is_moderator and panel_score is not None:
            # Overwrite the requesting judge's personal score (which is empty) with the live panel average
            total = panel_score"""

content = content.replace(old_logic, new_logic)

with open("app/crud/scoring.py", "w") as f:
    f.write(content)
