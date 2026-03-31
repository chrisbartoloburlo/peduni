import asyncio
from datetime import datetime

from google.auth.exceptions import RefreshError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..ai import extract_expense
from ..config import settings
from ..db import Expense, SessionLocal, User
from ..drive import ensure_root_folder, upload_file
from .onboarding import handle_setup_message
from .payments import NO_CREDITS_MSG, check_and_deduct_credit

MIME_FALLBACK = "application/octet-stream"


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            await update.message.reply_text("Please run /start first.")
            return

        if user.setup_step != "ready":
            await handle_setup_message(update, context, user, session)
            return

        # Check credits for hosted users
        if not await check_and_deduct_credit(user, session):
            await update.message.reply_text(NO_CREDITS_MSG)
            return

        # Determine file type
        if update.message.photo:
            photo = update.message.photo[-1]  # largest size
            tg_file = await photo.get_file()
            mime_type = "image/jpeg"
            filename = f"photo_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jpg"
        elif update.message.document:
            doc = update.message.document
            tg_file = await doc.get_file()
            mime_type = doc.mime_type or MIME_FALLBACK
            filename = doc.file_name or f"document_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        else:
            return

        processing_msg = await update.message.reply_text("Processing your document...")

        # Download from Telegram
        file_content = await tg_file.download_as_bytearray()
        file_bytes = bytes(file_content)

        # Extract expense data with AI first so we know the invoice date
        try:
            data = await extract_expense(user.ai_api_key, user.ai_provider, file_bytes, mime_type, filename)
        except Exception as e:
            data = {"merchant": None, "amount": None, "currency": None, "date": None, "category": None, "raw_text": str(e)}

        # Use invoice date for folder if available, otherwise fall back to today
        invoice_date = data.get("date")
        try:
            month_str = datetime.strptime(invoice_date, "%Y-%m-%d").strftime("%Y-%m")
        except (TypeError, ValueError):
            month_str = datetime.utcnow().strftime("%Y-%m")

        # Upload to Google Drive (blocking I/O — run in thread)
        try:
            if not user.drive_folder_id:
                user.drive_folder_id = await asyncio.get_event_loop().run_in_executor(
                    None, ensure_root_folder, user.google_tokens
                )
                await session.commit()

            drive_file_id = await asyncio.get_event_loop().run_in_executor(
                None, upload_file, user.google_tokens, user.drive_folder_id, month_str, filename, file_bytes, mime_type
            )
        except RefreshError:
            user.google_tokens = None
            user.drive_folder_id = None
            user.setup_step = "awaiting_google"
            await session.commit()
            await processing_msg.edit_text(
                "Your Google Drive connection has expired. Please reconnect:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "Reconnect Google Drive",
                        url=f"{settings.base_url}/auth/google/{user_id}",
                    )
                ]]),
            )
            return

        # Save to DB
        expense = Expense(
            user_id=user_id,
            drive_file_id=drive_file_id,
            filename=filename,
            merchant=data.get("merchant"),
            amount=data.get("amount"),
            currency=data.get("currency"),
            date=data.get("date"),
            category=data.get("category"),
            raw_text=data.get("raw_text"),
        )
        session.add(expense)
        await session.commit()

    # Build confirmation message
    lines = ["✅ Saved to your Google Drive!"]
    if data.get("merchant"):
        lines.append(f"Merchant: {data['merchant']}")
    if data.get("amount"):
        currency = data.get("currency") or ""
        lines.append(f"Amount: {data['amount']} {currency}".strip())
    if data.get("date"):
        lines.append(f"Date: {data['date']}")
    if data.get("category"):
        lines.append(f"Category: {data['category']}")
    if data.get("raw_text"):
        lines.append(f"Note: {data['raw_text']}")

    await processing_msg.edit_text("\n".join(lines))
