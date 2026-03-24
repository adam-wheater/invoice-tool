# Invoice Generator

This program lets you create professional invoices and email them straight to your clients — all from your Windows computer. No installation needed, just double-click and go.

---

## Step 1 — Download the program

Click here to download: [Download invoice.exe](../../releases/latest)

You'll get a single file called **invoice.exe**. Save it somewhere easy to find, like your Desktop.

---

## Step 2 — Run it for the first time

1. **Double-click `invoice.exe`**
2. It will ask you a series of questions the very first time — just type in your answers and press Enter after each one:
   - Your business name, address, email, and phone number
   - Your bank details (so clients know where to pay you): account holder name, sort code, account number
   - Your email settings (so the program can send emails on your behalf) — see the table below if you're not sure what to enter

> The program saves your answers automatically. You'll never be asked these questions again.

---

## Step 3 — Create and send an invoice

Each time you run the program, just follow the on-screen questions:
- Who is the client?
- What did you do for them?
- How much do you charge?

The program will create a PDF invoice and email it to your client for you. It also keeps a record of every invoice you've sent.

---

## Where does everything get saved?

| What | Where on your computer |
|---|---|
| Your settings | Saved automatically — you don't need to find this |
| Your invoice history | Saved automatically — you don't need to find this |
| PDF copies of your invoices | In your **Documents** folder, inside a folder called **Invoices** |

---

## Email settings — what to enter

When you first run the program, it asks for email settings. These tell the program how to send email on your behalf. Use the row that matches where your email comes from:

| My email is with... | Host | Port |
|---|---|---|
| Hostinger | smtp.hostinger.com | 587 |
| Gmail | smtp.gmail.com | 587 |
| Outlook / Hotmail | smtp-mail.outlook.com | 587 |

**Username** = your full email address
**Password** = your email password (or an app password — see note below)

> **Gmail or Outlook users:** Google and Microsoft sometimes block programs from logging in with your normal password. If sending fails, search online for "Gmail app password" or "Outlook app password" and use that instead.

---

## Resending an old invoice

Run the program again and choose option **2**. You'll see a list of invoices you've already sent — pick one and it will be resent.

---

## Starting over (re-entering your settings)

If you made a mistake in your settings and want to start fresh:

1. Press the **Windows key + R** on your keyboard (a small box appears)
2. Type `%APPDATA%\invoice-tool` and press Enter
3. Delete the file called `config.json`
4. Run the program again — it will ask you all the setup questions from the beginning

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
