from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, DateTime, Numeric, String, Text
from .config import settings

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user ID
    setup_step: Mapped[str] = mapped_column(String(50), default="awaiting_google")
    google_tokens: Mapped[str | None] = mapped_column(Text, default=None)
    drive_folder_id: Mapped[str | None] = mapped_column(String(200), default=None)
    ai_provider: Mapped[str | None] = mapped_column(String(50), default=None)
    ai_api_key: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    drive_file_id: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(500))
    merchant: Mapped[str | None] = mapped_column(String(200), default=None)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2), default=None)
    currency: Mapped[str | None] = mapped_column(String(10), default=None)
    date: Mapped[str | None] = mapped_column(String(50), default=None)
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    raw_text: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
