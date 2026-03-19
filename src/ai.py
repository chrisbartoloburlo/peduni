import base64
import json

import litellm

from .crypto import decrypt

PROVIDER_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini/gemini-2.0-flash",
}

EXTRACT_PROMPT = """Extract expense information from this document/receipt/invoice.
Return a JSON object with exactly these fields:
{
  "merchant": "store or restaurant name, or null",
  "amount": numeric value only (no currency symbol), or null,
  "currency": "3-letter code like USD, EUR, GBP, or null",
  "date": "YYYY-MM-DD format, or null",
  "category": one of: food, transport, accommodation, shopping, health, entertainment, utilities, other — or null,
  "raw_text": "one sentence describing what this expense is"
}
Return only the JSON object, nothing else."""


async def extract_expense(encrypted_api_key: str, provider: str, file_content: bytes, mime_type: str, filename: str) -> dict:
    api_key = decrypt(encrypted_api_key)
    model = PROVIDER_MODELS.get(provider, "gpt-4o")

    if mime_type.startswith("image/"):
        b64 = base64.b64encode(file_content).decode()
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                {"type": "text", "text": EXTRACT_PROMPT},
            ],
        }]
    elif mime_type == "application/pdf":
        # Extract text from PDF and pass as context
        import pdfplumber
        import io
        text = ""
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        messages = [{
            "role": "user",
            "content": f"Document: {filename}\n\n{text[:4000]}\n\n{EXTRACT_PROMPT}",
        }]
    else:
        messages = [{
            "role": "user",
            "content": f"Filename: {filename}\n\n{EXTRACT_PROMPT}",
        }]

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        api_key=api_key,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


async def answer_query(encrypted_api_key: str, provider: str, question: str, expenses: list[dict]) -> str:
    api_key = decrypt(encrypted_api_key)
    model = PROVIDER_MODELS.get(provider, "gpt-4o")

    if not expenses:
        expense_context = "No expenses recorded yet."
    else:
        lines = []
        for e in expenses:
            amount_str = f"{e['amount']} {e['currency'] or ''}".strip() if e['amount'] else "amount unknown"
            lines.append(f"- {e['date'] or 'unknown date'} | {e['merchant'] or 'unknown merchant'} | {amount_str} | {e['category'] or 'uncategorized'} | {e['raw_text'] or ''}")
        expense_context = "\n".join(lines)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful expense tracking assistant. "
                "Answer questions about the user's expenses accurately and concisely.\n\n"
                f"Expenses:\n{expense_context}"
            ),
        },
        {"role": "user", "content": question},
    ]

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        api_key=api_key,
    )

    return response.choices[0].message.content
