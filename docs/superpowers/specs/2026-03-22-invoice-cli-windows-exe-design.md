# Invoice CLI — Windows Standalone Exe Design

**Date:** 2026-03-22
**Status:** Approved

## Overview

Package the existing Python invoice CLI tool as a standalone Windows `.exe` that requires no prerequisites on the target PC, built automatically by GitHub Actions on every tagged release, and published as a private GitHub repository.

---

## Section 1: Code Changes

### 1a. Replace WeasyPrint with xhtml2pdf

WeasyPrint requires GTK system libraries (libcairo, libpango) which cannot be bundled cleanly by PyInstaller on Windows. Replace with `xhtml2pdf`, which is pure Python (uses reportlab under the hood) and bundles cleanly into a single exe.

**`requirements.txt`** — remove `weasyprint`, add `xhtml2pdf`.

**`invoice.py` — `generate_pdf()`** — swap WeasyPrint call for xhtml2pdf:

```python
from xhtml2pdf import pisa

def generate_pdf(html: str, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        pisa.CreatePDF(html, dest=f)
```

### 1b. Fix Windows strftime incompatibility

`helpers.py` uses `%-d` (Linux-only padding removal). Replace with cross-platform equivalent:

```python
def format_date_display(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"
```

### 1c. Rewrite template.html layout

`xhtml2pdf` does not support `display: flex`. The two flex sections (header, meta row) are converted to two-column `<table>` layouts. All other styling (colours, typography, borders, table items, totals, payment box, footer) is unchanged.

---

## Section 2: Security / .gitignore

**Files never committed:**

| File/Dir | Reason |
|---|---|
| `config.json` | SMTP credentials, bank account, personal details |
| `invoices.json` | Client data |
| `invoices/` | Generated PDFs |
| `venv/` | Local Python environment |
| `__pycache__/` | Bytecode cache |
| `build/`, `dist/`, `*.spec` | PyInstaller artefacts |

**`config.example.json`** committed with all fields present but values empty — serves as documentation for what config looks like without exposing real credentials.

---

## Section 3: PyInstaller + GitHub Actions

### 3a. PyInstaller spec

A `invoice.spec` file bundles:
- All Python source (`invoice.py`, `helpers.py`)
- `template.html` as a data file (extracted to temp dir at runtime)
- `--onefile` mode: single self-extracting `invoice.exe`
- Console application (CLI tool, no GUI window)

Template path resolved at runtime via:
```python
BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
```

### 3b. GitHub Actions workflow

**File:** `.github/workflows/build.yml`

**Trigger:** `push` to tags matching `v*` (e.g. `v1.0.0`)

**Steps (windows-latest runner):**
1. Checkout repo
2. Set up Python 3.11
3. Install dependencies (`pip install -r requirements.txt pyinstaller`)
4. Run PyInstaller with spec file
5. Upload `dist/invoice.exe` as a GitHub Release asset

The `.exe` is **not** committed to git — it lives only in GitHub Releases. Users download from the release page.

---

## Section 4: Standalone Config + Data Storage

### 4a. Config location

On Windows, config is stored at `%APPDATA%\invoice-tool\config.json` (typically `C:\Users\<name>\AppData\Roaming\invoice-tool\config.json`). This location:
- Is always writable by the user without admin rights
- Persists across exe updates/moves
- Is the standard Windows convention for per-user app data

**`invoice.py` — `BASE_DIR` and `CONFIG_FILE`:**
```python
import sys, os

def _app_data_dir() -> Path:
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', Path.home())) / 'invoice-tool'
    return Path.home() / '.invoice-tool'

APP_DATA_DIR = _app_data_dir()
CONFIG_FILE = APP_DATA_DIR / 'config.json'
INVOICES_FILE = APP_DATA_DIR / 'invoices.json'
```

### 4b. Invoices (PDFs) location

PDFs and the invoice log are saved to `Documents\Invoices\` (`~/Documents/Invoices/` cross-platform). This is easy for users to find and writable without admin rights.

```python
INVOICES_DIR = Path.home() / 'Documents' / 'Invoices'
```

### 4c. First-run flow

The existing `ensure_config()` function already detects missing fields and prompts interactively. On first launch the user is walked through:
1. Business name, address, email, phone
2. Bank payee name, sort code, account number
3. SMTP host, port, username, password, from address

Config is written to `%APPDATA%\invoice-tool\config.json`. Subsequent runs load silently — no prompts.

---

## Section 5: README

The README covers:
- What the tool does (one paragraph)
- Download link pointing to GitHub Releases
- First-run instructions (double-click, fill in settings)
- What gets saved where (`%APPDATA%`, `Documents\Invoices\`)
- How to re-run setup (delete `config.json` from `%APPDATA%`)
- For developers: how to run from source and how to trigger a release build

---

## Implementation Order

1. Update `requirements.txt` (remove weasyprint, add xhtml2pdf)
2. Fix `helpers.py` strftime
3. Update `invoice.py` — `generate_pdf()`, `_app_data_dir()`, paths
4. Update `BASE_DIR` resolution for frozen exe
5. Rewrite `template.html` flex → table layout
6. Add `.gitignore` and `config.example.json`
7. Create `invoice.spec` (PyInstaller)
8. Create `.github/workflows/build.yml`
9. Write `README.md`
10. Create private GitHub repo and push
11. Tag `v1.0.0` to trigger first release build
