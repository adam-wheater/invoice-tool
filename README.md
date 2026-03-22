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
