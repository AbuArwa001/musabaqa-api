import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import select
from app.models.admin_user import AdminUser
from app.core.security import verify_password

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///musabaqa.db")
    async with AsyncSession(engine) as db:
        result = await db.execute(
            select(AdminUser).where(AdminUser.email == "admin@jmc.or.ke", AdminUser.active == True)
        )
        try:
            user = result.scalar_one_or_none()
            print(f"User found: {user}")
        except Exception as e:
            print(f"Error fetching user: {e}")

if __name__ == "__main__":
    asyncio.run(main())
