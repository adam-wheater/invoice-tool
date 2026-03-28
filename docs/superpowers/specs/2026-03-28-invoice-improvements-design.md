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

### History submenu (new)

```
1) View invoices
2) Resend invoice
3) Mark invoice as paid
0) Back
```

"Resend" moves from the main menu into the History submenu. The main menu gains "Edit settings" (option 4) and "History" (option 2); "Test SMTP" shifts from option 3 to option 5.

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
- Prints a table: `#`, `Number`, `Client`, `Total`, `Date`, `Status`.
- Returns to the History submenu after display (no action taken).

### `mark_paid_flow(config)`

- Loads records with status `"sent"` (unpaid only).
- Prints same table format as `view_history_flow`.
- Prompts user to select by list number or invoice number.
- Confirms before marking: `Mark INV-001 (£300.00) as paid? [y/N]:`
- On confirm: sets `status = "paid"`, adds `paid_at` UTC timestamp, saves.

### `edit_settings_flow(config)`

- Re-uses existing `SETUP_SECTIONS` and `FIELD_PROMPTS` structure.
- Displays current values for each field (SMTP password masked as `****`).
- Prompts user to enter a new value or press Enter to keep existing.
- Saves on completion; returns updated config.

### `prompt_history_mode()`

- Prints the History submenu.
- Returns `"view"`, `"resend"`, `"mark_paid"`, or `"back"`.

---

## Modified Functions

### `new_invoice_flow(config)`

- `client_address` added to `log_data` so it is persisted in `invoices.json`.

### `build_invoice_data_from_record(record, config)`

- Reads `client_address` from the record (falls back to `""` if absent) instead of always returning `""`.

### `main()`

- Main loop updated to handle new menu options: `"history"`, `"edit_settings"`.
- History option opens a nested loop over `prompt_history_mode()`.
- Resend (`resend_flow`) called from History submenu, not main menu.

### `prompt_mode()`

- Updated option list and return values to match new main menu.

---

## Out of Scope

- Custom VAT rates
- Recurring invoices
- Invoice editing / drafts
- Multi-currency support
- Logo/branding in PDF template
