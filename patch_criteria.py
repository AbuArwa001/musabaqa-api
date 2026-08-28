import re

with open("app/crud/scoring.py", "r") as f:
    content = f.read()

old_logic = """    # Fetch criteria maxes
    criteria_result = await db.execute(
        select(ScoringCriteria, DeductionType).join(
            DeductionType, DeductionType.scoring_criteria_id == ScoringCriteria.id
        )
    )"""

new_logic = """    # Fetch student category to get category_group
    from app.models.student import Student
    from app.models.category import Category
    student = await db.get(Student, student_id)
    category = await db.get(Category, student.category_id)

    # Fetch criteria maxes for the student's category group
    criteria_result = await db.execute(
        select(ScoringCriteria, DeductionType).join(
            DeductionType, DeductionType.scoring_criteria_id == ScoringCriteria.id
        ).where(
            ScoringCriteria.category_group == category.category_group
        )
    )"""

content = content.replace(old_logic, new_logic)

with open("app/crud/scoring.py", "w") as f:
    f.write(content)
