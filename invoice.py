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
import smtplib
import sys
from datetime import date, datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
    'smtp_port': 465,
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
    """Load config; prompt for any missing or blank required fields."""
    config = {**CONFIG_DEFAULTS, **_load_config_file()}
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
