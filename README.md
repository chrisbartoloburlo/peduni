# Peduni

An open-source personal expense tracker that lives in Telegram. Drop receipts, invoices, and screenshots into a chat — Peduni extracts the data with AI, stores everything in your Google Drive, and lets you ask questions about your spending.

**Your data stays yours.** Documents go to your own Google Drive. AI runs on your own API key (or via OpenRouter). Peduni is just the glue.

## How It Works

```
You send a receipt photo in Telegram
        ↓
AI extracts merchant, amount, date, category
        ↓
Document saved to your Google Drive (organized by month)
        ↓
Ask "how much did I spend on food this month?" → AI answers
```

### Google Drive Structure

```
My Drive/
└── Peduni/
    ├── 2026-01/
    │   ├── receipt_starbucks.jpg
    │   └── invoice_amazon.pdf
    ├── 2026-02/
    └── 2026-03/
```

Files are organized by **invoice date** (not upload date), so everything lands in the right month.

## Features

- **Telegram-first** — no app to install, no website to visit
- **AI-powered extraction** — snap a photo of a receipt and get merchant, amount, date, and category automatically
- **Google Drive storage** — documents stored in your own Drive, organized into monthly folders
- **Natural language queries** — ask anything about your expenses in plain English
- **Multi-provider AI** — works with Claude (Anthropic), GPT-4 (OpenAI), Gemini (Google), or any model via OpenRouter
- **OpenRouter OAuth** — one-click AI setup, no API key copy-pasting required
- **Bring Your Own Key** — use your own API key from any supported provider
- **Encrypted secrets** — API keys and OAuth tokens are encrypted at rest with Fernet
- **Self-hostable** — deploy your own instance with Docker

## Setup

### Prerequisites

- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Google Cloud project with OAuth 2.0 credentials and the Drive API enabled
- A PostgreSQL database
- Somewhere to host it (Railway, Fly.io, VPS, Raspberry Pi, etc.)

### 1. Clone and configure

```bash
git clone https://github.com/chrisbartoloburlo/peduni.git
cd peduni
cp .env.example .env
```

Edit `.env` with your credentials:

```env
TELEGRAM_TOKEN=your_bot_token
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
ENCRYPTION_KEY=your_fernet_key
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
BASE_URL=https://your-public-url.com
```

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Google Cloud setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable the **Google Drive API**
4. Go to **APIs & Services > Credentials > Create Credentials > OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Add `https://your-public-url.com/auth/callback` as an authorized redirect URI
7. Copy the Client ID and Client Secret into your `.env`

### 3. Deploy

**With Docker Compose (local development):**

```bash
docker compose up
```

**With Docker (production):**

```bash
docker build -t peduni .
docker run --env-file .env peduni
```

**On Railway:**

1. Push to GitHub
2. Connect the repo on [Railway](https://railway.app)
3. Add a PostgreSQL database to your project
4. Set the environment variables in the Railway dashboard
5. Railway auto-deploys from the Dockerfile

### 4. Configure the bot

Message [@BotFather](https://t.me/BotFather) and set the bot commands:

```
start - Set up your account
settings - Change AI provider or API key
```

## User Onboarding

When a new user messages the bot:

1. `/start` — bot sends a **Connect Google Drive** button
2. User authorizes Google Drive (OAuth)
3. Bot offers two options:
   - **Connect OpenRouter** (recommended) — OAuth flow, no key pasting
   - **Use my own API key** — manually enter provider + key
4. Done — start dropping receipts

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Begin setup or check status |
| `/settings` | Change AI provider or API key |

Everything else is conversational — send a document to log an expense, send a text message to ask a question.

## Architecture

```
┌─────────────┐     ┌──────────────────────────────┐     ┌──────────────┐
│  Telegram    │────>│  Peduni                      │────>│  Google      │
│  (user chat) │<────│                              │<────│  Drive       │
└─────────────┘     │  ┌────────┐  ┌────────────┐  │     │  (user's)    │
                    │  │ Bot    │  │ FastAPI     │  │     └──────────────┘
                    │  │ Polling│  │ OAuth       │  │
                    │  └────┬───┘  └──────┬─────┘  │     ┌──────────────┐
                    │       │             │        │────>│  AI Provider  │
                    │  ┌────┴─────────────┴─────┐  │<────│  (user's key)│
                    │  │  PostgreSQL             │  │     └──────────────┘
                    │  │  (users + expenses)     │  │
                    │  └────────────────────────┘  │
                    └──────────────────────────────┘
```

### Tech Stack

- **Python 3.12** + **FastAPI** + **python-telegram-bot**
- **SQLAlchemy** (async) + **PostgreSQL**
- **LiteLLM** — unified interface across AI providers
- **Google Drive API** — document storage
- **Fernet** — encryption at rest for secrets

## Supported AI Providers

| Provider | Model | Setup |
|----------|-------|-------|
| OpenRouter | All models (Claude, GPT-4, Gemini, etc.) | OAuth (one click) |
| Anthropic | Claude Sonnet | API key |
| OpenAI | GPT-4o | API key |
| Google | Gemini 2.0 Flash | API key |

## Security

- API keys and OAuth tokens are **encrypted at rest** using Fernet symmetric encryption
- Google Drive access is scoped to `drive.file` — Peduni can only see files it created
- When users paste API keys, the message is **automatically deleted**
- All AI calls use the **user's own credentials**, not a shared key

## Cost

**For the host:** Railway hosting (~$5/month) + domain. Everything else is free.

**For users:** Whatever their AI provider charges per API call. With OpenRouter, a typical receipt costs ~$0.01-0.05 to process.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## License

MIT
