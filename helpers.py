import re
from datetime import date, timedelta
from email.utils import parseaddr
from pathlib import Path


def sanitise_filename(name: str) -> str:
    """Sanitise a client name for use in a filename."""
    result = name.lower()
    result = result.replace(' ', '-')
    result = re.sub(r'-+', '-', result)
    result = re.sub(r'[^a-z0-9-]', '', result)
    result = re.sub(r'-+', '-', result)
    return result[:30].strip('-')


def next_invoice_number(records: list) -> str:
    """Determine the next invoice number from existing records (all statuses)."""
    max_num = 0
    for record in records:
        num_str = record.get('number', '')
        if num_str.startswith('INV-'):
            try:
                n = int(num_str[4:])
                if n > max_num:
                    max_num = n
            except ValueError:
                pass
    next_num = max_num + 1
    if next_num < 1000:
        return f'INV-{next_num:03d}'
    return f'INV-{next_num}'


def validate_email(addr: str) -> bool:
    """Validate an email address: must parse to a non-empty address containing @."""
    _, address = parseaddr(addr)
    return bool(address) and '@' in address and address != '@'


def calculate_totals(line_items: list, apply_vat: bool) -> dict:
    """Calculate subtotal, VAT, and total from line items."""
    subtotal = sum(item['qty'] * item['unit_price'] for item in line_items)
    vat = round(subtotal * 0.20, 2) if apply_vat else 0.0
    total = round(subtotal + vat, 2)
    return {
        'subtotal': round(subtotal, 2),
        'vat': vat,
        'total': total,
    }


def compute_due_date(days: int) -> date:
    """Return the absolute due date given days from today."""
    return date.today() + timedelta(days=days)


def format_date_display(d: date) -> str:
    """Format a date as '16 April 2026'."""
    return f"{d.day} {d.strftime('%B %Y')}"


def format_plain_text_body(data: dict) -> str:
    """Generate a plain-text email body from invoice data."""
    vat_note = ' (inc. VAT)' if data['vat_applied'] else ''
    lines = [
        f"Invoice {data['number']} from {data['business_name']}",
        '',
        f"Billed to: {data['client_name']} <{data['client_email']}>",
        f"Amount due: \u00a3{data['totals']['total']:,.2f}{vat_note}",
        f"Due date: {format_date_display(data['date_due'])}",
        '',
        'To pay, please use the following bank details:',
        f"Payee: {data['bank_payee']}",
        f"Sort code: {data['bank_sort_code']}",
        f"Account: {data['bank_account']}",
        '',
        f"Please use invoice number {data['number']} as your payment reference.",
    ]
    return '\n'.join(lines)


def pdf_output_path(invoices_dir: Path, number: str, client_name: str, issued_date: date) -> str:
    """Compute a unique PDF output path, appending -2, -3 etc. to avoid overwrites."""
    base = f"{number}-{sanitise_filename(client_name)}-{issued_date.isoformat()}"
    path = invoices_dir / f"{base}.pdf"
    if not path.exists():
        return str(path)
    counter = 2
    while True:
        path = invoices_dir / f"{base}-{counter}.pdf"
        if not path.exists():
            return str(path)
        counter += 1
