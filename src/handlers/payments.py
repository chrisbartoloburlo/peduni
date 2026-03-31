from telegram import LabeledPrice, Update
from telegram.ext import ContextTypes

from ..db import SessionLocal, User

CREDIT_PACKS = [
    {"id": "credits_50", "credits": 50, "stars": 50, "label": "50 credits"},
    {"id": "credits_150", "credits": 150, "stars": 100, "label": "150 credits (best value)"},
    {"id": "credits_500", "credits": 500, "stars": 250, "label": "500 credits"},
]


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user or user.setup_step != "ready":
            await update.message.reply_text("Please complete setup first with /start.")
            return

        balance_text = f"You have **{user.credits}** credits remaining.\n\n" if not user.is_byok else ""

    text = (
        f"{balance_text}"
        "1 credit = 1 receipt upload or 1 AI question.\n"
        "Pick a pack:"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

    for pack in CREDIT_PACKS:
        await update.message.reply_invoice(
            title=pack["label"],
            description=f"{pack['credits']} credits for processing receipts and asking questions",
            payload=pack["id"],
            currency="XTR",
            prices=[LabeledPrice(pack["label"], pack["stars"])],
        )


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Always approve — validation happens at purchase time."""
    await update.pre_checkout_query.answer(ok=True)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user_id = update.effective_user.id

    # Find the matching pack
    pack = next((p for p in CREDIT_PACKS if p["id"] == payload), None)
    if not pack:
        await update.message.reply_text("Payment received but unknown pack. Contact support.")
        return

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            user.credits += pack["credits"]
            await session.commit()
            balance = user.credits

    await update.message.reply_text(
        f"✅ {pack['credits']} credits added!\n"
        f"Balance: {balance} credits"
    )


async def check_and_deduct_credit(user, session) -> bool:
    """
    Check if user can make an AI call. BYOK users always pass.
    Hosted users need credits. Deducts 1 credit if available.
    Returns True if the call is allowed.
    """
    if user.is_byok:
        return True

    if user.credits <= 0:
        return False

    user.credits -= 1
    await session.commit()
    return True


NO_CREDITS_MSG = (
    "You're out of credits! Use /buy to get more, "
    "or switch to your own API key with /settings."
)
