# AI-Native E-Commerce Shopping Assistant

A production-ready AI shopping assistant built with GPT-4, RAG (Retrieval-Augmented Generation), and ReAct (Reasoning + Acting) architecture.

## Features

- **Conversational AI**: Natural language product search and recommendations
- **Hybrid Search**: Combines semantic (vector) and keyword search with Reciprocal Rank Fusion
- **Intent Classification**: Automatically detects user intent (Browse, Search, Purchase, Support, Inquiry)
- **Guardrails**: Enforces business rules and prevents hallucinations
- **Streaming Responses**: Real-time WebSocket-based chat with token streaming
- **Product Cards**: Product details, ratings, and stock status
- **Multi-Source Search**: Aggregates results from Google Shopping, Amazon, ASOS, Home Depot, and more
- **Stripe Checkout**: Sandbox payment processing with tax calculation
- **Authentication**: Guest sessions, email/password, Google OAuth, Microsoft OAuth

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    INTERACTION LAYER                     │
│  React UI  │  REST API  │  WebSocket Streaming          │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────┐
│                    REASONING LAYER                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │         ORCHESTRATION ENGINE (ReAct)              │   │
│  │  Intent → Plan → Guardrails → LLM + Tools        │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────┐
│                  SERVICES / DATA LAYER                   │
│  Local Vector DB (numpy)  │  Product APIs  │  User DB   │
└─────────────────────────────────────────────────────────┘
```

### Core Components

1. **Orchestration Engine** (`backend/app/core/orchestrator.py`): Manages conversation flow using ReAct pattern
2. **Intent Classifier** (`backend/app/core/intent_classifier.py`): Classifies user messages into actionable intents
3. **Plan Generator** (`backend/app/core/plan_generator.py`): Creates execution plans for each intent
4. **Guardrails Engine** (`backend/app/core/guardrails.py`): Validates responses against business rules
5. **Tool Executor** (`backend/app/tools/executor.py`): Executes function calls (search, cart, orders)
6. **Vector Search** (`backend/app/services/vector_db.py`): Numpy-based semantic product search with cosine similarity
7. **Memory Service** (`backend/app/services/memory.py`): Manages conversation context and history

## Quick Start

> **Try it online:** Skip local setup and use the live demo at [commerce-agent-llm.vercel.app](https://commerce-agent-llm.vercel.app/)

### Prerequisites

- **Git** ([Download](https://git-scm.com/downloads))
- **Python 3.9 to 3.12** ([Download](https://www.python.org/downloads/)) (3.13+ is not yet supported by some dependencies)
- **Node.js 16+** ([Download](https://nodejs.org/))
- **OpenAI API key** ([Get one here](https://platform.openai.com/api-keys))

> No Docker required. The application uses in-memory storage and a numpy-based vector database.
>
> **Windows users:** The automated setup script requires Bash (Git Bash works). For manual setup, use `venv\Scripts\activate` instead of `source venv/bin/activate`.

### Option A: Automated Setup (Recommended)

```bash
git clone https://github.com/scientxst/Commerce-Agent-LLM.git
cd Commerce-Agent-LLM
chmod +x setup.sh
./setup.sh
```

The script will:
- Verify Python and Node.js versions
- Create a Python virtual environment
- Install all backend and frontend dependencies
- Generate a JWT secret automatically
- Prompt you for your OpenAI API key

Then follow the printed instructions to start the backend and frontend.

### Option B: Manual Setup

**1. Clone and configure environment**

```bash
git clone https://github.com/scientxst/Commerce-Agent-LLM.git
cd Commerce-Agent-LLM
cp .env.example .env
```

**2. Add your API keys to `.env`**

Open `.env` in any text editor. You need to set two values:

1. **JWT_SECRET**: generate one by running the command below, then paste the output into `.env`:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. **OPENAI_API_KEY**: paste your OpenAI API key (starts with `sk-`).

Your `.env` should have at minimum:
```
OPENAI_API_KEY=sk-proj-abc123...
JWT_SECRET=your-generated-64-char-string
```

To enable live product search, checkout, or OAuth login, fill in any of the optional keys listed in the [Environment Variables](#environment-variables) table below.

**3. Install and start the backend (Terminal 1)**

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

cd backend
python -m app.main
```

The server will start at `http://localhost:8000`. API docs are available at `http://localhost:8000/docs`.

**4. Install and start the frontend (Terminal 2)**

Open a new terminal and navigate to the project's `frontend` directory:

```bash
cd /path/to/Commerce-Agent-LLM/frontend    # macOS/Linux
cd C:\path\to\Commerce-Agent-LLM\frontend  # Windows
npm install
npm run dev
```

The frontend will open at `http://localhost:3000`.

## Usage

### Example Queries

**Product Search:**
- "I need comfortable shoes for a wedding under $150"
- "Show me the latest smartphones"
- "Looking for noise cancelling headphones for travel"

**Product Inquiries:**
- "Is this waterproof?"
- "What colors is this available in?"

**Cart Operations:**
- "Add this to my cart"
- "What's in my cart?"

## Project Structure

```
Commerce-Agent-LLM/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── orchestrator.py          # ReAct loop (main reasoning engine)
│   │   │   ├── intent_classifier.py     # LLM-based intent detection
│   │   │   ├── plan_generator.py        # Execution plan creation
│   │   │   └── guardrails.py            # Business rule enforcement
│   │   ├── services/
│   │   │   ├── vector_db.py             # Numpy-based semantic search
│   │   │   ├── product_db.py            # Product catalog + live API search
│   │   │   ├── user_db.py              # In-memory user/cart storage
│   │   │   ├── auth_db.py              # Authentication database
│   │   │   ├── memory.py               # Conversation memory management
│   │   │   ├── serpapi_client.py        # Google Shopping API
│   │   │   ├── rapidapi_client.py       # Real-time product search
│   │   │   ├── rainforest_client.py     # Amazon product data
│   │   │   ├── scraperapi_client.py     # Amazon structured data
│   │   │   ├── asos_client.py           # Fashion products (via RapidAPI)
│   │   │   ├── homedepot_client.py      # Home improvement (via RapidAPI)
│   │   │   ├── openfoodfacts_client.py  # Food products (free, no key)
│   │   │   ├── search_intent.py         # Category routing
│   │   │   └── result_aggregator.py     # Multi-source result merging
│   │   ├── tools/
│   │   │   ├── executor.py              # Tool implementations (search, cart)
│   │   │   └── registry.py             # OpenAI function call definitions
│   │   ├── routers/
│   │   │   └── auth.py                  # JWT auth, OAuth, guest sessions
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic data models
│   │   ├── utils/
│   │   │   └── config.py               # Environment config (Pydantic Settings)
│   │   └── main.py                      # FastAPI application entry point
│   ├── data/
│   │   └── sample_products.json         # Built-in product catalog
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/                    # ChatInterface, Message, TypingIndicator
│   │   │   ├── layout/                  # Header, Sidebar, CartDrawer
│   │   │   └── product/                # ProductCard, ProductGrid
│   │   ├── pages/                       # ChatPage, CheckoutPage, LoginPage, SavedPage
│   │   ├── stores/                      # Zustand state (auth, cart, saved, theme)
│   │   ├── lib/api.js                   # Backend API client
│   │   ├── App.jsx                      # Router and app shell
│   │   └── main.jsx                    # Vite entry point
│   ├── vite.config.js                   # Dev server + proxy config
│   └── package.json
├── docs/                                # Project documentation
├── .env.example                         # Environment variable template
├── setup.sh                             # One-command setup script
└── README.md
```

## Configuration

### Environment Variables

See `.env.example` for all available options. The two required variables are:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Powers the AI assistant |
| `JWT_SECRET` | Yes | Signing key for auth tokens (min 32 chars) |
| `RAPIDAPI_KEY` | No | Enables Real-Time Product Search |
| `SERPAPI_KEY` | No | Enables Google Shopping search |
| `RAINFOREST_API_KEY` | No | Enables Amazon product data |
| `SCRAPERAPI_KEY` | No | Enables Amazon structured data |
| `STRIPE_SECRET_KEY` | No | Enables Stripe checkout (use test key `sk_test_...`) |
| `GOOGLE_CLIENT_ID` | No | Enables Google OAuth login |
| `MICROSOFT_CLIENT_ID` | No | Enables Microsoft/Outlook login |

External product-search APIs (RapidAPI, SerpAPI, Rainforest, ScraperAPI, etc.) are all optional; without them the app uses sample product data. See `.env.example` for the full list.

## Key Features Explained

### 1. Hybrid Search

Combines semantic and keyword search for best results:
- **Semantic Search**: Understands intent ("comfortable wedding shoes")
- **Keyword Search**: Exact matches (SKU, brand names)
- **Reciprocal Rank Fusion**: Intelligently merges results from multiple sources

### 2. Guardrails System

Prevents AI from:
- Making up discounts or prices
- Mentioning competitor products
- Claiming items are in stock without verification
- Exposing user PII

### 3. ReAct Pattern

Reasoning + Acting loop:
1. User sends message
2. System classifies intent
3. Generates execution plan
4. Validates with guardrails
5. Executes tools (search, fetch data)
6. Generates natural response

### 4. Streaming Responses

WebSocket-based streaming for real-time token-by-token responses with lower perceived latency.

## API Endpoints

### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/chat` | Send chat message (non-streaming) |
| `GET` | `/api/products` | List all products |
| `GET` | `/api/products/{id}` | Get product details |
| `POST` | `/auth/guest` | Create guest session |
| `POST` | `/auth/register` | Register with email/password |
| `POST` | `/auth/login/email` | Login with email/password |
| `POST` | `/auth/google` | Google OAuth login |
| `POST` | `/auth/microsoft` | Microsoft OAuth login |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/chat/{user_id}/{session_id}` | Streaming chat |

## Testing

```bash
# Health check
curl http://localhost:8000/health

# Create a guest session
curl -s -X POST http://localhost:8000/auth/guest | python3 -m json.tool

# List products (no auth required)
curl -s http://localhost:8000/api/products | python3 -m json.tool

# Send a chat message (replace TOKEN with the token from /auth/guest)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "message": "Show me headphones under $100"
  }'
```

## Troubleshooting

### Backend won't start: "JWT_SECRET field required"
Generate a secret and add it to your `.env`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Backend won't start: "OPENAI_API_KEY field required"
Add your OpenAI API key to `.env`. Get one at https://platform.openai.com/api-keys

### pip install fails on Python 3.13+
Some dependencies do not yet have pre-built wheels for Python 3.13+. Use Python 3.9 to 3.12 instead.

### Frontend: "Missing script: start"
Use `npm run dev` (not `npm start`). The project uses Vite, not Create React App.

### Frontend can't connect to backend
- Verify the backend is running on port 8000
- The Vite dev server proxies `/api`, `/auth`, and `/ws` requests to `localhost:8000` automatically
- Check browser console for specific errors

### First startup is slow
On first run, the backend generates embeddings for the product catalog using the OpenAI API. This takes 30 to 60 seconds and is cached for subsequent runs.

## For Evaluators

API keys are not stored in the repository for security reasons. The team will provide them separately. Follow [Option A: Automated Setup](#option-a-automated-setup-recommended) above and paste the provided OpenAI API key when prompted.

## License

MIT License

## Support

For questions or issues, please open a GitHub issue.

---

Built with GPT-4, LangChain, FastAPI, React, and Vite
