#!/usr/bin/env python3
"""
Invoice Generator
=================
Generates professional PDF invoices and emails them via SMTP.

USAGE:
  python invoice.py
"""

import json
import os
import smtplib
import sys
from datetime import date, datetime, timezone
from typing import Optional
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path

import jinja2
from xhtml2pdf import pisa

from helpers import (
    calculate_totals,
    compute_due_date,
    format_date_display,
    format_plain_text_body,
    next_invoice_number,
    pdf_output_path,
    sanitise_filename,
    validate_email,
)

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

CONFIG_DEFAULTS = {
    'smtp_port': 587,
}

# Fields that must be non-blank (port handled separately as numeric)
REQUIRED_STRING_FIELDS = [
    'business_name', 'business_address', 'business_email', 'business_phone',
    'bank_payee', 'bank_sort_code', 'bank_account',
    'smtp_host', 'smtp_user', 'smtp_password', 'smtp_from',
]

# Grouped sections shown during first-run setup wizard
SETUP_SECTIONS = [
    ('Business details', [
        'business_name', 'business_address', 'business_email', 'business_phone',
    ]),
    ('Bank details  (printed on every invoice)', [
        'bank_payee', 'bank_sort_code', 'bank_account',
    ]),
    ('Email / SMTP settings  (used to send invoices)', [
        'smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from',
    ]),
]

FIELD_PROMPTS = {
    'business_name':    'Business name',
    'business_address': 'Business address',
    'business_email':   'Business email',
    'business_phone':   'Business phone',
    'bank_payee':       'Name on bank account',
    'bank_sort_code':   'Sort code  (e.g. 12-34-56)',
    'bank_account':     'Account number',
    'smtp_host':        'Email server address  (e.g. smtp.gmail.com / smtp.hostinger.com)',
    'smtp_port':        'Email server port  (587 for TLS, 465 for SSL)',
    'smtp_user':        'Email login  (usually your email address)',
    'smtp_password':    'Email password',
    'smtp_from':        'Display name + address  (e.g. Jane Smith <jane@example.com>)',
}


# ── Config ─────────────────────────────────────────────────────────────────────

def _load_config_file() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_config(config: dict) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def ensure_config() -> dict:
    """Load config; inject env vars, then prompt for any remaining blank fields."""
    first_run = not CONFIG_FILE.exists()
    config = {**CONFIG_DEFAULTS, **_load_config_file()}

    # Override with env vars if set (credentials never need to touch disk)
    if os.environ.get('INVOICE_SMTP_USER'):
        config['smtp_user'] = os.environ['INVOICE_SMTP_USER']
        if not config.get('smtp_from'):
            config['smtp_from'] = os.environ['INVOICE_SMTP_USER']
    if os.environ.get('INVOICE_SMTP_PASSWORD'):
        config['smtp_password'] = os.environ['INVOICE_SMTP_PASSWORD']

    all_fields = [f for _, fields in SETUP_SECTIONS for f in fields]
    missing = [f for f in all_fields if not str(config.get(f, '')).strip()]

    if not first_run and not missing:
        return config

    if first_run:
        print('\n  Welcome! Let\'s set up your invoice tool.')
        print('  You only need to do this once — answers are saved locally.')
        fields_to_prompt = all_fields
    else:
        fields_to_prompt = missing

    changed = False
    for section_title, fields in SETUP_SECTIONS:
        section_fields = [f for f in fields if f in fields_to_prompt]
        if not section_fields:
            continue
        print(f'\n  {section_title}')
        print('  ' + '-' * len(section_title))
        for field in section_fields:
            label = FIELD_PROMPTS.get(field, field)
            current = str(config.get(field, ''))
            fallback = str(CONFIG_DEFAULTS.get(field, ''))
            hint = f'  [{current or fallback}]' if (current or fallback) else ''
            value = input(f'  {label}{hint}: ').strip() or current or fallback
            config[field] = value
            changed = True

    if changed:
        _save_config(config)
    return config


# ── Invoice log ────────────────────────────────────────────────────────────────

def _load_invoices() -> list:
    if not INVOICES_FILE.exists():
        return []
    try:
        data = json.loads(INVOICES_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_invoices(records: list) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    INVOICES_FILE.write_text(json.dumps(records, indent=2, default=str))


def reserve_invoice_number() -> tuple:
    """Reserve next invoice number; write pending record immediately. Returns (number, records)."""
    records = _load_invoices()
    number = next_invoice_number(records)
    record = {
        'number': number,
        'status': 'pending',
        'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    records.append(record)
    _save_invoices(records)
    return number, records


def cancel_invoice(records: list, number: str) -> None:
    """Delete the pending record for a cancelled invoice."""
    _save_invoices([r for r in records if r.get('number') != number])


def finalise_invoice(records: list, number: str, data: dict) -> None:
    """Update the pending record with full invoice data and mark as sent."""
    for record in records:
        if record.get('number') == number:
            record.update(data)
            record['status'] = 'sent'
            record['sent_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            break
    _save_invoices(records)


def mark_invoice_paid(records: list, number: str) -> None:
    """Mark a sent invoice record as paid."""
    for record in records:
        if record.get('number') == number:
            record['status'] = 'paid'
            record['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            break
    _save_invoices(records)


def _select_invoice_from_list(sent_records: list, raw: str) -> Optional[dict]:
    """Return the matching record given a 1-based list index or invoice number string.

    Args:
        sent_records: List of sent invoice records.
        raw: User input — either a 1-based integer index or an invoice number (case-insensitive).

    Returns:
        The matching record dict, or None if not found.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(sent_records):
            return sent_records[idx]
        return None
    except ValueError:
        pass
    upper = raw.upper()
    for record in sent_records:
        if record.get('number', '').upper() == upper:
            return record
    return None


def build_invoice_data_from_record(record: dict, config: dict) -> dict:
    """Reconstruct a full invoice_data dict from a log record and live config.

    Args:
        record: A sent-invoice record from invoices.json.
        config: The live config dict (provides business/bank fields).

    Returns:
        A complete invoice_data dict suitable for render_html() and send_invoice_email().
    """
    line_items = record['line_items']
    vat_applied = record['vat_applied']
    invoice_data = {
        'number': record['number'],
        'client_name': record['client_name'],
        'client_email': record['client_email'],
        'client_address': record.get('client_address', ''),
        'date_issued': date.fromisoformat(record['date_issued']),
        'date_due': date.fromisoformat(record['date_due']),
        'line_items': line_items,
        'vat_applied': vat_applied,
        'totals': calculate_totals(line_items, vat_applied),
        'notes': record.get('notes', ''),
        'business_name': config['business_name'],
        'business_address': config.get('business_address', ''),
        'business_email': config.get('business_email', ''),
        'business_phone': config.get('business_phone', ''),
        'bank_payee': config['bank_payee'],
        'bank_sort_code': config['bank_sort_code'],
        'bank_account': config['bank_account'],
    }
    invoice_data['plain_text_body'] = format_plain_text_body(invoice_data)
    return invoice_data


# ── Prompts ────────────────────────────────────────────────────────────────────

def prompt_client_details() -> dict:
    print('\n── Client Details ──────────────────────────────────────')
    name = ''
    while not name:
        name = input('  Client name: ').strip()
        if not name:
            print('  Client name is required.')

    email = ''
    while not email:
        raw = input('  Client email: ').strip()
        if validate_email(raw):
            email = raw
        else:
            print('  Invalid email address. Please try again.')

    print('  Client address (optional — press Enter on a blank line to finish):')
    address_lines = []
    while True:
        line = input('    ')
        if not line:
            break
        address_lines.append(line)

    return {
        'client_name': name,
        'client_email': email,
        'client_address': '\n'.join(address_lines),
    }


def prompt_line_items() -> list:
    print('\n── Line Items ──────────────────────────────────────────')
    print('  Enter items one at a time. Leave description blank to finish.')
    items = []
    while True:
        desc = input(f'  Description [{len(items) + 1}] (blank to finish): ').strip()
        if not desc:
            if not items:
                print('  At least one line item is required.')
                continue
            break

        qty = None
        while qty is None:
            raw = input('    Quantity [1]: ').strip() or '1'
            try:
                q = float(raw)
                if q <= 0:
                    print('    Quantity must be greater than 0.')
                else:
                    qty = q
            except ValueError:
                print('    Please enter a valid number.')

        price = None
        while price is None:
            raw = input('    Unit price (£): ').strip()
            try:
                p = float(raw)
                if p < 0:
                    print('    Price cannot be negative.')
                else:
                    price = p
            except ValueError:
                print('    Please enter a valid amount.')

        items.append({'description': desc, 'qty': qty, 'unit_price': price})
        print(f'    → Subtotal: £{qty * price:,.2f}')

    return items


def prompt_invoice_options() -> dict:
    print('\n── Invoice Options ─────────────────────────────────────')

    vat_raw = input('  Apply VAT at 20%? [y/N]: ').strip().lower()
    apply_vat = vat_raw == 'y'

    days = None
    while days is None:
        raw = input('  Payment due in how many days? [30]: ').strip() or '30'
        try:
            d = int(raw)
            if d < 1:
                print('  Due date must be at least 1 day from today.')
            else:
                days = d
        except ValueError:
            print('  Please enter a whole number.')

    due_date = compute_due_date(days)
    print(f'  Due by: {format_date_display(due_date)}')

    notes_raw = input('  Notes (optional, max 500 chars): ').strip()
    if len(notes_raw) > 500:
        notes_raw = notes_raw[:500]
        print('  Notes truncated to 500 characters.')

    return {'apply_vat': apply_vat, 'due_date': due_date, 'notes': notes_raw}


def print_summary(number: str, client: dict, items: list, options: dict, totals: dict) -> None:
    issued = date.today()
    print('\n' + '═' * 56)
    print(f'  INVOICE {number}')
    print('═' * 56)
    print(f'  To:      {client["client_name"]} <{client["client_email"]}>')
    if client['client_address']:
        for line in client['client_address'].splitlines():
            print(f'           {line}')
    print(f'  Issued:  {format_date_display(issued)}')
    print(f'  Due:     {format_date_display(options["due_date"])}')
    print()
    for item in items:
        qty_str = str(int(item['qty'])) if item['qty'] == int(item['qty']) else str(item['qty'])
        print(f'  {item["description"][:36]:36s}  x{qty_str:>4}  £{item["unit_price"]:>9,.2f}')
    print('  ' + '─' * 54)
    print(f'  {"Subtotal":49s} £{totals["subtotal"]:>9,.2f}')
    if options['apply_vat']:
        print(f'  {"VAT (20%)":49s} £{totals["vat"]:>9,.2f}')
    print(f'  {"TOTAL DUE":49s} £{totals["total"]:>9,.2f}')
    if options['notes']:
        print(f'\n  Notes: {options["notes"]}')
    print('═' * 56)


def prompt_confirmation() -> bool:
    while True:
        raw = input('\n  Send this invoice? [y/N]: ').strip().lower()
        if raw == 'y':
            return True
        if raw in ('n', ''):
            return False
        print('  Please type y or n.')


def prompt_mode() -> str:
    """Prompt the user to choose a mode. Returns 'new', 'history', 'send_folder', 'edit_settings', 'smtp_test', or 'exit'."""
    print('  1) New invoice')
    print('  2) History')
    print('  3) Send unsent invoice from folder')
    print('  4) Edit settings')
    print('  5) Test SMTP connection')
    print('  0) Exit\n')
    while True:
        raw = input('  Choice [1]: ').strip()
        if raw in ('', '1'):
            return 'new'
        if raw == '2':
            return 'history'
        if raw == '3':
            return 'send_folder'
        if raw == '4':
            return 'edit_settings'
        if raw == '5':
            return 'smtp_test'
        if raw == '0':
            return 'exit'
        print('  Please enter 0, 1, 2, 3, 4, or 5.')


def prompt_history_mode() -> str:
    """Prompt the user to choose a history action. Returns 'view', 'resend', 'mark_paid', or 'back'."""
    print('  1) View invoices')
    print('  2) Resend invoice')
    print('  3) Mark invoice as paid')
    print('  0) Back\n')
    while True:
        raw = input('  Choice: ').strip()
        if raw == '1':
            return 'view'
        if raw == '2':
            return 'resend'
        if raw == '3':
            return 'mark_paid'
        if raw == '0':
            return 'back'
        print('  Please enter 0, 1, 2, or 3.')


def resend_flow(config: dict) -> None:
    """Handle the resend-existing-invoice flow."""
    all_records = _load_invoices()
    sent = [r for r in all_records if r.get('status') == 'sent']

    if not sent:
        print('  No sent invoices found.')
        return

    # Show list
    print('\n  Sent invoices:')
    print(f'   {"#":<4} {"Number":<10} {"Client":<22} {"Total":>10}  {"Date":<12}')
    print('  ' + '─' * 57)
    for i, r in enumerate(sent, 1):
        total_str = f'\u00a3{r["total_gbp"]:,.2f}'
        print(f'   {i:<4} {r["number"]:<10} {r["client_name"][:21]:<22} {total_str:>10}  {r["date_issued"]:<12}')

    # Select invoice
    record = None
    while record is None:
        sel = input('\n  Enter # or invoice number (e.g. INV-001): ').strip()
        record = _select_invoice_from_list(sent, sel)
        if record is None:
            print('  Not found. Enter a list number or invoice number.')

    # Confirm/change recipient
    original_email = record['client_email']
    recipient = original_email
    raw_email = input(f'  Send to [{original_email}]: ').strip()
    while raw_email and not validate_email(raw_email):
        print('  Invalid email address.')
        raw_email = input(f'  Send to [{original_email}]: ').strip()
    if raw_email:
        recipient = raw_email

    # Check PDF exists
    pdf_path = Path(record['pdf_path'])
    if not pdf_path.exists():
        print(f'\n  ERROR: PDF not found at {record["pdf_path"]}')
        print('  The file may have been moved or deleted.')
        sys.exit(1)

    # Confirm before sending
    total_str = f'\u00a3{record["total_gbp"]:,.2f}'
    while True:
        confirm = input(f'\n  Resend {record["number"]} ({total_str}) to {recipient}? [y/N]: ').strip().lower()
        if confirm == 'y':
            break
        if confirm in ('n', ''):
            print('  Cancelled.')
            return

    # Build, render, send
    invoice_data = build_invoice_data_from_record(record, config)
    html = render_html(invoice_data)

    print('  Sending email...')
    try:
        send_invoice_email(config, invoice_data, html, str(pdf_path), recipient=recipient)
    except Exception as e:
        print(f'\n  ERROR sending email:')
        print(_smtp_error_hint(config['smtp_host'], e))
        print(f'\n  PDF is at: {pdf_path}')
        print('  Use option 3 to test your SMTP settings.')
        return

    print(f'\n  {record["number"]} resent to {recipient}')


def view_history_flow(config: dict) -> None:
    """Display all sent and paid invoices."""
    records = _load_invoices()
    visible = [r for r in records if r.get('status') in ('sent', 'paid')]

    if not visible:
        print('  No invoices found.')
        return

    print('\n  Invoices:')
    print(f'   {"#":<4} {"Number":<10} {"Client":<22} {"Total":>10}  {"Date":<12}  {"Status"}')
    print('  ' + '─' * 68)
    for i, r in enumerate(visible, 1):
        total_str = f'\u00a3{r["total_gbp"]:,.2f}'
        status = r.get('status', 'sent')
        print(f'   {i:<4} {r["number"]:<10} {r["client_name"][:21]:<22} {total_str:>10}  {r["date_issued"]:<12}  {status}')


def mark_paid_flow(config: dict) -> None:
    """Mark a sent invoice as paid."""
    all_records = _load_invoices()
    unpaid = [r for r in all_records if r.get('status') == 'sent']

    if not unpaid:
        print('  No unpaid invoices found.')
        return

    print('\n  Unpaid invoices:')
    print(f'   {"#":<4} {"Number":<10} {"Client":<22} {"Total":>10}  {"Date":<12}')
    print('  ' + '─' * 57)
    for i, r in enumerate(unpaid, 1):
        total_str = f'\u00a3{r["total_gbp"]:,.2f}'
        print(f'   {i:<4} {r["number"]:<10} {r["client_name"][:21]:<22} {total_str:>10}  {r["date_issued"]:<12}')

    record = None
    while record is None:
        sel = input('\n  Enter # or invoice number: ').strip()
        record = _select_invoice_from_list(unpaid, sel)
        if record is None:
            print('  Not found. Enter a list number or invoice number.')

    total_str = f'\u00a3{record["total_gbp"]:,.2f}'
    while True:
        confirm = input(f'\n  Mark {record["number"]} ({total_str}) as paid? [y/N]: ').strip().lower()
        if confirm == 'y':
            break
        if confirm in ('n', ''):
            print('  Cancelled.')
            return

    mark_invoice_paid(all_records, record['number'])
    print(f'\n  {record["number"]} marked as paid.')


def send_from_folder_flow(config: dict) -> None:
    """Send a PDF invoice from the invoices folder that was never emailed."""
    # Find PDFs in INVOICES_DIR
    if not INVOICES_DIR.exists():
        print(f'  Invoices folder not found: {INVOICES_DIR}')
        return

    pdfs = sorted(INVOICES_DIR.glob('*.pdf'))
    if not pdfs:
        print(f'  No PDF files found in {INVOICES_DIR}')
        return

    # Cross-reference with sent records so user can see what's already been sent
    sent_paths = {r.get('pdf_path', '') for r in _load_invoices() if r.get('status') == 'sent'}

    print(f'\n  PDFs in {INVOICES_DIR}:')
    print(f'   {"#":<4} {"Filename":<40}  {"Status":<10}')
    print('  ' + '─' * 58)
    for i, p in enumerate(pdfs, 1):
        status = 'sent' if str(p.resolve()) in sent_paths else 'not sent'
        print(f'   {i:<4} {p.name[:39]:<40}  {status:<10}')

    # Select PDF
    pdf_path = None
    while pdf_path is None:
        sel = input('\n  Enter # or filename: ').strip()
        if not sel:
            continue
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(pdfs):
                pdf_path = pdfs[idx]
        except ValueError:
            matches = [p for p in pdfs if sel.lower() in p.name.lower()]
            if len(matches) == 1:
                pdf_path = matches[0]
            elif len(matches) > 1:
                print('  Multiple matches — be more specific.')
        if pdf_path is None:
            print('  Not found.')

    # Try to look up record for pre-filled recipient
    resolved = str(pdf_path.resolve())
    all_records = _load_invoices()
    record = next((r for r in all_records if r.get('pdf_path', '') == resolved), None)
    default_email = record['client_email'] if record else ''

    hint = f' [{default_email}]' if default_email else ''
    email = ''
    while not email:
        raw = input(f'  Recipient email{hint}: ').strip() or default_email
        if validate_email(raw):
            email = raw
        else:
            print('  Invalid email address.')

    # Confirm
    while True:
        confirm = input(f'\n  Send {pdf_path.name} to {email}? [y/N]: ').strip().lower()
        if confirm == 'y':
            break
        if confirm in ('n', ''):
            print('  Cancelled.')
            return

    # Build a minimal message and send
    if record:
        invoice_data = build_invoice_data_from_record(record, config)
        html = render_html(invoice_data)
    else:
        # No log record — send bare PDF with plain subject
        invoice_data = {
            'number': pdf_path.stem,
            'client_email': email,
            'plain_text_body': f'Please find attached invoice {pdf_path.stem}.',
        }
        html = f'<p>Please find attached invoice {pdf_path.stem}.</p>'

    print('  Sending email...')
    try:
        send_invoice_email(config, invoice_data, html, str(pdf_path), recipient=email)
    except Exception as e:
        print(f'\n  ERROR sending email:')
        print(_smtp_error_hint(config['smtp_host'], e))
        print('  Use option 3 to test your SMTP settings.')
        return

    print(f'\n  {pdf_path.name} sent to {email}')


def smtp_test_flow(config: dict) -> None:
    """Step-by-step SMTP diagnostic — connect, TLS, login, send."""
    host = config['smtp_host']
    port = int(config['smtp_port'])

    print(f'\n  SMTP settings in use:')
    print(f'    Host:     {host}:{port}')
    print(f'    Login:    {config["smtp_user"]}')
    print(f'    From:     {config["smtp_from"]}')

    _, from_addr = parseaddr(config['smtp_from'])
    to_addr = from_addr or config['smtp_user']
    override = input(f'\n  Send test email to [{to_addr}]: ').strip()
    if override:
        if not validate_email(override):
            print('  Invalid email address.')
            return
        to_addr = override

    print()

    # Step 1: Connect
    print(f'  [1/4] Connecting to {host}:{port} ...', end='', flush=True)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT)
        else:
            server = smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT)
        print('  OK')
    except Exception as exc:
        print('  FAILED')
        print(_smtp_error_hint(host, exc))
        return

    # Step 2: STARTTLS
    if port == 465:
        print('  [2/4] SSL already active — no STARTTLS needed.  OK')
    else:
        print('  [2/4] Starting TLS ...', end='', flush=True)
        try:
            server.starttls()
            print('  OK')
        except Exception as exc:
            print('  FAILED')
            print(f'  {exc}')
            server.close()
            return

    # Step 3: Login
    print(f'  [3/4] Logging in as {config["smtp_user"]} ...', end='', flush=True)
    try:
        server.login(config['smtp_user'], config['smtp_password'])
        print('  OK')
    except Exception as exc:
        print('  FAILED')
        print(_smtp_error_hint(host, exc))
        server.close()
        return

    # Step 4: Send
    print(f'  [4/4] Sending test email to {to_addr} ...', end='', flush=True)
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Invoice Tool — SMTP test'
        msg['From'] = config['smtp_from']
        msg['To'] = to_addr
        msg.attach(MIMEText(
            'This is a test email from your Invoice Tool. SMTP is working correctly.',
            'plain', 'utf-8',
        ))
        msg.attach(MIMEText(
            '<p>This is a test email from your <strong>Invoice Tool</strong>. '
            'SMTP is working correctly.</p>',
            'html', 'utf-8',
        ))
        _, envelope_from = parseaddr(config['smtp_from'])
        server.sendmail(envelope_from, [to_addr], msg.as_string())
        server.quit()
        print('  OK')
    except Exception as exc:
        print('  FAILED')
        print(_smtp_error_hint(host, exc))
        server.close()
        return

    print(f'\n  All steps passed — SMTP is working correctly.')
    print(f'  Check {to_addr} for the test email.')


def edit_settings_flow(config: dict) -> dict:
    """Let the user edit any saved setting."""
    smtp_user_from_env = bool(os.environ.get('INVOICE_SMTP_USER'))
    smtp_pass_from_env = bool(os.environ.get('INVOICE_SMTP_PASSWORD'))

    print('\n  Edit settings — press Enter to keep the current value.')

    for section_title, fields in SETUP_SECTIONS:
        print(f'\n  {section_title}')
        print('  ' + '-' * len(section_title))
        for field in fields:
            label = FIELD_PROMPTS.get(field, field)
            current = str(config.get(field, ''))
            if field == 'smtp_password':
                display = '****' if current else ''
            else:
                display = current

            env_note = ''
            if field == 'smtp_user' and smtp_user_from_env:
                env_note = ' (overridden by environment variable — editing will save to config.json but the env var will still take precedence on next launch)'
            elif field == 'smtp_password' and smtp_pass_from_env:
                env_note = ' (overridden by environment variable — editing will save to config.json but the env var will still take precedence on next launch)'

            hint = f'  [{display}]' if display else ''
            prompt = f'  {label}{hint}{env_note}: '
            print(prompt, end='', flush=True)
            raw = input().strip()
            if raw:
                config[field] = raw

    _save_config(config)
    print('\n  Settings saved.')
    return config


# ── PDF generation ─────────────────────────────────────────────────────────────

def render_html(template_data: dict) -> str:
    """Render the invoice HTML template with the given data."""
    template_src = TEMPLATE_FILE.read_text()
    env = jinja2.Environment(autoescape=True)
    template = env.from_string(template_src)
    return template.render(**template_data)


def generate_pdf(html: str, output_path: str) -> None:
    """Convert HTML string to PDF and save to output_path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        result = pisa.CreatePDF(html, dest=f)
    if result.err:
        raise RuntimeError(f'PDF generation failed (xhtml2pdf error code {result.err})')


# ── Email ──────────────────────────────────────────────────────────────────────

_SMTP_TIMEOUT = 15  # seconds


def _smtp_error_hint(host: str, exc: Exception) -> str:
    """Return a human-readable diagnostic for an SMTP error."""
    host_lower = host.lower()
    is_gmail = 'gmail' in host_lower
    is_outlook = any(x in host_lower for x in ('outlook', 'office365', 'hotmail', 'live'))

    lines = []

    if isinstance(exc, smtplib.SMTPAuthenticationError):
        raw = exc.smtp_error
        resp = raw.decode(errors='replace') if isinstance(raw, bytes) else str(raw)
        lines.append(f'  Server said: {exc.smtp_code} {resp.strip()}')
        lines.append('')
        if is_gmail:
            lines.append('  Gmail requires an App Password — your normal Google password')
            lines.append('  will not work if 2-Step Verification is on.')
            lines.append('  To fix: myaccount.google.com → Security → App passwords')
            lines.append('  Generate a password for "Mail" and paste it into smtp_password.')
        elif is_outlook:
            lines.append('  Outlook / Office 365: make sure "Authenticated SMTP" is')
            lines.append('  enabled for your account in the Microsoft 365 admin centre.')
            lines.append('  Admin centre → Users → Active users → [your account]')
            lines.append('  → Mail tab → Manage email apps → Authenticated SMTP.')
        else:
            lines.append('  Check smtp_user and smtp_password are correct.')
            lines.append('  Some providers require SMTP access to be enabled in account settings,')
            lines.append('  or use a separate app password rather than your login password.')

    elif isinstance(exc, (smtplib.SMTPConnectError, ConnectionRefusedError)):
        lines.append(f'  Could not connect to {host} — check smtp_host and smtp_port.')
        lines.append('  Common ports: 587 (STARTTLS)  465 (SSL/TLS)')

    elif isinstance(exc, TimeoutError):
        lines.append(f'  Connection timed out — {host} is not reachable on that port.')
        lines.append('  Check smtp_host is correct and that no firewall is blocking it.')

    elif isinstance(exc, smtplib.SMTPException):
        lines.append(f'  SMTP error: {exc}')

    else:
        lines.append(f'  {exc}')

    return '\n'.join(lines)


def _smtp_connect(config: dict):
    """Open and return an authenticated SMTP connection."""
    port = int(config['smtp_port'])
    if port == 465:
        server = smtplib.SMTP_SSL(config['smtp_host'], port, timeout=_SMTP_TIMEOUT)
    else:
        server = smtplib.SMTP(config['smtp_host'], port, timeout=_SMTP_TIMEOUT)
        server.starttls()
    server.login(config['smtp_user'], config['smtp_password'])
    return server


def send_invoice_email(config: dict, invoice_data: dict, html_body: str, pdf_path: str, recipient: Optional[str] = None) -> None:
    """Send invoice email with HTML body and PDF attachment via SMTP SSL.

    Args:
        recipient: Override delivery address. If None, uses invoice_data['client_email'].
                   The 'Billed to:' line in the email body always uses the original address.
    """
    to_addr = recipient if recipient is not None else invoice_data['client_email']
    msg = MIMEMultipart('mixed')
    msg['Subject'] = f"Invoice {invoice_data['number']} from {config['business_name']}"
    msg['From'] = config['smtp_from']
    msg['To'] = to_addr

    # Plain text + HTML alternative
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(invoice_data['plain_text_body'], 'plain', 'utf-8'))
    alt.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(alt)

    # PDF attachment
    with open(pdf_path, 'rb') as f:
        part = MIMEBase('application', 'pdf')
        part.set_payload(f.read())
    encoders.encode_base64(part)
    filename = Path(pdf_path).name
    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
    msg.attach(part)

    with _smtp_connect(config) as server:
        _, envelope_from = parseaddr(config['smtp_from'])
        server.sendmail(envelope_from, [to_addr], msg.as_string())


# ── Main ───────────────────────────────────────────────────────────────────────

def new_invoice_flow(config: dict) -> None:
    """Handle the create-and-send new invoice flow."""
    # 1. Reserve invoice number (written to log immediately)
    number, records = reserve_invoice_number()
    print(f'\nInvoice number: {number}')

    # 2. Collect details
    client = prompt_client_details()
    items = prompt_line_items()
    options = prompt_invoice_options()
    totals = calculate_totals(items, options['apply_vat'])

    # 3. Show summary and confirm
    print_summary(number, client, items, options, totals)
    if not prompt_confirmation():
        cancel_invoice(records, number)
        print('\nCancelled — no invoice sent.')
        return

    # 4. Assemble invoice data
    issued = date.today()
    invoice_data = {
        'number': number,
        'business_name': config['business_name'],
        'business_address': config.get('business_address', ''),
        'business_email': config.get('business_email', ''),
        'business_phone': config.get('business_phone', ''),
        'bank_payee': config['bank_payee'],
        'bank_sort_code': config['bank_sort_code'],
        'bank_account': config['bank_account'],
        'client_name': client['client_name'],
        'client_email': client['client_email'],
        'client_address': client['client_address'],
        'date_issued': issued,
        'date_due': options['due_date'],
        'line_items': items,
        'totals': totals,
        'vat_applied': options['apply_vat'],
        'notes': options['notes'],
    }
    invoice_data['plain_text_body'] = format_plain_text_body(invoice_data)

    # 5. Generate PDF
    print('\nGenerating PDF...')
    html = render_html(invoice_data)
    out_path = pdf_output_path(INVOICES_DIR, number, client['client_name'], issued)
    generate_pdf(html, out_path)
    print(f'  Saved: {out_path}')

    # 6. Send email
    print('Sending email...')
    try:
        send_invoice_email(config, invoice_data, html, out_path)
    except Exception as e:
        print(f'\n  ERROR sending email:')
        print(_smtp_error_hint(config['smtp_host'], e))
        print(f'\n  PDF saved at: {out_path}')
        print('  Invoice log record left as pending — use option 2 to send it manually.')
        print('  Use option 3 to test your SMTP settings.')
        return

    # 7. Finalise log
    log_data = {
        'client_name': client['client_name'],
        'client_email': client['client_email'],
        'client_address': client['client_address'],
        'date_issued': issued.isoformat(),
        'date_due': options['due_date'].isoformat(),
        'total_gbp': totals['total'],
        'vat_applied': options['apply_vat'],
        'line_items': items,
        'notes': options['notes'],
        'pdf_path': str(Path(out_path).resolve()),
    }
    finalise_invoice(records, number, log_data)

    print(f'\n  Invoice {number} sent to {client["client_email"]}')
    print(f'  PDF: {out_path}')


def main():
    print('\n╔══════════════════════════════════════════════════════╗')
    print('║               Invoice Generator                     ║')
    print('╚══════════════════════════════════════════════════════╝')

    config = ensure_config()

    while True:
        print()
        mode = prompt_mode()
        if mode == 'exit':
            print('  Goodbye.\n')
            break
        elif mode == 'new':
            new_invoice_flow(config)
        elif mode == 'send_folder':
            send_from_folder_flow(config)
        elif mode == 'smtp_test':
            smtp_test_flow(config)


if __name__ == '__main__':
    main()
