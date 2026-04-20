#!/usr/bin/env bash
set -euo pipefail

echo "=== Commerce-Agent-LLM Setup ==="
echo ""

# ── Check Python version (3.9 to 3.12) ──────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [[ "$major" -eq 3 && "$minor" -ge 9 && "$minor" -le 12 ]]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "ERROR: Python 3.9 to 3.12 is required but not found."
  echo "       Install it from https://www.python.org/downloads/"
  echo "       (Python 3.13+ is not yet supported by some dependencies.)"
  exit 1
fi
echo "Using $($PYTHON --version)"

# ── Check Node.js version (>=16) ────────────────────────────
if ! command -v node &>/dev/null; then
  echo "ERROR: Node.js is required but not found."
  echo "       Install it from https://nodejs.org/"
  exit 1
fi
NODE_VER=$(node --version | grep -oE '[0-9]+' | head -1)
if [[ "$NODE_VER" -lt 16 ]]; then
  echo "ERROR: Node.js 16+ is required (found $(node --version))."
  exit 1
fi
echo "Using Node.js $(node --version)"
echo ""

# ── Create .env from template ────────────────────────────────
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists, skipping copy"
fi

# ── Auto-generate JWT_SECRET if still placeholder ────────────
if grep -q "CHANGE-ME" .env 2>/dev/null; then
  JWT=$($PYTHON -c "import secrets; print(secrets.token_urlsafe(48))")
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/^JWT_SECRET=.*/JWT_SECRET=$JWT/" .env
  else
    sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$JWT/" .env
  fi
  echo "Generated JWT_SECRET automatically"
fi

# ── Prompt for OpenAI API key if still placeholder ───────────
if grep -q "your_openai_api_key_here" .env 2>/dev/null; then
  echo ""
  echo "Enter your OpenAI API key (starts with sk-):"
  read -r API_KEY
  if [[ -n "$API_KEY" ]]; then
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s/^OPENAI_API_KEY=.*/OPENAI_API_KEY=$API_KEY/" .env
    else
      sed -i "s/^OPENAI_API_KEY=.*/OPENAI_API_KEY=$API_KEY/" .env
    fi
    echo "OpenAI API key saved"
  fi
fi

echo ""

# ── Create Python venv and install backend deps ─────────────
echo "Setting up Python virtual environment..."
$PYTHON -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r backend/requirements.txt -q
echo "Backend dependencies installed"

# ── Install frontend deps ───────────────────────────────────
echo "Installing frontend dependencies..."
cd frontend && npm install --silent 2>/dev/null && cd ..
echo "Frontend dependencies installed"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To run the application, open TWO terminal windows:"
echo ""
echo "  Terminal 1 (Backend):"
echo "    source venv/bin/activate"
echo "    cd backend"
echo "    python -m app.main"
echo ""
echo "  Terminal 2 (Frontend):"
echo "    cd frontend"
echo "    npm run dev"
echo ""
echo "Then open http://localhost:3000 in your browser."
