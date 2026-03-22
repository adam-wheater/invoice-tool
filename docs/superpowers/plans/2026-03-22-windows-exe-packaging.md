# Invoice CLI — Windows Standalone Exe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the existing Python invoice CLI as a standalone `invoice.exe` for Windows — no prerequisites required, first-run prompts for all settings, built by GitHub Actions on every tagged release.

**Architecture:** Replace WeasyPrint (requires GTK system libs) with xhtml2pdf (pure Python). Rewrite the HTML template's flex layouts as tables for xhtml2pdf compatibility. Move config/data storage from the script directory to platform-appropriate locations (`%APPDATA%` for config, `~/Documents/Invoices` for PDFs). PyInstaller bundles everything into one `.exe`; GitHub Actions runs the build on a Windows runner and uploads the binary to the GitHub Release.

**Tech Stack:** Python 3.11, xhtml2pdf, Jinja2, PyInstaller, GitHub Actions (`softprops/action-gh-release@v2`)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `requirements.txt` | Modify | Remove weasyprint, add xhtml2pdf |
| `requirements-dev.txt` | Create | pytest (dev-only, not bundled into exe) |
| `helpers.py` | Modify | Fix `%-d` strftime (Linux-only) |
| `invoice.py` | Modify | New path constants, xhtml2pdf, absolute PDF paths |
| `template.html` | Modify | Replace flex with table layout |
| `.gitignore` | Modify | Add invoices.json, build/, dist/ (NOT *.spec — invoice.spec must be committed) |
| `config.example.json` | Create | Blank-value template committed to repo |
| `invoice.spec` | Create | PyInstaller bundle config |
| `.github/workflows/build.yml` | Create | GitHub Actions release build |
| `README.md` | Create | User-facing docs |
| `tests/test_helpers.py` | No change | format_date_display output unchanged |
| `tests/test_invoice.py` | No change | All patches still valid; CONFIG_FILE remains module-level attr |

---

## Task 1: Split requirements + install xhtml2pdf

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`

- [ ] **Step 1: Update requirements.txt**

Replace contents with:

```
xhtml2pdf==0.2.16
jinja2==3.1.6
```

(Remove `weasyprint==68.1` and `pytest==9.0.2`)

- [ ] **Step 2: Create requirements-dev.txt**

```
pytest==9.0.2
```

- [ ] **Step 3: Install xhtml2pdf in the local venv**

```bash
cd /root/invoice-tool
venv/bin/pip install xhtml2pdf==0.2.16
```

Expected output: `Successfully installed xhtml2pdf-0.2.16 ...`

- [ ] **Step 4: Run existing tests to confirm baseline still passes**

```bash
cd /root/invoice-tool
venv/bin/pytest tests/ -v
```

Expected: All tests pass (weasyprint is not exercised by any test).

- [ ] **Step 5: Commit**

```bash
cd /root/invoice-tool
git add requirements.txt requirements-dev.txt
git commit -m "chore: replace weasyprint with xhtml2pdf, split dev requirements"
```

---

## Task 2: Fix strftime in helpers.py

**Files:**
- Modify: `helpers.py:73` (the `format_date_display` function)

The current implementation uses `%-d` which is Linux-only and crashes on Windows.

- [ ] **Step 1: Verify existing tests pass for format_date_display**

```bash
cd /root/invoice-tool
venv/bin/pytest tests/test_helpers.py::test_format_date_display tests/test_helpers.py::test_format_date_display_single_digit_day -v
```

Expected: Both PASS.

- [ ] **Step 2: Edit helpers.py — replace format_date_display**

Find in `helpers.py`:
```python
def format_date_display(d: date) -> str:
    """Format a date as '16 April 2026'."""
    return d.strftime('%-d %B %Y')
```

Replace with:
```python
def format_date_display(d: date) -> str:
    """Format a date as '16 April 2026'."""
    return f"{d.day} {d.strftime('%B %Y')}"
```

- [ ] **Step 3: Run tests — must still pass with identical output**

```bash
cd /root/invoice-tool
venv/bin/pytest tests/test_helpers.py -v
```

Expected: All PASS. The new implementation produces identical output (`d.day` is an int, so `5` not `05`).

- [ ] **Step 4: Commit**

```bash
cd /root/invoice-tool
git add helpers.py
git commit -m "fix: cross-platform date formatting (%-d unsupported on Windows)"
```

---

## Task 3: Update invoice.py — path constants + generate_pdf + resend

**Files:**
- Modify: `invoice.py`

This task has four sub-changes: (a) new path constants, (b) new generate_pdf, (c) absolute PDF path on save, (d) absolute PDF path on resend lookup.

### 3a — Path constants

- [ ] **Step 1: Remove stale module docstring lines**

At the top of `invoice.py`, the docstring includes:
```
SETUP (one-time):
  sudo apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
  pip install -r requirements.txt
```

Replace the entire docstring with:
```python
"""
Invoice Generator
=================
Generates professional PDF invoices and emails them via SMTP.

USAGE:
  python invoice.py
"""
```

- [ ] **Step 2: Replace the import block for weasyprint**

Find:
```python
import jinja2
import weasyprint
```

Replace with:
```python
import jinja2
from xhtml2pdf import pisa
```

- [ ] **Step 3: Replace path constants**

Find the block:
```python
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'config.json'
INVOICES_FILE = BASE_DIR / 'invoices.json'
INVOICES_DIR = BASE_DIR / 'invoices'
TEMPLATE_FILE = BASE_DIR / 'template.html'
```

Replace with:
```python
# Template is bundled inside the exe (sys._MEIPASS) or lives next to this file in dev
BUNDLE_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
TEMPLATE_FILE = BUNDLE_DIR / 'template.html'

# User data lives in platform-appropriate writable locations
def _app_data_dir() -> Path:
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', Path.home())) / 'invoice-tool'
    return Path.home() / '.invoice-tool'

APP_DATA_DIR = _app_data_dir()
CONFIG_FILE = APP_DATA_DIR / 'config.json'
INVOICES_FILE = APP_DATA_DIR / 'invoices.json'
INVOICES_DIR = Path.home() / 'Documents' / 'Invoices'
```

Note: both `sys` and `os` are already imported in `invoice.py` — no new imports needed.

- [ ] **Step 4: Add mkdir guard to _save_config**

Find:
```python
def _save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
```

Replace with:
```python
def _save_config(config: dict) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
```

- [ ] **Step 5: Add mkdir guard to _save_invoices**

Find:
```python
def _save_invoices(records: list) -> None:
    INVOICES_FILE.write_text(json.dumps(records, indent=2, default=str))
```

Replace with:
```python
def _save_invoices(records: list) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    INVOICES_FILE.write_text(json.dumps(records, indent=2, default=str))
```

### 3b — Replace generate_pdf

- [ ] **Step 6: Replace generate_pdf**

Find:
```python
def generate_pdf(html: str, output_path: str) -> None:
    """Convert HTML string to PDF and save to output_path."""
    INVOICES_DIR.mkdir(exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(output_path)
```

Replace with:
```python
def generate_pdf(html: str, output_path: str) -> None:
    """Convert HTML string to PDF and save to output_path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        result = pisa.CreatePDF(html, dest=f)
    if result.err:
        raise RuntimeError(f'PDF generation failed (xhtml2pdf error code {result.err})')
```

### 3c — Store absolute PDF path

- [ ] **Step 7: Fix finalise_invoice log_data — absolute path**

In `main()`, find the `log_data` dict construction (near the bottom, after "9. Finalise log"):
```python
        'pdf_path': str(Path(out_path).relative_to(BASE_DIR)),
```

Replace with:
```python
        'pdf_path': str(Path(out_path).resolve()),
```

### 3d — Fix resend_flow PDF lookup

- [ ] **Step 8: Fix resend_flow — use absolute path directly**

In `resend_flow()`, find:
```python
    pdf_path = BASE_DIR / record['pdf_path']
```

Replace with:
```python
    pdf_path = Path(record['pdf_path'])
```

- [ ] **Step 9: Run the full test suite**

```bash
cd /root/invoice-tool
venv/bin/pytest tests/ -v
```

Expected: All tests pass. The tests patch `invoice.CONFIG_FILE` which still exists as a module attribute.

If any test fails because `invoice.CONFIG_FILE` path changed: the test patches `invoice.CONFIG_FILE` directly via `monkeypatch.setattr(invoice, 'CONFIG_FILE', ...)` which still works — CONFIG_FILE is still a module-level attribute on `invoice`.

- [ ] **Step 10: Commit**

```bash
cd /root/invoice-tool
git add invoice.py
git commit -m "feat: platform-aware paths, xhtml2pdf PDF generation, absolute invoice log paths"
```

---

## Task 4: Rewrite template.html — flex to table layout

**Files:**
- Modify: `template.html`

xhtml2pdf supports CSS 2.1 and `<table>` layout but not `display: flex`. Three flex sections need converting: header, meta row, totals.

- [ ] **Step 1: Replace the full template.html**

Overwrite `template.html` with the following (all CSS colours, borders, typography unchanged):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 13px; color: #333; background: #fff;
  }
  .page { max-width: 740px; margin: 0 auto; padding: 40px; }

  /* Header */
  .header { width: 100%; border-bottom: 3px solid #1a2e4a; margin-bottom: 40px; padding-bottom: 20px; }
  .header td { vertical-align: top; }
  .business-name { font-size: 22px; font-weight: bold; color: #1a2e4a; }
  .business-details { font-size: 11px; color: #666; margin-top: 6px; line-height: 1.6; }
  .invoice-title { text-align: right; }
  .invoice-title h1 {
    font-size: 28px; font-weight: 300; color: #1a2e4a;
    letter-spacing: 3px; text-transform: uppercase;
  }
  .invoice-number { font-size: 14px; font-weight: bold; color: #1a2e4a; margin-top: 4px; }

  /* Meta row */
  .meta { width: 100%; margin-bottom: 30px; }
  .meta td { vertical-align: top; }
  .bill-to h3, .dates h3 {
    font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    color: #999; margin-bottom: 8px;
  }
  .bill-to p { font-size: 12px; line-height: 1.7; }
  .dates { text-align: right; }
  .dates table { margin-left: auto; }
  .dates td { padding: 2px 0 2px 20px; font-size: 12px; }
  .dates td:first-child { color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
  .dates td:last-child { font-weight: bold; }

  /* Line items table */
  table.items { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
  table.items thead th {
    background: #1a2e4a; color: #fff; font-size: 10px;
    text-transform: uppercase; letter-spacing: 1px; padding: 10px 12px; text-align: left;
  }
  table.items thead th.right { text-align: right; }
  table.items tbody td {
    padding: 10px 12px; border-bottom: 1px solid #f0f0f0;
    font-size: 12px; vertical-align: top;
  }
  table.items tbody td.right { text-align: right; }
  table.items tbody tr:last-child td { border-bottom: none; }

  /* Totals */
  .totals { width: 100%; margin-bottom: 30px; }
  .totals-inner { width: 260px; }
  .totals-inner table { width: 100%; }
  .totals-inner td { padding: 4px 0; font-size: 12px; }
  .totals-inner td:last-child { text-align: right; padding-left: 20px; }
  .totals-inner .total-row td {
    font-size: 15px; font-weight: bold; color: #1a2e4a;
    border-top: 2px solid #1a2e4a; padding-top: 8px;
  }

  /* Payment details */
  .payment {
    background: #f7f9fc; border-left: 4px solid #1a2e4a;
    padding: 16px 20px; margin-bottom: 20px;
  }
  .payment h3 {
    font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    color: #999; margin-bottom: 10px;
  }
  .payment table td { font-size: 12px; padding: 3px 0; }
  .payment table td:first-child { color: #666; width: 130px; }
  .payment table td:last-child { font-weight: bold; }

  /* Notes */
  .notes { margin-bottom: 20px; }
  .notes h3 {
    font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    color: #999; margin-bottom: 6px;
  }
  .notes p { font-size: 12px; line-height: 1.6; color: #555; }

  /* Footer */
  .footer {
    text-align: center; font-size: 10px; color: #bbb;
    padding-top: 20px; border-top: 1px solid #eee; margin-top: 20px;
  }
</style>
</head>
<body>
<div class="page">

  <table class="header" width="100%">
    <tr>
      <td>
        <div class="business-name">{{ business_name }}</div>
        <div class="business-details">
          {{ business_address | replace('\n', '<br>') | safe }}<br>
          {{ business_email }}<br>
          {{ business_phone }}
        </div>
      </td>
      <td class="invoice-title">
        <h1>Invoice</h1>
        <div class="invoice-number">{{ number }}</div>
      </td>
    </tr>
  </table>

  <table class="meta" width="100%">
    <tr>
      <td class="bill-to">
        <h3>Bill To</h3>
        <p>
          <strong>{{ client_name }}</strong><br>
          {{ client_email }}
          {% if client_address %}
          <br>{{ client_address | replace('\n', '<br>') | safe }}
          {% endif %}
        </p>
      </td>
      <td class="dates">
        <h3>Details</h3>
        <table>
          <tr><td>Invoice Date</td><td>{{ date_issued.strftime('%d %b %Y') }}</td></tr>
          <tr><td>Due Date</td><td>{{ date_due.strftime('%d %b %Y') }}</td></tr>
        </table>
      </td>
    </tr>
  </table>

  <table class="items">
    <thead>
      <tr>
        <th>Description</th>
        <th class="right" style="width:70px">Qty</th>
        <th class="right" style="width:110px">Unit Price</th>
        <th class="right" style="width:110px">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for item in line_items %}
      <tr>
        <td>{{ item.description }}</td>
        <td class="right">{{ item.qty | int if item.qty == (item.qty | int) else item.qty }}</td>
        <td class="right">&#163;{{ "%.2f" | format(item.unit_price) }}</td>
        <td class="right">&#163;{{ "%.2f" | format(item.qty * item.unit_price) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <table class="totals" width="100%">
    <tr>
      <td></td>
      <td width="260">
        <div class="totals-inner">
          <table>
            <tr><td>Subtotal</td><td>&#163;{{ "%.2f" | format(totals.subtotal) }}</td></tr>
            {% if vat_applied %}
            <tr><td>VAT (20%)</td><td>&#163;{{ "%.2f" | format(totals.vat) }}</td></tr>
            {% endif %}
            <tr class="total-row"><td>Total Due</td><td>&#163;{{ "%.2f" | format(totals.total) }}</td></tr>
          </table>
        </div>
      </td>
    </tr>
  </table>

  <div class="payment">
    <h3>Payment Details</h3>
    <table>
      <tr><td>Payee</td><td>{{ bank_payee }}</td></tr>
      <tr><td>Sort Code</td><td>{{ bank_sort_code }}</td></tr>
      <tr><td>Account Number</td><td>{{ bank_account }}</td></tr>
      <tr><td>Reference</td><td>{{ number }}</td></tr>
    </table>
  </div>

  {% if notes %}
  <div class="notes">
    <h3>Notes</h3>
    <p>{{ notes }}</p>
  </div>
  {% endif %}

  <div class="footer">
    Thank you for your business &nbsp;&middot;&nbsp; {{ number }} &nbsp;&middot;&nbsp; {{ business_name }}
  </div>

</div>
</body>
</html>
```

Note: `£` replaced with `&#163;` for reliable xhtml2pdf encoding. `font-weight: 700` / `300` replaced with `bold` / `300` (xhtml2pdf handles named weights more reliably). `'Helvetica Neue'` removed from font stack (not available in xhtml2pdf's default fonts — Helvetica renders instead).

- [ ] **Step 2: Smoke-test PDF generation manually**

```bash
cd /root/invoice-tool
venv/bin/python - <<'EOF'
from invoice import render_html, generate_pdf
from datetime import date
import tempfile, os

data = {
    'number': 'INV-TEST',
    'business_name': 'Test Co',
    'business_address': '1 Test Street',
    'business_email': 'test@test.com',
    'business_phone': '01234567890',
    'bank_payee': 'Test Payee',
    'bank_sort_code': '00-00-00',
    'bank_account': '00000000',
    'client_name': 'Client Ltd',
    'client_email': 'client@example.com',
    'client_address': '',
    'date_issued': date.today(),
    'date_due': date(2026, 4, 30),
    'line_items': [{'description': 'Web development', 'qty': 1, 'unit_price': 1500.0}],
    'totals': {'subtotal': 1500.0, 'vat': 300.0, 'total': 1800.0},
    'vat_applied': True,
    'notes': 'Thank you.',
    'plain_text_body': '',
}
html = render_html(data)
out = '/tmp/test-invoice.pdf'
generate_pdf(html, out)
print(f'PDF generated: {out} ({os.path.getsize(out)} bytes)')
EOF
```

Expected: `PDF generated: /tmp/test-invoice.pdf (NNNN bytes)` — size should be > 5000 bytes.

- [ ] **Step 3: Run full test suite**

```bash
cd /root/invoice-tool
venv/bin/pytest tests/ -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
cd /root/invoice-tool
git add template.html
git commit -m "feat: rewrite template layout for xhtml2pdf (tables replace flexbox)"
```

---

## Task 5: Update .gitignore + add config.example.json

**Files:**
- Modify: `.gitignore`
- Create: `config.example.json`

- [ ] **Step 1: Update .gitignore**

Replace the full contents of `.gitignore` with:

```
# Credentials and personal data — never commit
config.json
invoices.json

# Generated PDFs
invoices/

# Python
venv/
.pytest_cache/
__pycache__/
*.pyc

# PyInstaller build output (NOT *.spec — invoice.spec must be committed for CI)
build/
dist/
```

- [ ] **Step 2: Create config.example.json**

```json
{
  "business_name": "",
  "business_address": "",
  "business_email": "",
  "business_phone": "",
  "bank_payee": "",
  "bank_sort_code": "",
  "bank_account": "",
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "smtp_user": "",
  "smtp_password": "",
  "smtp_from": "Your Name <you@example.com>"
}
```

- [ ] **Step 3: Verify config.json is not tracked**

```bash
cd /root/invoice-tool
git status
```

Expected: `config.json` does not appear in "Changes to be committed" or "Untracked files".

- [ ] **Step 4: Commit**

```bash
cd /root/invoice-tool
git add .gitignore config.example.json
git commit -m "chore: gitignore credentials/PDFs, add config.example.json"
```

---

## Task 6: Create invoice.spec (PyInstaller)

**Files:**
- Create: `invoice.spec`

- [ ] **Step 1: Install PyInstaller in venv**

```bash
cd /root/invoice-tool
venv/bin/pip install pyinstaller
```

- [ ] **Step 2: Generate base spec**

```bash
cd /root/invoice-tool
venv/bin/pyi-makespec --onefile --name invoice invoice.py
```

This creates `invoice.spec`.

- [ ] **Step 3: Edit invoice.spec — add datas line**

Open `invoice.spec`. Find the `Analysis(...)` block. It will have a `datas=[]` line. Change it to:

```python
    datas=[('template.html', '.')],
```

The full `Analysis` call will look something like:
```python
a = Analysis(
    ['invoice.py'],
    pathex=[],
    binaries=[],
    datas=[('template.html', '.')],
    hiddenimports=[],
    hookspath=[],
    ...
)
```

Also confirm the `EXE(...)` block has `console=True` (it should by default since there is no `--windowed` flag).

- [ ] **Step 4: Commit invoice.spec**

```bash
cd /root/invoice-tool
git add invoice.spec
git commit -m "chore: add PyInstaller spec with template.html bundle"
```

---

## Task 7: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/build.yml`

- [ ] **Step 1: Create the workflows directory**

```bash
mkdir -p /root/invoice-tool/.github/workflows
```

- [ ] **Step 2: Create build.yml**

```yaml
name: Build Windows Exe

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt pyinstaller

      - name: Build exe
        run: pyinstaller invoice.spec

      - name: Upload to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/invoice.exe
```

- [ ] **Step 3: Commit**

```bash
cd /root/invoice-tool
git add .github/
git commit -m "ci: GitHub Actions workflow — build Windows exe on tag push"
```

---

## Task 8: Write README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Invoice Generator

A command-line tool that generates professional PDF invoices and emails them directly to clients via SMTP. Runs on Windows with no installation required.

## Download

Download the latest `invoice.exe` from the [Releases page](../../releases/latest).

## Getting Started

1. Double-click `invoice.exe` (or run it from a terminal).
2. On first launch you'll be asked for your settings — fill these in once:
   - Business name, address, email, phone
   - Bank payee name, sort code, account number
   - SMTP host, port, username, password, from address
3. Settings are saved automatically. You won't be asked again.

## Where things are saved

| Item | Location |
|---|---|
| Settings | `%APPDATA%\invoice-tool\config.json` |
| Invoice log | `%APPDATA%\invoice-tool\invoices.json` |
| PDF invoices | `Documents\Invoices\` |

## Re-run first-time setup

Delete `%APPDATA%\invoice-tool\config.json` and re-launch the exe.

To open `%APPDATA%`, press `Win + R`, type `%APPDATA%` and press Enter.

## SMTP settings

The tool sends email via any SMTP server. Common settings:

| Provider | Host | Port |
|---|---|---|
| Hostinger | smtp.hostinger.com | 587 |
| Gmail | smtp.gmail.com | 587 |
| Outlook | smtp-mail.outlook.com | 587 |

For Gmail/Outlook you may need to generate an app-specific password.

## Resending an invoice

Run the tool and choose option `2` to resend any previously sent invoice to the same or a different address.

---

## For developers

### Run from source

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python invoice.py
```

### Run tests

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/pytest tests/ -v
```

### Build exe locally

```bash
venv/bin/pip install pyinstaller
venv/bin/pyinstaller invoice.spec
# Output: dist/invoice.exe
```

### Release a new version

Push a tag to trigger the GitHub Actions build:

```bash
git tag v1.0.1
git push origin v1.0.1
```

The `invoice.exe` will appear on the Releases page within a few minutes.
```

- [ ] **Step 2: Commit**

```bash
cd /root/invoice-tool
git add README.md
git commit -m "docs: add README with download link, first-run guide, dev instructions"
```

---

## Task 9: Create private GitHub repo and push

- [ ] **Step 1: Check GitHub CLI is authenticated**

```bash
gh auth status
```

Expected: `Logged in to github.com as <username>`. If not authenticated, run `gh auth login`.

- [ ] **Step 2: Create private repo**

```bash
gh repo create invoice-tool --private --source=/root/invoice-tool --remote=origin --push
```

This creates a private repo named `invoice-tool` on your GitHub account, sets it as `origin`, and pushes all commits.

Expected output includes: `✓ Created repository <username>/invoice-tool on GitHub`

- [ ] **Step 3: Verify push**

```bash
cd /root/invoice-tool
git log --oneline -8
gh repo view --web 2>/dev/null || echo "Repo URL: https://github.com/<username>/invoice-tool"
```

---

## Task 10: Tag v1.0.0 and trigger first release build

- [ ] **Step 1: Create and push the v1.0.0 tag**

```bash
cd /root/invoice-tool
git tag v1.0.0
git push origin v1.0.0
```

- [ ] **Step 2: Watch the build**

```bash
gh run list --limit 5
```

(Run from inside `/root/invoice-tool` where the remote is already set, or use `--repo <owner>/invoice-tool` with your GitHub username.)

Or open the Actions tab on GitHub. The build takes 3–5 minutes on the Windows runner.

- [ ] **Step 3: Confirm the exe is attached to the release**

```bash
gh release view v1.0.0
```

Expected: Shows `invoice.exe` as a release asset with a download URL.

- [ ] **Step 4: Test the download URL**

```bash
gh release download v1.0.0 --pattern invoice.exe --dir /tmp/
ls -lh /tmp/invoice.exe
```

Expected: File exists, size > 10MB (PyInstaller bundles Python runtime).

---

## Done

The tool is now:
- Packaged as a standalone `invoice.exe` — no prerequisites
- First run prompts for all settings, saves to `%APPDATA%\invoice-tool\`
- PDFs saved to `Documents\Invoices\`
- Built automatically by GitHub Actions on every `v*` tag
- Available for download from the GitHub Releases page
