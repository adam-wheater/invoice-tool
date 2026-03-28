# Invoice Tool — UX Improvements Design

**Date:** 2026-03-28
**Status:** Approved

---

## Overview

Four improvements to the CLI invoice generator targeting real day-to-day friction:

1. History submenu (view invoices, resend, mark as paid)
2. Edit settings from the menu (no need to delete config.json)
3. Mark invoice as paid (track payment status)
4. Client address saved and used on resend (currently discarded)

---

## Menu Structure

### Main menu (was 4 options, becomes 5)

```
1) New invoice
2) History
3) Send unsent invoice from folder
4) Edit settings
5) Test SMTP connection
0) Exit
```

Blank Enter still defaults to option 1 (`new`), same as today.

### History submenu (new)

```
1) View invoices
2) Resend invoice
3) Mark invoice as paid
0) Back
```

"Resend" moves from the main menu into the History submenu. The main menu gains "History" (option 2) and "Edit settings" (option 4); "Test SMTP" shifts from option 3 to option 5.

**Hardcoded hint strings to update** — three locations reference old menu option numbers and must be changed:

| Function | Old string | New string |
|---|---|---|
| `resend_flow` | `'Use option 3 to test your SMTP settings.'` | `'Use option 5 to test your SMTP settings.'` |
| `send_from_folder_flow` | `'Use option 3 to test your SMTP settings.'` | `'Use option 5 to test your SMTP settings.'` |
| `new_invoice_flow` | `'Use option 3 to test your SMTP settings.'` | `'Use option 5 to test your SMTP settings.'` |
| `new_invoice_flow` | `'Invoice log record left as pending — use option 2 to send it manually.'` | `'Invoice log record left as pending — use option 3 to send it manually.'` |

---

## Data Model Changes

Two new optional fields added to each record in `invoices.json`:

| Field | Type | Description |
|---|---|---|
| `client_address` | string | Multi-line client address. Stored on new invoice creation. Empty string if absent (backwards-compatible). |
| `paid_at` | string (ISO datetime) or absent | UTC timestamp set when invoice is marked paid. Absent means unpaid. |

`status` gains a third value: `"paid"` (existing: `"pending"`, `"sent"`).

All changes are backwards-compatible — old records without the new fields behave as before.

---

## New Functions

### `view_history_flow(config)`

- Loads all records with status `"sent"` or `"paid"`.
- If none found, prints `'  No invoices found.'` and returns.
- Prints a six-column table: `#`, `Number`, `Client`, `Total`, `Date`, `Status`.
- Returns to the History submenu after display (no action taken).

### `mark_paid_flow(config)`

- Loads records with status `"sent"` (unpaid only).
- If none found, prints `'  No unpaid invoices found.'` and returns.
- Prints a five-column table (no `Status` column — all shown records are `"sent"`): `#`, `Number`, `Client`, `Total`, `Date`. This matches the column layout used by `resend_flow`.
- Prompts user to select by list number or invoice number.
- Confirms before marking: `Mark INV-001 (£300.00) as paid? [y/N]:`
- On confirm: sets `status = "paid"`, adds `paid_at` UTC timestamp, saves.

### `edit_settings_flow(config)`

- Re-uses existing `SETUP_SECTIONS` and `FIELD_PROMPTS` structure.
- Displays current values for each field (SMTP password masked as `****`).
- Prompts user to enter a new value or press Enter to keep existing.
- Saves on completion; returns updated config.
- **Env-var interaction:** if `INVOICE_SMTP_USER` or `INVOICE_SMTP_PASSWORD` are set, display those fields with a note `(overridden by environment variable — editing will save to config.json but the env var will still take precedence on next launch)`.

### `prompt_history_mode()`

- Prints the History submenu.
- Returns `"view"`, `"resend"`, `"mark_paid"`, or `"back"`.

---

## Modified Functions

### `new_invoice_flow(config)`

- `client_address` added to `log_data` as `'client_address': client['client_address']` so it is persisted in `invoices.json`. This field comes from `prompt_client_details()` which already collects it; it is currently in `invoice_data` but deliberately excluded from `log_data`.

### `build_invoice_data_from_record(record, config)`

- Reads `client_address` from the record via `record.get('client_address', '')` instead of always returning `""`.
- **Docstring update required:** the line `client_address is always '' (not stored in log).` must be removed from the docstring, as it will no longer be true.

### `resend_flow(config)`

- Table format (`#`, `Number`, `Client`, `Total`, `Date`) remains unchanged.
- Moved to be called from the History submenu instead of the main menu. No other changes.

### `main()`

- Main loop updated to handle new menu options: `"history"`, `"edit_settings"`.
- History option opens a nested loop over `prompt_history_mode()`, which dispatches to `view_history_flow`, `resend_flow`, or `mark_paid_flow`.
- `edit_settings_flow` result updates `config` in place so subsequent operations in the same session use the new values.

### `prompt_mode()`

- Updated option list and return values to match new main menu.
- Blank Enter default stays as `"new"` (option 1), unchanged from today.

---

## Out of Scope

- Custom VAT rates
- Recurring invoices
- Invoice editing / drafts
- Multi-currency support
- Logo/branding in PDF template
