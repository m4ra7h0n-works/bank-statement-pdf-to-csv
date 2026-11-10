# bank-statement-pdf-to-csv

Extract date, description and amount from multi-page text bank statements in two common table layouts.

## Install

Python 3.10 or newer. From this repository:

```sh
python -m venv .venv
# Activate .venv using your shell's activation command, then:
python -m pip install .
```

Runtime dependency: `pypdf` (no OCR or external PDF command required). You can also run directly from the repository after installing its dependencies.

## Usage

```sh
python -m bank_statement_pdf_to_csv examples/statement.pdf transactions.csv
```

The output path must be new. Existing files are never overwritten. All conversion runs locally; the CLI makes no network requests. Conversion/validation errors exit with code 2. Run `python -m bank_statement_pdf_to_csv --help` for arguments.

Importable API (returns the number of exported rows):

```python
from bank_statement_pdf_to_csv import convert

convert("examples/statement.pdf", "transactions.csv")
```

Files under `examples/` are entirely fictional. Expected output:

```csv
date,description,amount
2026-01-02,Sample supplies,-12.50
2026-01-03,Sample refund,100.00
```

## Capabilities and limits

- One unencrypted, text-based PDF, up to 15 MiB, with one account and any number of pages. Uses `pypdf` layout-preserving text extraction; it does not visually inspect or OCR pages. A page without extractable text stops the entire export.
- Two case-insensitive English headers are supported: `Date Description Amount` and `Date Description Debit Credit Balance`, with flexible whitespace. Repeated headers are accepted. Non-transaction text before the first header on each page is ignored; transaction-like rows there cause an error. A continuation page without a header must start with transaction rows and retain the preceding layout. `Page N` and `Page N of M` footers are ignored; other nonempty lines after the header must be transactions.
- Dates must be `YYYY-MM-DD` or US `MM/DD/YYYY` (month first), with a four-digit year; output dates are ISO. There is no date-order guessing. Each transaction occupies one line, with a nonempty description.
- Amounts require exactly two decimal places. Comma thousands groups, a leading sign, and parentheses for negative amounts are supported; currency symbols and decimal commas are rejected. In the Amount layout, negative means money out and positive means money in.
- In the Debit/Credit/Balance layout, debit and credit are nonnegative and at most one may be nonzero. Output amount is credit minus debit. Use `0.00` or `-` for an unused debit/credit cell, or leave it blank with both the activity amount and balance aligned under their headers (left or right edge). Ambiguous column positions stop export. A numeric balance is required but is neither exported nor reconciled.
- Wrapped descriptions, other headers, other footers, standalone monetary values in descriptions and invalid rows stop export before any CSV is created. The CLI does not detect multiple accounts or parse arbitrary statements. Compare every output row manually with the original. Formula-leading descriptions receive an apostrophe for spreadsheet safety.
- No OCR, balance reconciliation, editable preview, XLSX or missing-row report. The examples demonstrate supported layouts with fictional data, not verified compatibility with a specific bank.

The original [single-amount layout](examples/statement.txt) and PDF remain available. The fictional [two-page debit/credit layout](examples/debit-credit.txt), [PDF](examples/debit-credit.pdf) and [expected CSV](examples/debit-credit.csv) show repeated page headers, blank debit/credit cells and running balances. For example:

```text
Date        Description                          Debit      Credit       Balance
01/02/2026  Sample supplies                      12.50                    987.50
01/03/2026  Sample refund                                   100.00      1,087.50
```

## This CLI vs Online version

| Feature | This CLI | Online version |
| --- | --- | --- |
| PDF layout | Multiple pages; two documented text table layouts | Broader statement layouts; cross-page processing |
| Input | Text PDF | Text PDF and supported scans via local English Tesseract OCR |
| Output | Date, description, amount CSV | CSV or XLSX with Balance check sheet |
| Balance checks | No | Opening + activity vs closing; running-balance checks where available |
| Corrections | Edit source externally | Editable transaction preview |
| Failed pages and omitted rows | Unsupported input stops export | Failed-page / skipped-row review and failure-list CSV |

## Online version

[BankXL online](https://bankxl.pivlu.com/?utm_source=github&utm_medium=readme&utm_campaign=bank-statement-pdf-to-csv) is a separate online version by the same author, Zijian Xiao. The online version requires no local installation and adds a preview with editable rows and balance checks where source balances are available. OCR results and complex layouts still need checking; handwriting, blurred scans and decimal-comma amounts are unsupported.

Current online free allowance (product information dated November 10, 2026):

No sign-up or payment card is required for the browser allowance. Signing in provides a separate account allowance.

10 free pages with data per browser credential, plus a separate 10 per account, usable across PDFs with preview, corrections, balance checks where available, and XLSX/CSV downloads. Shared network limits apply: 30 free pages in a rolling 30 days across anonymous and account use, including a shared anonymous limit of 10 pages per network in 30 days. Clearing cookies does not renew that limit. Free uploads are limited to 10 attempts per credential/account and 30 per network per hour. Failed pages use no free pages. A PDF exceeding the remaining allowance returns the free portion; the preview and both export formats explicitly state Only includes the first N pages with data and list source pages. Remaining pages require one-time page credits.

The local MIT-licensed CLI has no online quota. Visiting the link is optional; uploaded online files are processed by the online service.

## Tests

```sh
python -m pip install ".[test]"
python -m pytest
```

## License

MIT. Copyright (c) 2026 Zijian Xiao. See [LICENSE](LICENSE).
