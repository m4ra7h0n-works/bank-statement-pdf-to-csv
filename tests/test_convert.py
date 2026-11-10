import csv
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from bank_statement_pdf_to_csv import convert
from pdf_fixture import make_pdf

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_bundled_example(tmp_path):
    target = tmp_path / "transactions.csv"
    assert convert(EXAMPLES / "statement.pdf", target) == 2
    assert target.read_bytes() == (EXAMPLES / "transactions.csv").read_bytes()


@pytest.mark.parametrize("lines,pages", [
    (["Date Description Amount", "2026-02-30 Sample -12.50"], 1),
    (["Date Description Amount", "2026-01-02 Sample -12.50", "wrapped description"], 1),
    (["Date Description Amount", "2026-01-02 Sample -12.50 100.00"], 1),
    (["Date Description Amount", "02/30/2026 Sample -12.50"], 1),
    (["Date Description Amount", "2026-01-02 Sample 12,50"], 1),
    (["Date Description Amount"], 1),
    (["2026-01-02 Sample -12.50"], 1),
    ([], 1),
])
def test_reject_unsupported_without_partial_csv(tmp_path, lines, pages):
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf(lines, pages))
    with pytest.raises(ValueError):
        convert(source, output)
    assert not output.exists()


def test_encrypted_pdf(tmp_path):
    writer = PdfWriter()
    writer.add_page(PdfReader(EXAMPLES / "statement.pdf").pages[0])
    writer.encrypt("synthetic-password")
    source = tmp_path / "encrypted.pdf"
    writer.write(source)
    with pytest.raises(ValueError, match="Encrypted"):
        convert(source, tmp_path / "output.csv")


def test_formula_text_and_no_overwrite(tmp_path):
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf(["Date Description Amount", "2026-01-02 =1+1 -12.50"]))
    convert(source, output)
    expected = "date,description,amount\n2026-01-02,'=1+1,-12.50\n"
    assert output.read_text() == expected
    with pytest.raises(FileExistsError):
        convert(source, output)
    assert output.read_text() == expected


def test_cli(tmp_path):
    output = tmp_path / "output.csv"
    result = subprocess.run([sys.executable, "-m", "bank_statement_pdf_to_csv", str(EXAMPLES / "statement.pdf"), str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    failed = subprocess.run([sys.executable, "-m", "bank_statement_pdf_to_csv", str(EXAMPLES / "statement.pdf"), str(output)], capture_output=True, text=True)
    assert failed.returncode == 2
    assert "Traceback" not in failed.stderr


@pytest.mark.parametrize("repeated_header", [False, True])
def test_multiple_pages_amount_layout(tmp_path, repeated_header):
    pages = [["Fictional checking statement", "Date Description Amount",
              "01/02/2026 Sample supplies (1,012.50)", "Page 1 of 2"],
             (["Fictional checking statement", "date description amount"] if repeated_header else []) +
             ["01/03/2026 Sample refund +100.00", "Page 2 of 2"]]
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf(pages))
    assert convert(source, output) == 2
    assert list(csv.DictReader(output.open())) == [
        dict(date="2026-01-02", description="Sample supplies", amount="-1012.50"),
        dict(date="2026-01-03", description="Sample refund", amount="100.00"),
    ]


def test_bundled_multiple_page_debit_credit_layout(tmp_path):
    output = tmp_path / "output.csv"
    assert convert(EXAMPLES / "debit-credit.pdf", output) == 3
    assert output.read_bytes() == (EXAMPLES / "debit-credit.csv").read_bytes()


def test_left_aligned_blank_debit_credit_cells(tmp_path):
    columns = "{:<12}{:<30}{:<12}{:<12}{}"
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf([
        columns.format("Date", "Description", "Debit", "Credit", "Balance"),
        columns.format("01/02/2026", "Sample debit", "12.50", "", "987.50"),
        columns.format("01/03/2026", "Sample credit", "", "100.00", "1087.50"),
    ]))
    assert convert(source, output) == 2
    assert [row["amount"] for row in csv.DictReader(output.open())] == ["-12.50", "100.00"]


@pytest.mark.parametrize("cells", [
    "12.50 - 987.50", "12.50 0.00 987.50", "- 12.50 1012.50", "0.00 12.50 1012.50",
])
def test_explicit_debit_credit_columns(tmp_path, cells):
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf(["Date Description Debit Credit Balance", f"2026-01-02 Sample {cells}"]))
    assert convert(source, output) == 1
    amount = next(csv.DictReader(output.open()))["amount"]
    assert amount == ("-12.50" if cells.startswith("12.50") else "12.50")


@pytest.mark.parametrize("row", [
    "2026-01-02 Sample -12.50 - 987.50", "2026-01-02 Sample 12.50 10.00 997.50",
    "2026-01-02 Sample 12.50 - bad", "2026-01-02 Sample 12.50 -",
    "2026-01-02 Sample 12.50 987.50", "2026-01-02 Sample 987.50",
])
def test_invalid_debit_credit_columns(tmp_path, row):
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf(["Date Description Debit Credit Balance", row]))
    with pytest.raises(ValueError):
        convert(source, output)
    assert not output.exists()


def test_reject_transaction_before_header(tmp_path):
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf(["2026-01-02 Sample 12.50", "Date Description Amount", "2026-01-03 Sample 1.00"]))
    with pytest.raises(ValueError, match="before the table header"):
        convert(source, output)
    assert not output.exists()


@pytest.mark.parametrize("last_page", [[], ["Date Description Amount", "2026-02-30 Sample 1.00"], ["unrecognized continuation"]])
def test_invalid_later_page_leaves_no_partial_csv(tmp_path, last_page):
    source, output = tmp_path / "statement.pdf", tmp_path / "output.csv"
    source.write_bytes(make_pdf([["Date Description Amount", "2026-01-02 Sample -12.50"], last_page]))
    with pytest.raises(ValueError, match="Page 2"):
        convert(source, output)
    assert not output.exists()
