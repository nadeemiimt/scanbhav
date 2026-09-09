# Scan Bhav — Local Stock Analyzer (Ollama + Chroma RAG)

**New clone?** Follow [SETUP.md](SETUP.md) for install, Ollama, RAG, and autopilot desk setup.

This project keeps your PDFs, embeddings, vector database, and LLM calls on your machine. Your books teach the evaluation framework; the stock JSON supplies the company facts.

## 1. Prerequisites

You already have Chroma and Ollama. Confirm Ollama is reachable and identify the exact Llama model name:

```bash
ollama list
ollama pull mxbai-embed-large:latest
```

Create a virtual environment and install the project dependencies:

```bash
cd stock-analyzer-starter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your private configuration file and add your own Alpha Vantage key. `.env` is ignored by Git and must not be shared:

```bash
cp .env.example .env
# Edit .env in a text editor and replace only this value:
# ALPHAVANTAGE_API_KEY=replace_with_your_secret_key
```

`LLM_MODEL=llama3.1:8b` and `EMBEDDING_MODEL=mxbai-embed-large:latest` are already the defaults in `.env.example`.

## 2. Build the knowledge base

Copy your two PDFs into `data/books/`, then run:

```bash
python ingest_books.py --reset
```

The command prints the number of chunks indexed. Re-run it with `--reset` after replacing or modifying a PDF. Chroma data is stored locally at `data/chroma/`.

If a PDF is scanned images rather than selectable text, OCR it first; `pypdf` only extracts embedded text.

## 3. Fetch market and fundamental data

Use a provider symbol such as `RELIANCE.BSE`. Fetch five years of adjusted daily prices first:

```bash
python fetch_stock_data.py RELIANCE.BSE --years 5
```

For richer fundamental analysis, fetch the supported financial statements as well. This performs multiple API calls and follows the delay set in `.env`:

```bash
python fetch_stock_data.py RELIANCE.BSE --years 5 --fundamentals --news
python build_stock_input.py RELIANCE.BSE
```

Raw, timestamped provider replies go to `data/raw/RELIANCE.BSE/`. The generated analyzer input is written to `data/stock_inputs/RELIANCE.BSE.json`. These folders are intentionally excluded from Git because they can be recreated and may be subject to data-provider terms.

Five-year `outputsize=full` daily history and historical intraday access require an Alpha Vantage plan that permits those endpoints. The command-line tool uses free providers by default, while Alpha Vantage remains available for optional fundamental/news calls.

By default, `--provider auto` uses Yahoo Finance and falls back to NSE's public historical endpoint for NSE-listed equities. Alpha Vantage is only used when explicitly selected for prices or when you request its optional fundamentals/news data. You can select a provider explicitly:

```bash
python fetch_stock_data.py RELIANCE.BSE --years 5 --provider yfinance
python fetch_stock_data.py RELIANCE.NSE --years 5 --provider nse
python fetch_stock_data.py RELIANCE.BSE --years 5 --provider alpha
```

Yahoo uses `.BO` for BSE and `.NS` for NSE, while this project accepts either the Alpha Vantage-style `RELIANCE.BSE` / `RELIANCE.NSE` name or the Yahoo form. Yahoo Finance is a fallback data source, not an official exchange feed; validate any trading research against a licensed or exchange/broker data feed before acting on it.

## 4. Analyze a stock JSON file

Start from `samples/example_stock.json`, replace the placeholder fields with your own data, then run:

```bash
python analyze.py samples/example_stock.json
```

Or analyze data generated from Alpha Vantage:

```bash
python analyze.py data/stock_inputs/RELIANCE.BSE.json
```

The result is JSON containing a verdict, framework checks, missing data, research questions, and the book page/chunk references retrieved for that analysis.

## 5. React dashboard + API server

The Python app is now a FastAPI backend and `frontend/` is a React dashboard.

**One command (auto-restart if either process stops):**

```bash
./scripts/dev.sh
```

- UI: `http://127.0.0.1:5173` (Vite proxies `/api` → backend)
- API health: `http://127.0.0.1:8000/health`
- Set `RESTART=0 ./scripts/dev.sh` to disable auto-restart

**Or two terminals manually:**

Terminal 1 — backend:

```bash
uvicorn api:app --reload --port 8000
```

Terminal 2 — React app:

```bash
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`), or after `npm run build` open `http://127.0.0.1:8000`.

## 6. Desktop distribution (Mac & Windows)

Ship a standalone app (no Python/Node install for end users):

| Platform | Build command | Output |
| --- | --- | --- |
| **macOS** | `./scripts/build-release.sh` | `dist/release/ScanBhav.app`, `.dmg`, `.zip` |
| **Windows** | `.\scripts\build-release.ps1` | `dist\release\ScanBhav\ScanBhav.exe` + `.zip` |

Build **Mac on macOS** and **Windows on Windows** (PyInstaller is platform-specific).

First launch opens `http://127.0.0.1:8000` and stores user data in:

- macOS: `~/Library/Application Support/ScanBhav`
- Windows: `%LOCALAPPDATA%\ScanBhav`

Full details: [packaging/DISTRIBUTION.md](packaging/DISTRIBUTION.md)

### Feature tabs (revamped)

| Tab | What it does |
| --- | --- |
| **Single Stock Analysis** | Full technicals (SMA/EMA/RSI/MACD/Bollinger/ATR/Stochastic/ADX/Supertrend/volume) + scores for 1D, 1W, 1M, 3M, 6M, 9M, 1Y, 2Y, 3Y, 5Y |
| **Multi Stock Screen (~200)** | Scores a liquid NSE universe with the same engine and ranks by selected horizon |

Key TA routes:

- `POST /api/ta/analyze` — single-stock technical analysis + horizon ratings
- `POST /api/ta/screen` — multi-stock screen (`limit`, `horizon`, `force_refresh`)
- `GET /api/ta/universe` — screened symbol list
- `GET /api/ta/horizons` — horizon definitions
- `GET /api/search?q=` — name/code search

Educational technical screens only — not investment advice or forecasts.

## 6. API documentation only

Run:

```bash
uvicorn api:app --reload --port 8000
```

Then submit JSON from another terminal:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  --data @samples/example_stock.json
```

Interactive API documentation is at `http://127.0.0.1:8000/docs`.

## Guardrails built in

- The prompt tells the model not to invent stock data or sources.
- The model must return JSON, with citations limited to retrieved book passages.
- The output is educational analysis, not personalized investment advice.
- Calculation-heavy metrics should be computed upstream and passed into the input JSON rather than left to the language model.
- A prediction must be backtested against unseen data with fees and slippage; it is not a trade recommendation or a promise of intraday performance.

## Suggested improvements

Add historical quarterly fundamentals, earnings-call notes, and a deterministic scorecard in Python. Evaluate the result against a small set of known companies before treating it as part of a real research workflow. Paper-trade results assume a simple fee and use end-of-day closes — they are not a broker-grade backtest with slippage or taxes.
