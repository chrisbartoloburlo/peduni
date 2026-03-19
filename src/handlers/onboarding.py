from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..config import settings
from ..crypto import encrypt
from ..db import SessionLocal, User

PROVIDERS = {"anthropic", "openai", "gemini"}
PROVIDER_NAMES = {"anthropic": "Anthropic (Claude)", "openai": "OpenAI", "gemini": "Google Gemini"}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            user = User(id=user_id, setup_step="awaiting_google")
            session.add(user)
            await session.commit()
        elif user.setup_step == "ready":
            await update.message.reply_text(
                "You're all set! Send me a receipt or ask a question about your expenses."
            )
            return

    await update.message.reply_text(
        "👋 Welcome to Peduni — your personal expense tracker.\n\n"
        "I'll store your receipts in your own Google Drive and let you query them with AI.\n\n"
        "Let's start by connecting your Google Drive:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Connect Google Drive",
                url=f"{settings.base_url}/auth/google/{user_id}",
            )
        ]]),
    )


async def handle_setup_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, session) -> bool:
    """
    Handle messages during the setup flow.
    Returns True if the message was consumed by setup, False otherwise.
    """
    text = update.message.text.strip().lower() if update.message.text else ""

    if user.setup_step == "awaiting_google":
        await update.message.reply_text(
            "Please connect your Google Drive first:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Connect Google Drive",
                    url=f"{settings.base_url}/auth/google/{user.id}",
                )
            ]]),
        )
        return True

    if user.setup_step == "awaiting_provider":
        if text in PROVIDERS:
            user.ai_provider = text
            user.setup_step = "awaiting_api_key"
            await session.commit()
            await update.message.reply_text(
                f"Great, using {PROVIDER_NAMES[text]}.\n\n"
                "Now paste your API key. I'll encrypt it and it won't be visible to anyone.\n"
                "(The message will be deleted after I read it.)"
            )
        else:
            await update.message.reply_text(
                "Please choose one of:\n• anthropic\n• openai\n• gemini"
            )
        return True

    if user.setup_step == "awaiting_api_key":
        if not update.message.text:
            return True
        raw_key = update.message.text.strip()
        user.ai_api_key = encrypt(raw_key)
        user.setup_step = "ready"
        await session.commit()

        try:
            await update.message.delete()
        except Exception:
            pass  # can't delete in some chat types

        await update.message.reply_text(
            "✅ All set! Your API key is stored encrypted.\n\n"
            "You can now:\n"
            "• Send me receipts, invoices, or screenshots\n"
            '• Ask questions like "how much did I spend on food this month?"'
        )
        return True

    return False


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user or user.setup_step != "ready":
            await update.message.reply_text("Please complete setup first with /start.")
            return

        current = PROVIDER_NAMES.get(user.ai_provider, user.ai_provider)
        user.setup_step = "awaiting_provider"
        await session.commit()

    await update.message.reply_text(
        f"Current AI provider: {current}\n\n"
        "Which provider would you like to switch to?\n"
        "• anthropic\n"
        "• openai\n"
        "• gemini\n\n"
        "Reply with the provider name, then I'll ask for your new API key."
    )
