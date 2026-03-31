from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..config import settings
from ..crypto import encrypt
from ..db import SessionLocal, User

PROVIDERS = {"anthropic", "openai", "gemini"}
PROVIDER_NAMES = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "openrouter": "OpenRouter",
    "hosted": "Pay per use",
}


def _ai_setup_markup(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            "Connect OpenRouter (recommended)",
            url=f"{settings.base_url}/auth/openrouter/{user_id}",
        )],
        [InlineKeyboardButton("Pay per use with Telegram Stars", callback_data="pay_per_use")],
        [InlineKeyboardButton("Use my own API key instead", callback_data="use_own_key")],
    ]
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            user = User(id=user_id, setup_step="awaiting_google")
            session.add(user)
            await session.commit()
        elif user.setup_step == "ready":
            if user.is_byok:
                await update.message.reply_text(
                    "You're all set! Send me a receipt or ask a question about your expenses."
                )
            else:
                await update.message.reply_text(
                    f"You're all set! You have {user.credits} credits.\n"
                    "Send me a receipt or ask a question. Use /buy for more credits."
                )
            return
        elif user.setup_step == "awaiting_ai_setup":
            await update.message.reply_text(
                "Almost there! Connect your AI to finish setup:",
                reply_markup=_ai_setup_markup(user_id),
            )
            return

    await update.message.reply_text(
        "Welcome to Peduni — your personal expense tracker.\n\n"
        "I'll store your receipts in your own Google Drive and let you query them with AI.\n\n"
        "Let's start by connecting your Google Drive:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Connect Google Drive",
                url=f"{settings.base_url}/auth/google/{user_id}",
            )
        ]]),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_settings":
        async with SessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.setup_step = "ready"
                await session.commit()
        await query.edit_message_text("Cancelled. Nothing was changed.")
        return

    if query.data == "pay_per_use":
        if not settings.hosted_ai_api_key:
            await query.edit_message_text(
                "Pay per use is not available on this instance. "
                "Please use OpenRouter or your own API key."
            )
            return

        async with SessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.ai_provider = "hosted"
                user.ai_api_key = None
                user.credits = max(user.credits, settings.free_credits)
                user.setup_step = "ready"
                await session.commit()
                credits = user.credits

        await query.edit_message_text(
            f"✅ All set! You have {credits} free credits to start.\n\n"
            "You can now:\n"
            "• Send me receipts, invoices, or screenshots\n"
            "• Ask questions like \"how much did I spend on food this month?\"\n\n"
            "Use /buy to get more credits when you run out."
        )
        return

    if query.data == "use_own_key":
        async with SessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.setup_step = "awaiting_provider"
                await session.commit()

        await query.edit_message_text(
            "Which provider?\n"
            "• anthropic\n"
            "• openai\n"
            "• gemini\n\n"
            "Reply with the provider name."
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

    if user.setup_step == "awaiting_ai_setup":
        await update.message.reply_text(
            "Please choose how to connect your AI:",
            reply_markup=_ai_setup_markup(user.id),
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
            pass

        await update.message.reply_text(
            "✅ All set! Your API key is stored encrypted.\n\n"
            "You can now:\n"
            "• Send me receipts, invoices, or screenshots\n"
            '• Ask questions like "how much did I spend on food this month?"'
        )
        return True

    return False


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**Peduni — Expense Tracker**\n\n"
        "**Getting started:**\n"
        "Send me a photo, screenshot, or PDF of a receipt and I'll extract the details and save it to your Google Drive.\n\n"
        "**Ask questions:**\n"
        "Just type a question like:\n"
        '• "How much did I spend on food this month?"\n'
        '• "What are my biggest expenses?"\n'
        '• "Total spending in March"\n\n'
        "**Commands:**\n"
        "/start — Set up your account\n"
        "/settings — Change AI provider or API key\n"
        "/buy — Buy credits (pay-per-use users)\n"
        "/help — Show this message",
        parse_mode="Markdown",
    )


async def change_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user or user.setup_step != "ready":
            await update.message.reply_text("Please complete setup first with /start.")
            return

        current = PROVIDER_NAMES.get(user.ai_provider, user.ai_provider)
        user.setup_step = "awaiting_ai_setup"
        await session.commit()

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Connect OpenRouter (recommended)",
            url=f"{settings.base_url}/auth/openrouter/{user_id}",
        )],
        [InlineKeyboardButton("Pay per use with Telegram Stars", callback_data="pay_per_use")],
        [InlineKeyboardButton("Use my own API key instead", callback_data="use_own_key")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_settings")],
    ])
    await update.message.reply_text(
        f"Current AI: {current}\n\nSwitch to a different AI:",
        reply_markup=markup,
    )
