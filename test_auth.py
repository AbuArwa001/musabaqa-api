import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import select
from app.models.admin_user import AdminUser
from app.core.security import verify_password
import os

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///musabaqa.db") # Assuming default sqlite? Or let's check .env
    SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    async with SessionLocal() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.email == "admin@jamiamosque.co.ke"))
        user = result.scalar_one_or_none()
        print(f"User: {user}")
        if user:
            print(f"Password hash: {user.password_hash}")
            try:
                is_valid = verify_password("admin123", user.password_hash)
                print(f"Is valid: {is_valid}")
            except Exception as e:
                print(f"Verify Error: {e}")
        else:
            print("User not found.")

if __name__ == "__main__":
    asyncio.run(main())
