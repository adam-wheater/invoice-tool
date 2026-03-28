"""Tests for invoice.py functions (config management, env var injection)."""
import email
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import invoice


# ── ensure_config: env var injection ──────────────────────────────────────────

def _write_config(tmpdir: Path, data: dict) -> Path:
    p = tmpdir / 'config.json'
    p.write_text(json.dumps(data))
    return p


def test_ensure_config_reads_smtp_user_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setenv('INVOICE_SMTP_USER', 'env@example.com')
    monkeypatch.delenv('INVOICE_SMTP_PASSWORD', raising=False)

    # Provide all other required fields so no prompt is triggered
    base = {
        'business_name': 'Test Co', 'business_address': '1 St', 'business_email': 'a@b.com',
        'business_phone': '01234', 'bank_payee': 'Test Payee', 'bank_sort_code': '00-00-00',
        'bank_account': '00000000', 'smtp_host': 'smtp.example.com',
        'smtp_user': '', 'smtp_password': 'secret', 'smtp_from': 'a@b.com',
    }
    _write_config(tmp_path, base)

    config = invoice.ensure_config()
    assert config['smtp_user'] == 'env@example.com'


def test_ensure_config_reads_smtp_password_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setenv('INVOICE_SMTP_PASSWORD', 'envpassword')
    monkeypatch.delenv('INVOICE_SMTP_USER', raising=False)

    base = {
        'business_name': 'Test Co', 'business_address': '1 St', 'business_email': 'a@b.com',
        'business_phone': '01234', 'bank_payee': 'Test Payee', 'bank_sort_code': '00-00-00',
        'bank_account': '00000000', 'smtp_host': 'smtp.example.com',
        'smtp_user': 'user@example.com', 'smtp_password': '', 'smtp_from': 'user@example.com',
    }
    _write_config(tmp_path, base)

    config = invoice.ensure_config()
    assert config['smtp_password'] == 'envpassword'


def test_ensure_config_smtp_from_defaults_to_env_user_when_blank(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setenv('INVOICE_SMTP_USER', 'env@example.com')
    monkeypatch.delenv('INVOICE_SMTP_PASSWORD', raising=False)

    base = {
        'business_name': 'Test Co', 'business_address': '1 St', 'business_email': 'a@b.com',
        'business_phone': '01234', 'bank_payee': 'Test Payee', 'bank_sort_code': '00-00-00',
        'bank_account': '00000000', 'smtp_host': 'smtp.example.com',
        'smtp_user': '', 'smtp_password': 'secret', 'smtp_from': '',
    }
    _write_config(tmp_path, base)

    # smtp_from is blank — should be prompted. Mock input to provide it.
    with mock.patch('builtins.input', return_value='env@example.com'):
        config = invoice.ensure_config()

    assert config['smtp_from'] == 'env@example.com'


# ── send_invoice_email: recipient override ─────────────────────────────────────

def _make_invoice_data():
    return {
        'number': 'INV-001',
        'plain_text_body': 'test body',
        'client_email': 'original@example.com',
    }

def _make_config():
    return {
        'business_name': 'Test Co',
        'smtp_from': 'sender@example.com',
        'smtp_host': 'smtp.hostinger.com',
        'smtp_port': 587,
        'smtp_user': 'u',
        'smtp_password': 'p',
    }


def test_send_invoice_email_defaults_to_client_email(tmp_path):
    pdf = tmp_path / 'test.pdf'
    pdf.write_bytes(b'%PDF')
    with mock.patch('invoice.smtplib.SMTP') as mock_smtp_cls:
        mock_server = mock_smtp_cls.return_value.__enter__.return_value
        invoice.send_invoice_email(_make_config(), _make_invoice_data(), '<html/>', str(pdf))
        _, sendmail_args, _ = mock_server.sendmail.mock_calls[0]
        assert sendmail_args[1] == ['original@example.com']


def test_send_invoice_email_uses_recipient_override(tmp_path):
    pdf = tmp_path / 'test.pdf'
    pdf.write_bytes(b'%PDF')
    with mock.patch('invoice.smtplib.SMTP') as mock_smtp_cls:
        mock_server = mock_smtp_cls.return_value.__enter__.return_value
        invoice.send_invoice_email(
            _make_config(), _make_invoice_data(), '<html/>', str(pdf),
            recipient='override@example.com'
        )
        _, sendmail_args, _ = mock_server.sendmail.mock_calls[0]
        assert sendmail_args[1] == ['override@example.com']


def test_send_invoice_email_to_header_uses_recipient(tmp_path):
    """msg['To'] header must also use the override, not the original client_email."""
    pdf = tmp_path / 'test.pdf'
    pdf.write_bytes(b'%PDF')
    captured = {}
    def fake_sendmail(from_addr, to_addrs, msg_str):
        msg = email.message_from_string(msg_str)
        captured['to_header'] = msg['To']
    with mock.patch('invoice.smtplib.SMTP') as mock_smtp_cls:
        mock_server = mock_smtp_cls.return_value.__enter__.return_value
        mock_server.sendmail.side_effect = fake_sendmail
        invoice.send_invoice_email(
            _make_config(), _make_invoice_data(), '<html/>', str(pdf),
            recipient='override@example.com'
        )
    assert captured['to_header'] == 'override@example.com'


from datetime import date as date_type


# ── build_invoice_data_from_record ─────────────────────────────────────────────

def _sample_record(**overrides):
    base = {
        'number': 'INV-001',
        'status': 'sent',
        'client_name': 'Acme Ltd',
        'client_email': 'billing@acme.com',
        'date_issued': '2026-03-17',
        'date_due': '2026-04-16',
        'line_items': [{'description': 'Web dev', 'qty': 1, 'unit_price': 1000.0}],
        'vat_applied': True,
        'total_gbp': 1200.0,
        'notes': 'Pay promptly',
        'pdf_path': 'invoices/INV-001-acme-ltd-2026-03-17.pdf',
        'sent_at': '2026-03-17T14:00:00Z',
    }
    base.update(overrides)
    return base

def _sample_config():
    return {
        'business_name': 'Test Business', 'business_address': '1 Example Street',
        'business_email': 'test@example.com', 'business_phone': '01234567890',
        'bank_payee': 'Test Payee', 'bank_sort_code': '00-00-00',
        'bank_account': '00000000',
    }


def test_build_invoice_data_from_record_dates_are_date_objects():
    data = invoice.build_invoice_data_from_record(_sample_record(), _sample_config())
    assert isinstance(data['date_issued'], date_type)
    assert isinstance(data['date_due'], date_type)
    assert data['date_issued'] == date_type(2026, 3, 17)
    assert data['date_due'] == date_type(2026, 4, 16)


def test_build_invoice_data_from_record_totals_recomputed():
    data = invoice.build_invoice_data_from_record(_sample_record(), _sample_config())
    assert data['totals']['subtotal'] == 1000.0
    assert data['totals']['vat'] == 200.0
    assert data['totals']['total'] == 1200.0


def test_build_invoice_data_from_record_client_address_is_empty_string():
    data = invoice.build_invoice_data_from_record(_sample_record(), _sample_config())
    assert data['client_address'] == ''


def test_build_invoice_data_from_record_client_address_from_record():
    record = _sample_record()
    record['client_address'] = '10 Downing Street\nLondon'
    data = invoice.build_invoice_data_from_record(record, _sample_config())
    assert data['client_address'] == '10 Downing Street\nLondon'


def test_build_invoice_data_from_record_notes_from_record():
    data = invoice.build_invoice_data_from_record(_sample_record(), _sample_config())
    assert data['notes'] == 'Pay promptly'


def test_build_invoice_data_from_record_notes_defaults_to_empty():
    record = _sample_record()
    del record['notes']
    data = invoice.build_invoice_data_from_record(record, _sample_config())
    assert data['notes'] == ''


def test_build_invoice_data_from_record_business_fields_from_config():
    data = invoice.build_invoice_data_from_record(_sample_record(), _sample_config())
    assert data['business_name'] == 'Test Business'
    assert data['bank_payee'] == 'Test Payee'


def test_build_invoice_data_from_record_plain_text_body_present():
    data = invoice.build_invoice_data_from_record(_sample_record(), _sample_config())
    assert 'plain_text_body' in data
    assert 'INV-001' in data['plain_text_body']
    assert 'Acme Ltd' in data['plain_text_body']


# ── _select_invoice_from_list ──────────────────────────────────────────────────

def _sent_records():
    return [
        {'number': 'INV-001', 'client_name': 'Acme Ltd'},
        {'number': 'INV-002', 'client_name': 'Bob Smith'},
        {'number': 'INV-003', 'client_name': 'Charlie Co'},
    ]


def test_select_by_list_number():
    assert invoice._select_invoice_from_list(_sent_records(), '1')['number'] == 'INV-001'
    assert invoice._select_invoice_from_list(_sent_records(), '2')['number'] == 'INV-002'
    assert invoice._select_invoice_from_list(_sent_records(), '3')['number'] == 'INV-003'


def test_select_by_invoice_number():
    assert invoice._select_invoice_from_list(_sent_records(), 'INV-002')['number'] == 'INV-002'


def test_select_by_invoice_number_case_insensitive():
    assert invoice._select_invoice_from_list(_sent_records(), 'inv-001')['number'] == 'INV-001'


def test_select_invalid_returns_none():
    assert invoice._select_invoice_from_list(_sent_records(), 'xyz') is None
    assert invoice._select_invoice_from_list(_sent_records(), '0') is None
    assert invoice._select_invoice_from_list(_sent_records(), '99') is None
    assert invoice._select_invoice_from_list(_sent_records(), '') is None


# ── mark_invoice_paid ──────────────────────────────────────────────────────────

def test_mark_invoice_paid_sets_status(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    records = [{'number': 'INV-001', 'status': 'sent', 'total_gbp': 100.0}]
    invoice.mark_invoice_paid(records, 'INV-001')
    saved = json.loads((tmp_path / 'invoices.json').read_text())
    assert saved[0]['status'] == 'paid'


def test_mark_invoice_paid_adds_paid_at(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    records = [{'number': 'INV-001', 'status': 'sent'}]
    invoice.mark_invoice_paid(records, 'INV-001')
    saved = json.loads((tmp_path / 'invoices.json').read_text())
    assert 'paid_at' in saved[0]
    assert saved[0]['paid_at'].endswith('Z')


def test_mark_invoice_paid_unknown_number_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    records = [{'number': 'INV-001', 'status': 'sent'}]
    invoice.mark_invoice_paid(records, 'INV-999')
    saved = json.loads((tmp_path / 'invoices.json').read_text())
    assert saved[0]['status'] == 'sent'


# ── view_history_flow ──────────────────────────────────────────────────────────

def _make_records_for_history():
    return [
        {'number': 'INV-001', 'status': 'sent', 'client_name': 'Acme Ltd',
         'total_gbp': 300.0, 'date_issued': '2026-03-18'},
        {'number': 'INV-002', 'status': 'paid', 'client_name': 'Bob Co',
         'total_gbp': 500.0, 'date_issued': '2026-03-20'},
        {'number': 'INV-003', 'status': 'pending', 'client_name': 'Charlie',
         'total_gbp': 100.0, 'date_issued': '2026-03-21'},
    ]


def test_view_history_flow_shows_sent_and_paid(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text(
        json.dumps(_make_records_for_history())
    )
    invoice.view_history_flow({})
    out = capsys.readouterr().out
    assert 'INV-001' in out
    assert 'INV-002' in out


def test_view_history_flow_excludes_pending(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text(
        json.dumps(_make_records_for_history())
    )
    invoice.view_history_flow({})
    out = capsys.readouterr().out
    assert 'INV-003' not in out


def test_view_history_flow_empty_no_records(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text('[]')
    invoice.view_history_flow({})
    out = capsys.readouterr().out
    assert 'No invoices found' in out


def test_view_history_flow_empty_all_pending(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text(json.dumps([
        {'number': 'INV-001', 'status': 'pending', 'client_name': 'Acme',
         'total_gbp': 100.0, 'date_issued': '2026-03-18'},
    ]))
    invoice.view_history_flow({})
    out = capsys.readouterr().out
    assert 'No invoices found' in out


# ── mark_paid_flow ─────────────────────────────────────────────────────────────

def test_mark_paid_flow_marks_selected_invoice(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text(json.dumps([
        {'number': 'INV-001', 'status': 'sent', 'client_name': 'Acme',
         'total_gbp': 300.0, 'date_issued': '2026-03-18'},
    ]))
    with mock.patch('builtins.input', side_effect=['1', 'y']):
        invoice.mark_paid_flow({})
    saved = json.loads((tmp_path / 'invoices.json').read_text())
    assert saved[0]['status'] == 'paid'


def test_mark_paid_flow_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text(json.dumps([
        {'number': 'INV-001', 'status': 'sent', 'client_name': 'Acme',
         'total_gbp': 300.0, 'date_issued': '2026-03-18'},
    ]))
    with mock.patch('builtins.input', side_effect=['1', 'n']):
        invoice.mark_paid_flow({})
    saved = json.loads((tmp_path / 'invoices.json').read_text())
    assert saved[0]['status'] == 'sent'


def test_mark_paid_flow_no_unpaid(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(invoice, 'INVOICES_FILE', tmp_path / 'invoices.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    (tmp_path / 'invoices.json').write_text(json.dumps([
        {'number': 'INV-001', 'status': 'paid', 'client_name': 'Acme',
         'total_gbp': 300.0, 'date_issued': '2026-03-18'},
    ]))
    invoice.mark_paid_flow({})
    out = capsys.readouterr().out
    assert 'No unpaid invoices found' in out


# ── edit_settings_flow ─────────────────────────────────────────────────────────

def _full_config():
    return {
        'business_name': 'Old Co', 'business_address': '1 St',
        'business_email': 'old@example.com', 'business_phone': '01234',
        'bank_payee': 'Old Payee', 'bank_sort_code': '00-00-00',
        'bank_account': '00000000', 'smtp_host': 'smtp.example.com',
        'smtp_port': 587, 'smtp_user': 'user@example.com',
        'smtp_password': 'secret', 'smtp_from': 'user@example.com',
    }


def test_edit_settings_flow_updates_field(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    monkeypatch.delenv('INVOICE_SMTP_USER', raising=False)
    monkeypatch.delenv('INVOICE_SMTP_PASSWORD', raising=False)
    config = _full_config()
    # Press Enter for every field except business_name (first field)
    field_count = sum(len(fields) for _, fields in invoice.SETUP_SECTIONS)
    inputs = ['New Co'] + [''] * (field_count - 1)
    with mock.patch('builtins.input', side_effect=inputs):
        result = invoice.edit_settings_flow(config)
    assert result['business_name'] == 'New Co'


def test_edit_settings_flow_keeps_existing_on_enter(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    monkeypatch.delenv('INVOICE_SMTP_USER', raising=False)
    monkeypatch.delenv('INVOICE_SMTP_PASSWORD', raising=False)
    config = _full_config()
    field_count = sum(len(fields) for _, fields in invoice.SETUP_SECTIONS)
    with mock.patch('builtins.input', side_effect=[''] * field_count):
        result = invoice.edit_settings_flow(config)
    assert result['business_name'] == 'Old Co'
    assert result['smtp_password'] == 'secret'


def test_edit_settings_flow_masks_password(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(invoice, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setattr(invoice, 'APP_DATA_DIR', tmp_path)
    monkeypatch.delenv('INVOICE_SMTP_USER', raising=False)
    monkeypatch.delenv('INVOICE_SMTP_PASSWORD', raising=False)
    config = _full_config()
    field_count = sum(len(fields) for _, fields in invoice.SETUP_SECTIONS)
    with mock.patch('builtins.input', side_effect=[''] * field_count):
        invoice.edit_settings_flow(config)
    out = capsys.readouterr().out
    assert 'secret' not in out
    assert '****' in out
