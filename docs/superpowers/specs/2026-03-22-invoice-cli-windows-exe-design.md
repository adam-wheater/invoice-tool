# Invoice CLI — Windows Standalone Exe Design

**Date:** 2026-03-22
**Status:** Approved

## Overview

Package the existing Python invoice CLI tool as a standalone Windows `.exe` that requires no prerequisites on the target PC, built automatically by GitHub Actions on every tagged release, and published as a private GitHub repository.

---

## Section 1: Code Changes

### 1a. Replace WeasyPrint with xhtml2pdf

WeasyPrint requires GTK system libraries (libcairo, libpango) which cannot be bundled cleanly by PyInstaller on Windows. Replace with `xhtml2pdf`, which is pure Python (uses reportlab under the hood) and bundles cleanly into a single exe.

**`requirements.txt`** — remove `weasyprint`, add `xhtml2pdf`. Move `pytest` to a separate `requirements-dev.txt` so it is not bundled into the exe by PyInstaller.

**`invoice.py` — `generate_pdf()`** — swap WeasyPrint call for xhtml2pdf. The `pisa.CreatePDF` return value must be checked — xhtml2pdf does not raise on failure, it returns a status object where `.err` is truthy on error:

```python
from xhtml2pdf import pisa

def generate_pdf(html: str, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        result = pisa.CreatePDF(html, dest=f)
    if result.err:
        raise RuntimeError(f'PDF generation failed (xhtml2pdf error code {result.err})')
```

**`| safe` filter audit**: The Jinja2 environment uses `autoescape=True`. Two template locations use `| safe` to inject `<br>` for newlines in address fields — this is intentional and controlled (input comes from the user's own config/prompts, not external data). These callsites are reviewed as part of the template rewrite and remain safe.

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

**Files never committed** (update existing `.gitignore` — `invoices.json` is currently missing from it):

| File/Dir | Reason |
|---|---|
| `config.json` | SMTP credentials, bank account, personal details |
| `invoices.json` | Client data — currently missing from `.gitignore`, must be added |
| `invoices/` | Generated PDFs |
| `venv/` | Local Python environment |
| `__pycache__/` | Bytecode cache |
| `build/`, `dist/`, `*.spec` | PyInstaller artefacts |

**`run.sh`** is committed — it is a useful Linux/macOS dev launcher. The stale GTK/system-library setup comment at the top of `invoice.py` is removed as part of the code changes (those dependencies are gone).

**`config.example.json`** committed with all fields present but values empty — serves as documentation for what config looks like without exposing real credentials.

---

## Section 3: PyInstaller + GitHub Actions

### 3a. PyInstaller spec

A `invoice.spec` file bundles:
- All Python source (`invoice.py`, `helpers.py`)
- `template.html` as a data file (extracted to temp dir at runtime)
- `--onefile` mode: single self-extracting `invoice.exe`
- Console application (CLI tool, no GUI window)

Two separate path roots are required post-migration, replacing the single `BASE_DIR` in the current code:

- **`BUNDLE_DIR`** — where bundled data files (e.g. `template.html`) live at runtime. In a frozen exe PyInstaller extracts data files to a temp directory pointed to by `sys._MEIPASS`, not next to the exe. In development it is `Path(__file__).parent`.

```python
BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
TEMPLATE_FILE = BUNDLE_DIR / 'template.html'
```

- **`APP_DATA_DIR`** — where config and the invoice log live (see Section 4).

### 3b. PyInstaller spec file

Generate the base spec with `pyi-makespec --onefile invoice.py`, then edit the `datas` line in the resulting `invoice.spec` to bundle `template.html`:

```python
# invoice.spec (relevant section)
a = Analysis(
    ['invoice.py'],
    ...
    datas=[('template.html', '.')],   # copies template.html into root of bundle
    ...
)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='invoice',
    console=True,
    onefile=True,
)
```

The `('template.html', '.')` entry means: copy `template.html` from the project root into the `.` directory of `sys._MEIPASS` at runtime.

### 3c. GitHub Actions workflow

**File:** `.github/workflows/build.yml`

**Trigger:** `push` to tags matching `v*` (e.g. `v1.0.0`)

```yaml
permissions:
  contents: write   # required to create releases and upload assets

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt pyinstaller
      - run: pyinstaller invoice.spec
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/invoice.exe
```

`softprops/action-gh-release@v2` creates the GitHub Release (named after the tag) and attaches `invoice.exe` as a downloadable asset. `actions/upload-artifact` must NOT be used here — it stores workflow artifacts, not release assets.

The `.exe` is **not** committed to git — it lives only in GitHub Releases. Users download from the Releases page.

---

## Section 4: Standalone Config + Data Storage

### 4a. Config location

On Windows, config is stored at `%APPDATA%\invoice-tool\config.json` (typically `C:\Users\<name>\AppData\Roaming\invoice-tool\config.json`). This location:
- Is always writable by the user without admin rights
- Persists across exe updates/moves
- Is the standard Windows convention for per-user app data

**`invoice.py` — config path constants:**
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

`APP_DATA_DIR` must be created before any file writes (first run). This is done at startup: `APP_DATA_DIR.mkdir(parents=True, exist_ok=True)`.

### 4b. Invoices (PDFs) location

PDFs and the invoice log are saved to `Documents\Invoices\` (`~/Documents/Invoices/` cross-platform). This is easy for users to find and writable without admin rights.

```python
INVOICES_DIR = Path.home() / 'Documents' / 'Invoices'
```

**Critical: PDF paths stored as absolute strings.** The current code stores `pdf_path` as a path relative to `BASE_DIR`. After the migration, `BASE_DIR` no longer exists as a single concept, so relative paths would be unresolvable. The invoice log must store the **absolute** PDF path:

```python
# In finalise_invoice log_data:
'pdf_path': str(Path(out_path).resolve()),
```

And `resend_flow()` must look up the PDF directly by absolute path — no joining with any base directory:

```python
pdf_path = Path(record['pdf_path'])  # already absolute
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

1. Split `requirements.txt` → `requirements.txt` (runtime) and `requirements-dev.txt` (pytest); remove weasyprint, add xhtml2pdf to runtime
2. Fix `helpers.py` strftime (`%-d` → `f"{d.day} {d.strftime('%B %Y')}"`)
3. Update `invoice.py`:
   - Remove stale GTK setup comment from module docstring
   - Replace `BASE_DIR` with `BUNDLE_DIR` (for template) and `APP_DATA_DIR`/`CONFIG_FILE`/`INVOICES_FILE`/`INVOICES_DIR` (for data)
   - Add `APP_DATA_DIR.mkdir(parents=True, exist_ok=True)` at startup
   - Replace `generate_pdf()` with xhtml2pdf implementation (check `.err`)
   - Store `pdf_path` as absolute string in invoice log
   - Fix `resend_flow()` to use absolute PDF path directly
4. Rewrite `template.html` flex → table layout
5. Update `.gitignore` (add `invoices.json`, `build/`, `dist/`, `*.spec`)
6. Add `config.example.json`
7. Create `invoice.spec` (PyInstaller, `--onefile`, bundle `template.html`)
8. Create `.github/workflows/build.yml`
9. Write `README.md`
10. Create private GitHub repo and push
11. Tag `v1.0.0` to trigger first release build
