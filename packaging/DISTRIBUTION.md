# Stock Adda — Distribution Guide

Desktop builds bundle the FastAPI backend + React UI into a single launcher. **Build Mac on macOS, Windows on Windows** (PyInstaller is platform-specific).

## Quick build

### macOS

```bash
cd stock-analyzer-starter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/build-release.sh
./scripts/build-release.sh
```

**Outputs** (`dist/release/`):

| Artifact | Description |
| --- | --- |
| `StockAdda.app` | Double-click to run |
| `StockAdda-macOS-v0.6.0.dmg` | Installer disk image for sharing |
| `StockAdda-macOS-v0.6.0.zip` | Zipped `.app` |

### Windows

In PowerShell (from project root):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\scripts\build-release.ps1
```

**Outputs** (`dist\release\`):

| Artifact | Description |
| --- | --- |
| `StockAdda\StockAdda.exe` | Run this executable |
| `StockAdda-Windows-v0.6.0.zip` | Share the whole folder |

## First launch (end users)

1. Open the app — a browser tab opens at `http://127.0.0.1:8000`.
2. User data is stored outside the app bundle:

   | OS | Location |
   | --- | --- |
   | macOS | `~/Library/Application Support/StockAdda` |
   | Windows | `%LOCALAPPDATA%\StockAdda` |
   | Linux | `~/.stockadda` |

3. Copy `.env.example` → `.env` in that folder (done automatically on first run) and add API keys / broker credentials.
4. Optional: install [Ollama](https://ollama.com) for local LLM + embeddings.

Override data directory:

```bash
export STOCK_ADDA_DATA=/path/to/data   # macOS/Linux
set STOCK_ADDA_DATA=C:\path\to\data    # Windows
```

## What is bundled

- Python runtime + dependencies (FastAPI, pandas, chromadb, broker SDKs, …)
- Built React UI (`frontend/dist`)
- Nifty 500 universe list + quant foundation seeds
- Sample JSON files

**Not bundled** (downloaded or created at runtime):

- Historical price cache (`data/raw/`)
- User trading ledger, pick log, Chroma insights
- PDF books (user drops into `data/books/`)

## Development vs packaged mode

| | Dev (`./scripts/dev.sh`) | Packaged (`StockAdda`) |
| --- | --- | --- |
| UI | Vite dev server `:5173` | Served by API `:8000` |
| Data | `./data/` in repo | User app-support folder |
| Hot reload | Yes | No |

## Code signing (optional)

- **macOS**: `codesign --deep --force --sign "Developer ID" dist/release/StockAdda.app`
- **Windows**: Sign `StockAdda.exe` with your Authenticode certificate to reduce SmartScreen warnings.

## Source distribution

To ship source instead of a binary:

```bash
git archive --format=zip --prefix=stock-adda/ HEAD -o dist/release/stock-adda-source.zip
```

Users then follow the main `README.md` setup (`venv`, `npm install`, `./scripts/dev.sh`).

## Troubleshooting builds

- **Frontend missing**: run `cd frontend && npm run build` before PyInstaller.
- **Bundle seed missing**: run `python packaging/prepare_bundle_data.py`.
- **PyInstaller import errors**: add the module to `hiddenimports` in `packaging/stock_adda.spec`.
- **Large artifact (~500MB+)**: expected with pandas + chromadb; use the zip/dmg, not git.
