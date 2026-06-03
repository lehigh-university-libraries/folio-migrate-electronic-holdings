"""
Load and index the two coral-ID mapping worksheets.

Both sheets have duplicate "Holdings note type" column headers and a second
descriptor row, so we read by column position rather than by name.

Sheet 1 columns (row 0 = main header, row 1 = sub-header, rows 2+ = data):
  0  MARC 856$w
  1  E Resource coral identifier
  2  E Resource provider
  3  E Resource provider code
  4  E Resource access method
  5  E Resource access method code
  6  Call Number
  7  ILL Policy

Sheet 2 columns (same header structure):
  0  MARC 856$w
  1  MARC 856$x  (condition: "Unlimited" or "{856 $x} is not equal to 'Unlimited'")
  2  E Resource coral identifier
  3  E Resource provider
  4  E Resource provider code
  5  E Resource access method
  6  E Resource access method code
  7  Call Number
  8  ILL Policy
"""

import csv
import os
from dataclasses import dataclass


SHEET1_PATH = os.path.join(
    ".claudedoc", "Conversion Worksheet 2 - 1 - Mapping from 856$w.csv"
)
SHEET2_PATH = os.path.join(
    ".claudedoc", "Conversion Worksheet 2 - 2 - Mapping from 856$w.csv"
)

# Sentinel in sheet 1 access_method meaning "use the actual 856$x value"
_X_SENTINEL = "{856$x}"


@dataclass
class CollectionRow:
    coral_id: str
    call_number: str        # "Electronic book" or "Streaming video"
    provider: str
    provider_code: str
    access_method: str      # "" for streaming video
    access_method_code: str # "" for streaming video
    ill_policy: str         # "" when not specified

    @property
    def is_ebook(self):
        return self.call_number.strip().lower() == "electronic book"


def _read_csv_rows(path):
    """Return all rows (as lists) from a CSV, skipping the first two header rows."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows[2:]  # skip main header row and sub-header descriptor row


def _cell(row, index):
    """Return stripped cell value, or '' if index is out of range."""
    if index < len(row):
        return row[index].strip()
    return ""


def load_collections(sheet1_path=SHEET1_PATH, sheet2_path=SHEET2_PATH):
    """
    Returns a CollectionLookup loaded from both mapping worksheets.
    """
    sheet1 = {}
    for row in _read_csv_rows(sheet1_path):
        cid = _cell(row, 0)
        if not cid:
            continue
        sheet1[cid] = CollectionRow(
            coral_id=cid,
            call_number=_cell(row, 6),
            provider=_cell(row, 2),
            provider_code=_cell(row, 3),
            access_method=_cell(row, 4),
            access_method_code=_cell(row, 5),
            ill_policy=_cell(row, 7),
        )

    # Sheet 2: two rows per coral_id keyed by whether $x == "Unlimited"
    sheet2 = {}
    for row in _read_csv_rows(sheet2_path):
        cid = _cell(row, 0)
        if not cid:
            continue
        x_cond = _cell(row, 1)
        parsed = CollectionRow(
            coral_id=cid,
            call_number=_cell(row, 7),
            provider=_cell(row, 3),
            provider_code=_cell(row, 4),
            access_method=_cell(row, 5),
            access_method_code=_cell(row, 6),
            ill_policy=_cell(row, 8),
        )
        if cid not in sheet2:
            sheet2[cid] = {}
        if x_cond == "Unlimited":
            sheet2[cid]["Unlimited"] = parsed
        else:
            sheet2[cid]["not_unlimited"] = parsed

    return CollectionLookup(sheet1, sheet2)


class CollectionLookup:
    def __init__(self, sheet1, sheet2):
        self._sheet1 = sheet1
        self._sheet2 = sheet2

    def lookup(self, coral_id, x_value):
        """
        Return a CollectionRow for the given coral_id and 856$x value,
        or None if not found in either spreadsheet.

        Sheet 2 takes precedence for its four conditional coral IDs.
        For those IDs, the correct row is selected by whether x_value == "Unlimited".
        The non-Unlimited row's access_method is always set to the literal $x value.

        Two sheet-1 IDs (coral-175, coral-533) use "{856$x}" as a sentinel in
        access_method; that sentinel is replaced with x_value at lookup time.
        """
        if coral_id in self._sheet2:
            conditions = self._sheet2[coral_id]
            if x_value and x_value.strip() == "Unlimited":
                return conditions.get("Unlimited")
            row = conditions.get("not_unlimited")
            if row is not None:
                return CollectionRow(
                    coral_id=row.coral_id,
                    call_number=row.call_number,
                    provider=row.provider,
                    provider_code=row.provider_code,
                    access_method=x_value or "",
                    access_method_code=row.access_method_code,
                    ill_policy=row.ill_policy,
                )
            return None

        if coral_id in self._sheet1:
            row = self._sheet1[coral_id]
            if row.access_method == _X_SENTINEL:
                return CollectionRow(
                    coral_id=row.coral_id,
                    call_number=row.call_number,
                    provider=row.provider,
                    provider_code=row.provider_code,
                    access_method=x_value or "",
                    access_method_code=row.access_method_code,
                    ill_policy=row.ill_policy,
                )
            return row

        return None
