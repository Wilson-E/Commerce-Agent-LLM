# Quick Start Guide

## Prerequisites

Before you begin, ensure you have:
- Python 3.9 to 3.12 (3.13+ is not yet supported by some dependencies)
- Node.js 16+
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

> No Docker required.

## Setup (5 minutes)

### Automated (Recommended)

```bash
git clone https://github.com/scientxst/Commerce-Agent-LLM.git
cd Commerce-Agent-LLM
chmod +x setup.sh
./setup.sh
```

Follow the prompts to enter your OpenAI API key, then follow the printed run instructions.

### Manual

**1. Clone and configure**

```bash
git clone https://github.com/scientxst/Commerce-Agent-LLM.git
cd Commerce-Agent-LLM
cp .env.example .env
```

Edit `.env` and set these two required values:
- `OPENAI_API_KEY`: your OpenAI key (starts with `sk-`)
- `JWT_SECRET`: run `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` and paste the output

**2. Start Backend (Terminal 1)**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

cd backend
python -m app.main
```

Server starts at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

**3. Start Frontend (Terminal 2)**

```bash
cd frontend
npm install
npm run dev
```

Frontend opens at `http://localhost:3000`.

## You're Ready

The chat interface should now be open in your browser. Try asking:

- "I need comfortable shoes for a wedding under $150"
- "Show me the latest smartphones"
- "What headphones are good for travel?"

## What Happens Behind the Scenes

When you send a message:

1. **Intent Classification**: GPT-4 classifies your intent (Search, Browse, Purchase, etc.)
2. **Plan Generation**: Creates an execution plan
3. **Guardrails Check**: Validates against business rules
4. **Tool Execution**: Searches products using hybrid search (semantic + keyword) across multiple APIs
5. **Response Generation**: GPT-4 generates a natural language response
6. **Streaming**: Response streams back token-by-token via WebSocket

## Key Files

**Backend:**
- `backend/app/core/orchestrator.py` — Main ReAct reasoning loop
- `backend/app/services/vector_db.py` — Numpy-based semantic search
- `backend/app/tools/executor.py` — Tool implementations (search, cart, checkout)
- `backend/app/main.py` — FastAPI server and all endpoints

**Frontend:**
- `frontend/src/components/chat/ChatInterface.jsx` — Main chat UI with WebSocket streaming
- `frontend/src/components/product/ProductCard.jsx` — Product display cards
- `frontend/src/stores/authStore.js` — Authentication state management

## Troubleshooting

### Backend won't start?
- Verify your OpenAI API key in `.env`
- Make sure `JWT_SECRET` is set (at least 32 characters)
- Check that you are using Python 3.9 to 3.12 (not 3.13+)
- Check for port conflicts on 8000

### Frontend won't connect?
- Ensure backend is running on port 8000
- Use `npm run dev` (not `npm start`)
- Check browser console for errors
- Try hard refresh (Ctrl+Shift+R)

## Next Steps

1. Read the full [README.md](README.md) for architecture details
2. Explore the API docs at http://localhost:8000/docs
3. Modify `backend/data/sample_products.json` to add your own products
4. Customize the system prompt in `orchestrator.py`

---

Need help? Check the [README.md](README.md) or open an issue on GitHub.
