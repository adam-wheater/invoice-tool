import os
from datetime import date, timedelta
from pathlib import Path
import tempfile
from helpers import (
    sanitise_filename,
    next_invoice_number,
    validate_email,
    calculate_totals,
    format_plain_text_body,
    format_date_display,
    compute_due_date,
    pdf_output_path,
)


# ── sanitise_filename ──────────────────────────────────────────────────────────

def test_sanitise_filename_basic():
    assert sanitise_filename('Acme Ltd') == 'acme-ltd'

def test_sanitise_filename_apostrophe():
    assert sanitise_filename("O'Brien") == 'obrien'

def test_sanitise_filename_ampersand_collapses_hyphen():
    # space→hyphen, &→stripped, space→hyphen → "acme--co" → collapsed → "acme-co"
    assert sanitise_filename('Acme & Co') == 'acme-co'

def test_sanitise_filename_non_ascii():
    assert sanitise_filename('Müller GmbH') == 'mller-gmbh'

def test_sanitise_filename_truncates_to_30():
    long_name = 'A Very Long Company Name That Exceeds Thirty Characters'
    result = sanitise_filename(long_name)
    assert len(result) <= 30

def test_sanitise_filename_no_trailing_hyphen_after_truncation():
    # 29 'a's + '-extra' → after truncation at 30 chars the last char would be '-'
    name = 'a' * 29 + '-extra'
    result = sanitise_filename(name)
    assert not result.endswith('-')

def test_sanitise_filename_consecutive_spaces():
    assert sanitise_filename('Foo  Bar') == 'foo-bar'


# ── next_invoice_number ────────────────────────────────────────────────────────

def test_next_invoice_number_empty_log():
    assert next_invoice_number([]) == 'INV-001'

def test_next_invoice_number_increments():
    records = [{'number': 'INV-001', 'status': 'sent'}]
    assert next_invoice_number(records) == 'INV-002'

def test_next_invoice_number_pads_to_three_digits():
    records = [{'number': 'INV-009', 'status': 'sent'}]
    assert next_invoice_number(records) == 'INV-010'

def test_next_invoice_number_includes_pending_in_highest():
    records = [
        {'number': 'INV-005', 'status': 'sent'},
        {'number': 'INV-006', 'status': 'pending'},
    ]
    assert next_invoice_number(records) == 'INV-007'

def test_next_invoice_number_no_truncation_past_999():
    records = [{'number': 'INV-999', 'status': 'sent'}]
    assert next_invoice_number(records) == 'INV-1000'

def test_next_invoice_number_handles_out_of_order():
    records = [
        {'number': 'INV-003', 'status': 'sent'},
        {'number': 'INV-001', 'status': 'sent'},
    ]
    assert next_invoice_number(records) == 'INV-004'


# ── validate_email ─────────────────────────────────────────────────────────────

def test_validate_email_simple():
    assert validate_email('user@example.com') is True

def test_validate_email_with_display_name():
    assert validate_email('John Doe <john@example.com>') is True

def test_validate_email_no_at_sign():
    assert validate_email('notanemail') is False

def test_validate_email_empty_string():
    assert validate_email('') is False

def test_validate_email_at_only():
    assert validate_email('@') is False


# ── calculate_totals ───────────────────────────────────────────────────────────

def test_calculate_totals_no_vat():
    items = [{'qty': 2, 'unit_price': 100.0}]
    result = calculate_totals(items, apply_vat=False)
    assert result == {'subtotal': 200.0, 'vat': 0.0, 'total': 200.0}

def test_calculate_totals_with_vat():
    items = [{'qty': 1, 'unit_price': 1000.0}]
    result = calculate_totals(items, apply_vat=True)
    assert result == {'subtotal': 1000.0, 'vat': 200.0, 'total': 1200.0}

def test_calculate_totals_multiple_items():
    items = [
        {'qty': 3, 'unit_price': 50.0},
        {'qty': 1, 'unit_price': 25.0},
    ]
    result = calculate_totals(items, apply_vat=False)
    assert result['subtotal'] == 175.0
    assert result['total'] == 175.0

def test_calculate_totals_vat_rounding():
    # 99.99 * 0.20 = 19.998 → rounds to 20.0
    items = [{'qty': 1, 'unit_price': 99.99}]
    result = calculate_totals(items, apply_vat=True)
    assert result['vat'] == 20.0
    assert result['total'] == 119.99


# ── format_date_display ────────────────────────────────────────────────────────

def test_format_date_display():
    assert format_date_display(date(2026, 4, 16)) == '16 April 2026'

def test_format_date_display_single_digit_day():
    assert format_date_display(date(2026, 1, 5)) == '5 January 2026'


# ── format_plain_text_body ─────────────────────────────────────────────────────

def _sample_data(vat=True):
    return {
        'number': 'INV-001',
        'business_name': 'Test Co',
        'client_name': 'Acme Ltd',
        'client_email': 'billing@acme.com',
        'vat_applied': vat,
        'totals': {'total': 1200.0},
        'date_due': date(2026, 4, 16),
        'bank_payee': 'Adam Wheater',
        'bank_sort_code': '23-01-20',
        'bank_account': '66530274',
    }

def test_format_plain_text_body_contains_key_fields():
    body = format_plain_text_body(_sample_data())
    assert 'INV-001' in body
    assert 'Acme Ltd' in body
    assert '£1,200.00' in body
    assert '16 April 2026' in body
    assert 'Adam Wheater' in body
    assert '23-01-20' in body
    assert '66530274' in body

def test_format_plain_text_body_vat_note():
    body = format_plain_text_body(_sample_data(vat=True))
    assert 'inc. VAT' in body

def test_format_plain_text_body_no_vat_note():
    body = format_plain_text_body(_sample_data(vat=False))
    assert 'inc. VAT' not in body


# ── compute_due_date ───────────────────────────────────────────────────────────

def test_compute_due_date_30_days():
    result = compute_due_date(30)
    assert result == date.today() + timedelta(days=30)

def test_compute_due_date_1_day():
    result = compute_due_date(1)
    assert result == date.today() + timedelta(days=1)


# ── pdf_output_path ────────────────────────────────────────────────────────────

def test_pdf_output_path_new_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        result = pdf_output_path(d, 'INV-001', 'Acme Ltd', date(2026, 3, 17))
        assert result == str(d / 'INV-001-acme-ltd-2026-03-17.pdf')

def test_pdf_output_path_avoids_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        # Create the base file to simulate a collision
        (d / 'INV-001-acme-ltd-2026-03-17.pdf').touch()
        result = pdf_output_path(d, 'INV-001', 'Acme Ltd', date(2026, 3, 17))
        assert result == str(d / 'INV-001-acme-ltd-2026-03-17-2.pdf')

def test_pdf_output_path_avoids_multiple_overwrites():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        (d / 'INV-001-acme-ltd-2026-03-17.pdf').touch()
        (d / 'INV-001-acme-ltd-2026-03-17-2.pdf').touch()
        result = pdf_output_path(d, 'INV-001', 'Acme Ltd', date(2026, 3, 17))
        assert result == str(d / 'INV-001-acme-ltd-2026-03-17-3.pdf')
