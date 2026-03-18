#!/usr/bin/env python3
"""
Invoice Generator
=================
Generates professional PDF invoices and emails them via SMTP.

SETUP (one-time):
  sudo apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
  pip install -r requirements.txt

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
import weasyprint

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

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'config.json'
INVOICES_FILE = BASE_DIR / 'invoices.json'
INVOICES_DIR = BASE_DIR / 'invoices'
TEMPLATE_FILE = BASE_DIR / 'template.html'

CONFIG_DEFAULTS = {
    'bank_payee': 'Adam Wheater',
    'bank_sort_code': '23-01-20',
    'bank_account': '66530274',
    'smtp_host': 'smtp.hostinger.com',
    'smtp_port': 587,
}

REQUIRED_STRING_FIELDS = [
    'business_name', 'business_address', 'business_email', 'business_phone',
    'bank_payee', 'bank_sort_code', 'bank_account',
    'smtp_host', 'smtp_user', 'smtp_password', 'smtp_from',
]

FIELD_PROMPTS = {
    'business_name': 'Business name',
    'business_address': 'Business address',
    'business_email': 'Business email',
    'business_phone': 'Business phone',
    'bank_payee': 'Bank payee name',
    'bank_sort_code': 'Bank sort code',
    'bank_account': 'Bank account number',
    'smtp_host': 'SMTP host',
    'smtp_user': 'SMTP username (email address)',
    'smtp_password': 'SMTP password',
    'smtp_from': 'From address, e.g. Your Name <you@domain.com>',
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
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def ensure_config() -> dict:
    """Load config; inject env vars, then prompt for any remaining blank fields."""
    config = {**CONFIG_DEFAULTS, **_load_config_file()}
    # Override with env vars if set (credentials never need to touch disk)
    if os.environ.get('INVOICE_SMTP_USER'):
        config['smtp_user'] = os.environ['INVOICE_SMTP_USER']
        if not config.get('smtp_from'):
            config['smtp_from'] = os.environ['INVOICE_SMTP_USER']
    if os.environ.get('INVOICE_SMTP_PASSWORD'):
        config['smtp_password'] = os.environ['INVOICE_SMTP_PASSWORD']
    changed = False
    for field in REQUIRED_STRING_FIELDS:
        if not str(config.get(field, '')).strip():
            label = FIELD_PROMPTS.get(field, field)
            default = str(CONFIG_DEFAULTS.get(field, ''))
            hint = f' [{default}]' if default else ''
            value = input(f'  {label}{hint}: ').strip() or default
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
        client_address is always '' (not stored in log).
    """
    line_items = record['line_items']
    vat_applied = record['vat_applied']
    invoice_data = {
        'number': record['number'],
        'client_name': record['client_name'],
        'client_email': record['client_email'],
        'client_address': '',
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


# ── PDF generation ─────────────────────────────────────────────────────────────

def render_html(template_data: dict) -> str:
    """Render the invoice HTML template with the given data."""
    template_src = TEMPLATE_FILE.read_text()
    env = jinja2.Environment(autoescape=True)
    template = env.from_string(template_src)
    return template.render(**template_data)


def generate_pdf(html: str, output_path: str) -> None:
    """Convert HTML string to PDF and save to output_path."""
    INVOICES_DIR.mkdir(exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(output_path)


# ── Email ──────────────────────────────────────────────────────────────────────

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

    port = int(config['smtp_port'])
    if port == 465:
        conn = smtplib.SMTP_SSL(config['smtp_host'], port)
    else:
        conn = smtplib.SMTP(config['smtp_host'], port)
        conn.starttls()
    with conn as server:
        server.login(config['smtp_user'], config['smtp_password'])
        _, envelope_from = parseaddr(config['smtp_from'])
        server.sendmail(envelope_from, [to_addr], msg.as_string())


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print('\n╔══════════════════════════════════════════════════════╗')
    print('║               Invoice Generator                     ║')
    print('╚══════════════════════════════════════════════════════╝\n')

    # 1. Config
    config = ensure_config()

    # 2. Reserve invoice number (written to log immediately)
    number, records = reserve_invoice_number()
    print(f'\nInvoice number: {number}')

    # 3. Collect details
    client = prompt_client_details()
    items = prompt_line_items()
    options = prompt_invoice_options()
    totals = calculate_totals(items, options['apply_vat'])

    # 4. Show summary and confirm
    print_summary(number, client, items, options, totals)
    if not prompt_confirmation():
        cancel_invoice(records, number)
        print('\nCancelled — no invoice sent.')
        sys.exit(0)

    # 5. Assemble invoice data
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

    # 6. Generate PDF
    print('\nGenerating PDF...')
    html = render_html(invoice_data)
    out_path = pdf_output_path(INVOICES_DIR, number, client['client_name'], issued)
    generate_pdf(html, out_path)
    print(f'  Saved: {out_path}')

    # 7. Send email
    print('Sending email...')
    try:
        send_invoice_email(config, invoice_data, html, out_path)
    except Exception as e:
        print(f'\n  ERROR sending email: {e}')
        print(f'  PDF saved at: {out_path}')
        print('  Invoice log record left as pending — re-run or send manually.')
        sys.exit(1)

    # 8. Finalise log
    log_data = {
        'client_name': client['client_name'],
        'client_email': client['client_email'],
        'date_issued': issued.isoformat(),
        'date_due': options['due_date'].isoformat(),
        'total_gbp': totals['total'],
        'vat_applied': options['apply_vat'],
        'line_items': items,
        'notes': options['notes'],
        'pdf_path': str(Path(out_path).relative_to(BASE_DIR)),
    }
    finalise_invoice(records, number, log_data)

    print(f'\n  Invoice {number} sent to {client["client_email"]}')
    print(f'  PDF: {out_path}\n')


if __name__ == '__main__':
    main()
