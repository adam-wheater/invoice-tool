"""Tests for invoice.py functions (config management, env var injection)."""
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
        'business_phone': '01234', 'bank_payee': 'Adam Wheater', 'bank_sort_code': '23-01-20',
        'bank_account': '66530274', 'smtp_host': 'smtp.hostinger.com',
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
        'business_phone': '01234', 'bank_payee': 'Adam Wheater', 'bank_sort_code': '23-01-20',
        'bank_account': '66530274', 'smtp_host': 'smtp.hostinger.com',
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
        'business_phone': '01234', 'bank_payee': 'Adam Wheater', 'bank_sort_code': '23-01-20',
        'bank_account': '66530274', 'smtp_host': 'smtp.hostinger.com',
        'smtp_user': '', 'smtp_password': 'secret', 'smtp_from': '',
    }
    _write_config(tmp_path, base)

    # smtp_from is blank — should be prompted. Mock input to provide it.
    with mock.patch('builtins.input', return_value='env@example.com'):
        config = invoice.ensure_config()

    assert config['smtp_from'] == 'env@example.com'
