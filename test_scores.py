import asyncio
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import AsyncSessionLocal
from app.crud.scoring import get_judge_score_summary
from app.models.admin_user import AdminUser
from app.models.student import Student

async def test_scores():
    async with AsyncSessionLocal() as db:
        # Get moderator
        mod_res = await db.execute(select(AdminUser).where(AdminUser.email == "moderator@jmc.or.ke"))
        mod = mod_res.scalars().first()
        
        # Get judge 1
        judge_res = await db.execute(select(AdminUser).where(AdminUser.email == "judge1@jmc.or.ke"))
        judge1 = judge_res.scalars().first()
        
        # Get first student
        student_res = await db.execute(select(Student))
        student = student_res.scalars().first()
        
        # Call for judge 1
        j_summary = await get_judge_score_summary(db, 2, student.id, judge1.id)
        print(f"Judge 1 Score: {j_summary.total_score}")
        
        # Call for moderator
        m_summary = await get_judge_score_summary(db, 2, student.id, mod.id)
        print(f"Moderator Score: {m_summary.total_score}")

if __name__ == "__main__":
    asyncio.run(test_scores())
