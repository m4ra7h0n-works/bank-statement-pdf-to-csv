"""Extract two common transaction tables from multi-page text statements."""
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

__all__ = ["convert"]

DAY = r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4})"
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,13})\.[0-9]{2}"
MONEY = rf"(?:[+-]?{NUMBER}|\({NUMBER}\))"
HEADER = re.compile(r"^\s*Date\s+Description\s+(?:(?P<amount>Amount)|(?P<debit>Debit)\s+(?P<credit>Credit)\s+(?P<balance>Balance))\s*$", re.I)


def _money(value, optional=False):
    value = value.strip()
    if optional and value in ("", "-"):
        return Decimal(0)
    if not re.fullmatch(MONEY, value):
        raise ValueError("Require dot-decimal amounts with exactly two decimal places.")
    normalized = value.replace(",", "")
    if normalized.startswith("("):
        normalized = "-" + normalized[1:-1]
    if len(normalized.lstrip("+-").split(".")[0]) > 13:
        raise ValueError("Amount exceeds 13 integer digits.")
    return Decimal(normalized)


def _row(line, header):
    if header.group("amount"):
        match = re.fullmatch(rf"\s*({DAY})\s+(.+?)\s+({MONEY})\s*", line)
        if not match:
            raise ValueError("Expected date, description and signed amount.")
        day, description, amount = match.groups()
        amount = _money(amount)
    else:
        match = re.fullmatch(rf"\s*({DAY})\s+(.+?)\s+({MONEY}|-)\s+({MONEY}|-)\s+({MONEY})\s*", line)
        if match:
            day, description, debit, credit, balance = match.groups()
        else:
            # shortcut: a lone activity amount must align with its header; use the online version for irregular columns.
            match = re.fullmatch(rf"\s*({DAY})\s+(.+?)\s+(?P<activity>{MONEY})\s+(?P<balance>{MONEY})\s*", line)
            if not match:
                raise ValueError("Expected date, description, debit, credit and balance columns.")
            day, description, activity, balance = match.groups()
            columns = [key for key in ("debit", "credit")
                       if match.start("activity") == header.start(key)
                       or abs(match.end("activity") - header.end(key)) <= 1]
            balance_aligned = (match.start("balance") == header.start("balance")
                               or abs(match.end("balance") - header.end("balance")) <= 1)
            if len(columns) != 1 or not balance_aligned:
                raise ValueError("Blank debit/credit cells require amounts aligned under their column headers; otherwise use 0.00 or - placeholders.")
            debit, credit = (activity, "") if columns[0] == "debit" else ("", activity)
        debit, credit = _money(debit, optional=True), _money(credit, optional=True)
        _money(balance)
        if debit < 0 or credit < 0 or (debit and credit):
            raise ValueError("Debit and credit must be nonnegative, with at most one nonzero column per row.")
        amount = credit - debit
    day = date.fromisoformat(day).isoformat() if "-" in day else datetime.strptime(day, "%m/%d/%Y").date().isoformat()
    description = " ".join(description.split())
    if re.search(rf"(?<!\S){MONEY}(?!\S)", description):
        raise ValueError("Extra amount columns or standalone amounts in descriptions are unsupported.")
    if description.startswith(("=", "+", "-", "@")):
        description = "'" + description
    return [day, description, format(amount, ".2f")]


def convert(source, target):
    """Write date,description,amount CSV to a new path; return row count."""
    source, target = Path(source), Path(target)
    if source.suffix.lower() != ".pdf" or target.suffix.lower() != ".csv":
        raise ValueError("Use a .pdf input and .csv output.")
    if source.stat().st_size > 15 * 1024 * 1024:
        raise ValueError("PDF exceeds 15 MiB.")
    try:
        reader = PdfReader(source, strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported.")
        rows, header = [], None
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text(extraction_mode="layout")
            if not text or not text.strip():
                raise ValueError(f"Page {page_number}: no text found; scanned PDFs are unsupported.")
            lines = text.splitlines()
            first_header = next((index for index, line in enumerate(lines) if HEADER.fullmatch(line)), None)
            if first_header is not None:
                if any(re.match(rf"\s*{DAY}\s", line) for line in lines[:first_header]):
                    raise ValueError(f"Page {page_number}: transaction-like row before the table header.")
                lines = lines[first_header:]
            elif header is None:
                raise ValueError(f"Page {page_number}: require Date Description Amount or Date Description Debit Credit Balance header.")
            for line in lines:
                if not line.strip() or re.fullmatch(r"\s*Page\s+[0-9]+(?:\s+of\s+[0-9]+)?\s*", line, re.I):
                    continue
                found = HEADER.fullmatch(line)
                if found:
                    header = found
                    continue
                try:
                    rows.append(_row(line, header))
                except ValueError as exc:
                    raise ValueError(f"Page {page_number}: {exc}") from exc
    except PdfReadError as exc:
        raise ValueError("Cannot read PDF.") from exc
    if not rows:
        raise ValueError("No supported transactions found.")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "description", "amount"])
    writer.writerows(rows)
    with target.open("x", encoding="utf-8", newline="") as output:
        output.write(buffer.getvalue())
    return len(rows)
