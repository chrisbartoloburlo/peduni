from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from ..ai import answer_query
from ..db import Expense, SessionLocal, User
from .onboarding import handle_setup_message
from .payments import NO_CREDITS_MSG, check_credits, deduct_credit


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            await update.message.reply_text("Please run /start first.")
            return

        if user.setup_step != "ready":
            consumed = await handle_setup_message(update, context, user, session)
            if not consumed:
                await update.message.reply_text("Please complete setup first. Use /start.")
            return

        # Check credits for hosted users
        if not await check_credits(user):
            await update.message.reply_text(NO_CREDITS_MSG)
            return

        # Deduct after successful query (below)
        should_deduct = not user.is_byok

        # Fetch user's expenses
        result = await session.execute(
            select(Expense).where(Expense.user_id == user_id).order_by(Expense.created_at.desc())
        )
        expenses = result.scalars().all()
        expenses_data = [
            {
                "merchant": e.merchant,
                "amount": float(e.amount) if e.amount else None,
                "currency": e.currency,
                "date": e.date,
                "category": e.category,
                "raw_text": e.raw_text,
            }
            for e in expenses
        ]

    thinking_msg = await update.message.reply_text("Thinking...")

    try:
        answer = await answer_query(user.ai_api_key, user.ai_provider, update.message.text, expenses_data)
        if should_deduct:
            async with SessionLocal() as session:
                user = await session.get(User, user_id)
                await deduct_credit(user, session)
        await thinking_msg.edit_text(answer)
    except Exception as e:
        await thinking_msg.edit_text(f"Error contacting AI: {e}")
