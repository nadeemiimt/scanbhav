# Stock Adda — Setup Guide

Local stock research, quant autopilot desk, and RAG-backed analysis.  
**Private deployment:** never commit `.env` or broker keys.

---

## Prerequisites

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | 3.9+ | Backend API |
| Node.js | 18+ | Frontend build |
| Git | any | Clone & updates |
| Ollama | latest | Local LLM + embeddings (optional but recommended) |

Optional: Zerodha / Groww / FYERS credentials for live trading; Finnhub/Alpha Vantage keys for enrichment.

---

## 1. Clone (private GitHub repo)

```bash
git clone git@github.com:YOUR_USERNAME/stock-adda.git
cd stock-adda
```

Or HTTPS:

```bash
git clone https://github.com/YOUR_USERNAME/stock-adda.git
```

---

## 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Configuration

```bash
cp .env.example .env
```

Edit `.env` — minimum for local research:

```env
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=mxbai-embed-large:latest
LLM_MODEL=llama3.2:3b
GENAI_PROVIDER=ollama
```

Generate a production JWT secret:

```bash
openssl rand -hex 32
# paste into AUTH_JWT_SECRET=
```

**Production / public host:**

```env
AUTH_ALLOW_DEV=false
FRONTEND_URL=https://your-domain.com
AUTH_CALLBACK_BASE=https://your-domain.com
```

Configure at least one OAuth provider (Google, GitHub, etc.) or keep the app behind VPN + reverse-proxy auth.

---

## 4. Ollama + RAG (local LLM)

```bash
# Install Ollama: https://ollama.com
ollama pull mxbai-embed-large:latest
ollama pull llama3.2:3b
```

Add investment PDFs to `data/books/`, then index:

```bash
python ingest_books.py --reset
```

Chroma stores vectors under `data/chroma/` (gitignored).

---

## 5. Frontend

```bash
cd frontend
npm install
cd ..
```

---

## 6. Run (development)

**One command** (API + Vite UI):

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

| Service | URL |
| --- | --- |
| UI | http://127.0.0.1:5173 |
| API | http://127.0.0.1:8000/health |

**Production-style** (built UI served by API):

```bash
cd frontend && npm run build && cd ..
uvicorn api:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

---

## 7. Desktop app (optional)

Build installers on each platform (see `packaging/DISTRIBUTION.md`):

```bash
./scripts/build-release.sh              # macOS → .app / .dmg
# Windows: .\scripts\build-release.ps1
```

User data lives outside the bundle:

- macOS: `~/Library/Application Support/StockAdda`
- Windows: `%LOCALAPPDATA%\StockAdda`

---

## 8. Autopilot / trading desk

1. Open **Autopilot** tab → configure paper mode first (`TRADING_EXECUTION_MODE=paper`).
2. Run **Daily universe job** before market open.
3. **Auto Pick** = primary desk; **Curated** = test desk.
4. Reset stale learning: **Reset RAG / learning** (Autopilot → Quant panel).

Broker live trading requires SDK credentials in `.env` and explicit arm-live flow — see `.env.example` broker section.

---

## 9. Public host security (summary)

- Bind Ollama to `127.0.0.1:11434` only — never expose port 11434.
- Put **nginx/Caddy** in front with TLS + IP allowlist.
- Set `AUTH_ALLOW_DEV=false`; use OAuth or VPN.
- Full guide: ask for deployment doc or see conversation notes on reverse-proxy setup.

---

## 10. Troubleshooting

| Issue | Fix |
| --- | --- |
| Empty RAG answers | Run `python ingest_books.py --reset` |
| Ollama connection refused | `ollama serve` or restart Ollama app |
| UI blank after deploy | `cd frontend && npm run build` |
| Port in use | `FREE_PORTS=1 ./scripts/dev.sh` |
| Curated desk not buying | Check RAG blocks; run learning reset |

---

## What is NOT in git (created at runtime)

- `.env` — secrets
- `data/raw/` — downloaded prices
- `data/trading/` — ledger, pick log, sessions
- `data/chroma/` — vector DB
- `frontend/node_modules/`, `dist/`, `.venv/`

After clone, run steps 2–6 above to become operational.
