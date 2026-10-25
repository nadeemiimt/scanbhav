# Scan Bhav — Distribution Guide

Desktop builds bundle the FastAPI backend + React UI into a single launcher. **Build Mac on macOS, Windows on Windows** (PyInstaller is platform-specific).

## Quick build

PyInstaller builds are **platform-native**: Mac on macOS, Windows on Windows (or use GitHub Actions → **Desktop packages** workflow → download artifacts).

### macOS

```bash
cd stock-analyzer-starter
python3 -m venv .venv && source .venv/bin/activate
export SCAN_BHAV_INSTALL_PACKAGING=1
./scripts/install-python-deps.sh
chmod +x scripts/build-release.sh
./scripts/build-release.sh
```

> Broker note: `fyers-apiv3` pins old `requests`/`aiohttp` that conflict with `growwapi`. The install script loads FYERS with `--no-deps` so Mac/Windows CI can resolve.

**Outputs** (`dist/release/`):

| Artifact | Description |
| --- | --- |
| `ScanBhav.app` | Double-click to run |
| `ScanBhav-macOS-v0.6.0.dmg` | Installer disk image for sharing |
| `ScanBhav-macOS-v0.6.0.zip` | Zipped `.app` |

### Windows

In PowerShell (from project root on a Windows machine):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:SCAN_BHAV_INSTALL_PACKAGING = "1"
.\scripts\install-python-deps.ps1
.\scripts\build-release.ps1
```

**Outputs** (`dist\release\`):

| Artifact | Description |
| --- | --- |
| `ScanBhav\ScanBhav.exe` | Run this executable |
| `ScanBhav-Windows-v0.6.0.zip` | Share the whole folder |

### CI (both platforms)

GitHub Actions workflow `.github/workflows/desktop-packages.yml` builds Mac + Windows on `workflow_dispatch` or version tags. Download the `ScanBhav-macOS` and `ScanBhav-Windows` artifacts from the run.

## Prerequisites for external users (shared .exe / .app)

**You do not install Python, Node, or pip.** Those are already inside the package.

| | Windows | Mac |
| --- | --- | --- |
| OS | 64-bit Windows 10 or 11 | macOS 12+ (Apple Silicon arm64 build from CI) |
| Required software | None beyond a browser | None beyond a browser |
| First open | Unzip → run `ScanBhav.exe` (keep `_internal` next to it) | Open `ScanBhav.app` or the `.dmg` |
| Gatekeeper / SmartScreen | “More info → Run anyway” if unsigned | Right-click → Open the first time if unsigned |
| Optional | [Ollama](https://ollama.com) for local GenAI; VC++ x64 redistributable only if a DLL error appears | [Ollama](https://ollama.com) for local GenAI |
| API keys | Optional — Settings → Your API keys | Same |

First launch opens a **setup panel** (also under Settings → Run on this computer) that can:
- Install / open **Ollama** (`winget` / `brew` when available, otherwise the download page)
- Open the **VC++ Redistributable** download on Windows
- Explain that core Analyze / Screener / Paper / Backtest need **no token**

## Tokens required to run

**Core desk needs no API key.** Analyze, Screener, horizon picks, paper Autopilot, and backtests use Yahoo Finance + NSE public data.

| Need | Token | Where to set |
| --- | --- | --- |
| Core (paper) | None | — |
| GenAI notes | OpenAI or Anthropic key, **or** local [Ollama](https://ollama.com) | Settings → Your API keys |
| Backup prices / news | Alpha Vantage, Finnhub | Settings → Your API keys |
| Cursor code learning | Cursor API key | Settings → Your API keys (only if you allow edits) |
| Live ticks / live orders | Zerodha / Groww / FYERS app key + secret, then daily OAuth | Settings → Broker app keys, then Accounts |

Keys saved in the UI live in `data/user_secrets.json` under the user data folder (never shipped in the installer). Clear from the same Settings panel.

## First launch (end users)

1. Open the app — a browser tab opens at `http://127.0.0.1:8000`.
2. User data is stored outside the app bundle:

   | OS | Location |
   | --- | --- |
   | macOS | `~/Library/Application Support/ScanBhav` |
   | Windows | `%LOCALAPPDATA%\ScanBhav` |
   | Linux | `~/.scanbhav` |

3. Open **Settings → Your API keys** for the token guide and optional keys. `.env` in the data folder still works as an override.
4. Optional: install [Ollama](https://ollama.com) for local LLM + embeddings.

Override data directory:

```bash
export SCAN_BHAV_DATA=/path/to/data   # macOS/Linux
set SCAN_BHAV_DATA=C:\path\to\data    # Windows
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

| | Dev (`./scripts/dev.sh`) | Packaged (`ScanBhav`) |
| --- | --- | --- |
| UI | Vite dev server `:5173` | Served by API `:8000` |
| Data | `./data/` in repo | User app-support folder |
| Hot reload | Yes | No |

## Code signing (optional)

- **macOS**: `codesign --deep --force --sign "Developer ID" dist/release/ScanBhav.app`
- **Windows**: Sign `ScanBhav.exe` with your Authenticode certificate to reduce SmartScreen warnings.

## Source distribution

To ship source instead of a binary:

```bash
git archive --format=zip --prefix=scan-bhav/ HEAD -o dist/release/scan-bhav-source.zip
```

Users then follow the main `README.md` setup (`venv`, `npm install`, `./scripts/dev.sh`).

## Troubleshooting builds

- **Frontend missing**: run `cd frontend && npm run build` before PyInstaller.
- **Bundle seed missing**: run `python packaging/prepare_bundle_data.py`.
- **PyInstaller import errors**: add the module to `hiddenimports` in `packaging/scan_bhav.spec`.
- **Large artifact (~500MB+)**: expected with pandas + chromadb; use the zip/dmg, not git.
