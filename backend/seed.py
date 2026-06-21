"""
Run once to create the initial user account.
Usage: python seed.py
"""
import asyncio
import uuid
from sqlalchemy import select
import bcrypt
from app.database import AsyncSessionLocal
from app.models.user import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

EMAIL = "rahul@spectropy.com"
PASSWORD = "spectropy2022"
FULL_NAME = "Rahul"


async def seed():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == EMAIL))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"User {EMAIL} already exists — skipping.")
            return

        user = User(
            id=str(uuid.uuid4()),
            email=EMAIL,
            hashed_password=hash_password(PASSWORD),
            full_name=FULL_NAME,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"Created user: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
