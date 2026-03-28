# Invoice Tool UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add history submenu, mark-as-paid tracking, edit-settings flow, and client address persistence to the CLI invoice generator.

**Architecture:** All changes are in `invoice.py` and `tests/test_invoice.py` — `helpers.py` is untouched. New functions are added in logical order: data mutation first, then interactive flows, then menu wiring. Every new data function is TDD'd independently before its interactive flow is built on top.

**Tech Stack:** Python 3, pytest, stdlib only (no new dependencies)

---

## File Map

| File | Changes |
|---|---|
| `invoice.py` | Add 4 new functions; modify 5 existing functions; update 4 hint strings |
| `tests/test_invoice.py` | Add tests for all new/changed behaviour |

Run tests throughout with: `venv/bin/pytest tests/ -v`

---

### Task 1: Persist and restore client_address

**Files:**
- Modify: `invoice.py:247` (`build_invoice_data_from_record`)
- Modify: `invoice.py:855–860` (`new_invoice_flow` — `log_data` dict)
- Modify: `tests/test_invoice.py` (add one test, keep existing)

- [ ] **Step 1: Write failing test**

Add to `tests/test_invoice.py` after `test_build_invoice_data_from_record_client_address_is_empty_string`:

```python
def test_build_invoice_data_from_record_client_address_from_record():
    record = _sample_record()
    record['client_address'] = '10 Downing Street\nLondon'
    data = invoice.build_invoice_data_from_record(record, _sample_config())
    assert data['client_address'] == '10 Downing Street\nLondon'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
venv/bin/pytest tests/test_invoice.py::test_build_invoice_data_from_record_client_address_from_record -v
```

Expected: FAIL — `assert '' == '10 Downing Street\nLondon'`

- [ ] **Step 3: Fix `build_invoice_data_from_record` in `invoice.py`**

At line 247, change:
```python
        'client_address': '',
```
to:
```python
        'client_address': record.get('client_address', ''),
```

Also update the docstring — remove this line (around line 239):
```
    client_address is always '' (not stored in log).
```

- [ ] **Step 4: Run tests to verify pass**

```bash
venv/bin/pytest tests/test_invoice.py -v
```

Expected: all pass, including the existing `test_build_invoice_data_from_record_client_address_is_empty_string` (which uses a record with no address field — still returns `''`).

- [ ] **Step 5: Add `client_address` to `log_data` in `new_invoice_flow`**

In `invoice.py` around line 855, the `log_data` dict is assembled. Add one line:

```python
    log_data = {
        'client_name': client['client_name'],
        'client_email': client['client_email'],
        'client_address': client['client_address'],   # ← add this line
        'date_issued': issued.isoformat(),
        ...
    }
```

- [ ] **Step 6: Run full test suite**

```bash
venv/bin/pytest tests/ -v
```

Expected: all 50 pass (49 existing + 1 new).

- [ ] **Step 7: Commit**

```bash
git add invoice.py tests/test_invoice.py
git commit -m "feat: persist and restore client_address in invoice log"
```

---

### Task 2: Add `mark_invoice_paid()` data function

**Files:**
- Modify: `invoice.py` (add function after `finalise_invoice`, around line 200)
- Modify: `tests/test_invoice.py` (add 3 tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_invoice.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_invoice.py::test_mark_invoice_paid_sets_status tests/test_invoice.py::test_mark_invoice_paid_adds_paid_at tests/test_invoice.py::test_mark_invoice_paid_unknown_number_does_nothing -v
```

Expected: FAIL — `AttributeError: module 'invoice' has no attribute 'mark_invoice_paid'`

- [ ] **Step 3: Implement `mark_invoice_paid()` in `invoice.py`**

Add after the `finalise_invoice` function (around line 200):

```python
def mark_invoice_paid(records: list, number: str) -> None:
    """Mark a sent invoice record as paid."""
    for record in records:
        if record.get('number') == number:
            record['status'] = 'paid'
            record['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            break
    _save_invoices(records)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_invoice.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add invoice.py tests/test_invoice.py
git commit -m "feat: add mark_invoice_paid data function"
```

---

### Task 3: Add `view_history_flow()`

**Files:**
- Modify: `invoice.py` (add function)
- Modify: `tests/test_invoice.py` (add 3 tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_invoice.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_invoice.py::test_view_history_flow_shows_sent_and_paid tests/test_invoice.py::test_view_history_flow_excludes_pending tests/test_invoice.py::test_view_history_flow_empty_no_records tests/test_invoice.py::test_view_history_flow_empty_all_pending -v
```

Expected: FAIL — `AttributeError: module 'invoice' has no attribute 'view_history_flow'`

- [ ] **Step 3: Implement `view_history_flow()` in `invoice.py`**

Add after `resend_flow` (around line 490):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_invoice.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add invoice.py tests/test_invoice.py
git commit -m "feat: add view_history_flow"
```

---

### Task 4: Add `mark_paid_flow()`

**Files:**
- Modify: `invoice.py` (add function)
- Modify: `tests/test_invoice.py` (add 3 tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_invoice.py`:

```python
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
    (tmp_path / 'invoices.json').write_text(json.dumps([
        {'number': 'INV-001', 'status': 'paid', 'client_name': 'Acme',
         'total_gbp': 300.0, 'date_issued': '2026-03-18'},
    ]))
    invoice.mark_paid_flow({})
    out = capsys.readouterr().out
    assert 'No unpaid invoices found' in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_invoice.py::test_mark_paid_flow_marks_selected_invoice tests/test_invoice.py::test_mark_paid_flow_cancelled tests/test_invoice.py::test_mark_paid_flow_no_unpaid -v
```

Expected: FAIL — `AttributeError: module 'invoice' has no attribute 'mark_paid_flow'`

- [ ] **Step 3: Implement `mark_paid_flow()` in `invoice.py`**

Add after `view_history_flow`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_invoice.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add invoice.py tests/test_invoice.py
git commit -m "feat: add mark_paid_flow"
```

---

### Task 5: Add `edit_settings_flow()`

**Files:**
- Modify: `invoice.py` (add function)
- Modify: `tests/test_invoice.py` (add 3 tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_invoice.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_invoice.py::test_edit_settings_flow_updates_field tests/test_invoice.py::test_edit_settings_flow_keeps_existing_on_enter tests/test_invoice.py::test_edit_settings_flow_masks_password -v
```

Expected: FAIL — `AttributeError: module 'invoice' has no attribute 'edit_settings_flow'`

- [ ] **Step 3: Implement `edit_settings_flow()` in `invoice.py`**

Add after `smtp_test_flow`:

```python
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
            raw = input(f'  {label}{hint}{env_note}: ').strip()
            if raw:
                config[field] = raw

    _save_config(config)
    print('\n  Settings saved.')
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_invoice.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add invoice.py tests/test_invoice.py
git commit -m "feat: add edit_settings_flow"
```

---

### Task 6: Add `prompt_history_mode()` and update `prompt_mode()`

**Files:**
- Modify: `invoice.py` (`prompt_mode` function + add `prompt_history_mode`)
- Modify: `tests/test_invoice.py` (add tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_invoice.py`:

```python
# ── prompt_history_mode ────────────────────────────────────────────────────────

def test_prompt_history_mode_view():
    with mock.patch('builtins.input', return_value='1'):
        assert invoice.prompt_history_mode() == 'view'

def test_prompt_history_mode_resend():
    with mock.patch('builtins.input', return_value='2'):
        assert invoice.prompt_history_mode() == 'resend'

def test_prompt_history_mode_mark_paid():
    with mock.patch('builtins.input', return_value='3'):
        assert invoice.prompt_history_mode() == 'mark_paid'

def test_prompt_history_mode_back():
    with mock.patch('builtins.input', return_value='0'):
        assert invoice.prompt_history_mode() == 'back'


# ── prompt_mode (updated) ──────────────────────────────────────────────────────

def test_prompt_mode_new_default():
    with mock.patch('builtins.input', return_value=''):
        assert invoice.prompt_mode() == 'new'

def test_prompt_mode_history():
    with mock.patch('builtins.input', return_value='2'):
        assert invoice.prompt_mode() == 'history'

def test_prompt_mode_edit_settings():
    with mock.patch('builtins.input', return_value='4'):
        assert invoice.prompt_mode() == 'edit_settings'

def test_prompt_mode_smtp_test():
    with mock.patch('builtins.input', return_value='5'):
        assert invoice.prompt_mode() == 'smtp_test'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_invoice.py::test_prompt_history_mode_view tests/test_invoice.py::test_prompt_mode_history tests/test_invoice.py::test_prompt_mode_edit_settings tests/test_invoice.py::test_prompt_mode_smtp_test -v
```

Expected: FAIL.

- [ ] **Step 3: Update `prompt_mode()` in `invoice.py`**

Replace the existing `prompt_mode` function body:

```python
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
```

- [ ] **Step 4: Add `prompt_history_mode()` in `invoice.py`**

Add immediately after `prompt_mode`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_invoice.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add invoice.py tests/test_invoice.py
git commit -m "feat: add prompt_history_mode and update prompt_mode for new menu"
```

---

### Task 7: Wire up `main()` and fix hint strings

**Files:**
- Modify: `invoice.py` (`main` function + 4 hint strings)

No new tests needed — the hint strings are print statements and `main()` is an integration entry point not unit-tested.

- [ ] **Step 1: Update `main()` in `invoice.py`**

Replace the existing `main` function body:

```python
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
        elif mode == 'history':
            while True:
                print()
                sub = prompt_history_mode()
                if sub == 'back':
                    break
                elif sub == 'view':
                    view_history_flow(config)
                elif sub == 'resend':
                    resend_flow(config)
                elif sub == 'mark_paid':
                    mark_paid_flow(config)
        elif mode == 'send_folder':
            send_from_folder_flow(config)
        elif mode == 'edit_settings':
            config = edit_settings_flow(config)
        elif mode == 'smtp_test':
            smtp_test_flow(config)
```

- [ ] **Step 2: Update the 4 hardcoded hint strings**

In `invoice.py`, find and update these four strings:

| Location | Old | New |
|---|---|---|
| `resend_flow` (~line 487) | `'  Use option 3 to test your SMTP settings.'` | `'  Use option 5 to test your SMTP settings.'` |
| `send_from_folder_flow` (~line 577) | `'  Use option 3 to test your SMTP settings.'` | `'  Use option 5 to test your SMTP settings.'` |
| `new_invoice_flow` (~line 846) | `'  Use option 3 to test your SMTP settings.'` | `'  Use option 5 to test your SMTP settings.'` |
| `new_invoice_flow` (~line 845) | `'  Invoice log record left as pending — use option 2 to send it manually.'` | `'  Invoice log record left as pending — use option 3 to send it manually.'` |

- [ ] **Step 3: Run the full test suite**

```bash
venv/bin/pytest tests/ -v
```

Expected: all tests pass. Final count should be ~68 (49 original + ~19 new).

- [ ] **Step 4: Smoke test manually** *(optional but recommended)*

```bash
venv/bin/python invoice.py
```

Navigate through: History → View invoices, History → Mark as paid, Edit settings. Verify the menu shows correctly and all flows work.

- [ ] **Step 5: Commit**

```bash
git add invoice.py
git commit -m "feat: wire up history submenu and edit settings in main; fix option hint strings"
```

---

## Done

All four improvements implemented:
- `client_address` persisted in invoice log and restored on resend
- `mark_invoice_paid()` + `mark_paid_flow()` track payment status
- `view_history_flow()` shows all sent/paid invoices
- `edit_settings_flow()` lets users update config without touching files
- Menu restructured with History submenu and Edit settings option
