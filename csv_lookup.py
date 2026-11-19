"""
Load and index the two coral-ID mapping worksheets.

Both sheets have duplicate "Holdings note type" column headers and a second
descriptor row, so we read by column position rather than by name.  Columns
not listed below (platform, provider type, purchase method, DRM, etc.) are
intentionally ignored.

Sheet 1 columns (row 0 = main header, row 1 = sub-header, rows 2+ = data):
  0  MARC 856$w
  1  Copy number
  2  E Resource coral identifier
  3  Agreement UUID
  4  E Resource agreement name
  9  E Resource simultaneous users  ("{856$x}" sentinel = use the 856$x value)
  17 ILL Policy
  18 Call Number

Sheet 2 columns (same header structure; two rows per coral ID):
  0  MARC 856$w
  1  Copy number
  2  E Resource coral identifier
  3  Agreement UUID
  4  E Resource agreement name
  9  E Resource simultaneous users (condition: "{856 $x} doesn't contain
     'Unlimited'" or "Unlimited Users")
  14 ILL Policy
  15 Call Number
"""

import csv
from dataclasses import dataclass, replace

SHEET1_PATH = "Conversion Worksheet 3 - Mapping from 856$w.csv"
SHEET2_PATH = "Conversion Worksheet 3 - Special Mapping (spec. no. of users).csv"

# Sentinel in sheet 1 simultaneous-users column meaning "use the actual 856$x value"
_X_SENTINEL = "{856$x}"

# Sheet 2 condition cells for the "not Unlimited" row start with this
_X_CONDITION_PREFIX = "{856"


@dataclass
class CollectionRow:
    coral_id: str
    call_number: str  # e.g. "Electronic book" or "Streaming video"
    copy_number: str  # "" when not specified
    agreement_uuid: str
    agreement_name: str
    ill_policy: str  # "" when not specified
    simultaneous_users: str = ""  # only set from 856$x for sentinel/conditional rows


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
    sheet1_x_ids = set()
    for row in _read_csv_rows(sheet1_path):
        cid = _cell(row, 0)
        if not cid:
            continue
        sheet1[cid] = CollectionRow(
            coral_id=cid,
            call_number=_cell(row, 18),
            copy_number=_cell(row, 1),
            agreement_uuid=_cell(row, 3),
            agreement_name=_cell(row, 4),
            ill_policy=_cell(row, 17),
        )
        if _cell(row, 9) == _X_SENTINEL:
            sheet1_x_ids.add(cid)

    # Sheet 2: two rows per coral_id keyed by whether $x contains "Unlimited"
    sheet2 = {}
    for row in _read_csv_rows(sheet2_path):
        cid = _cell(row, 0)
        if not cid:
            continue
        users_cell = _cell(row, 9)
        is_conditional = users_cell.startswith(_X_CONDITION_PREFIX)
        parsed = CollectionRow(
            coral_id=cid,
            call_number=_cell(row, 15),
            copy_number=_cell(row, 1),
            agreement_uuid=_cell(row, 3),
            agreement_name=_cell(row, 4),
            ill_policy=_cell(row, 14),
            # Unlimited row keeps its literal cell value ("Unlimited Users");
            # the conditional row gets the $x value at lookup time.
            simultaneous_users="" if is_conditional else users_cell,
        )
        key = "not_unlimited" if is_conditional else "Unlimited"
        sheet2.setdefault(cid, {})[key] = parsed

    return CollectionLookup(sheet1, sheet1_x_ids, sheet2)


class CollectionLookup:
    def __init__(self, sheet1, sheet1_x_ids, sheet2):
        self._sheet1 = sheet1
        self._sheet1_x_ids = sheet1_x_ids
        self._sheet2 = sheet2

    def lookup(self, coral_id, x_value):
        """
        Return a CollectionRow for the given coral_id and 856$x value,
        or None if not found in either spreadsheet.

        Sheet 2 takes precedence for its conditional coral IDs.  For those IDs,
        the correct row is selected by whether x_value contains "Unlimited".
        The Unlimited row's simultaneous_users is the literal sheet value
        ("Unlimited Users"); the non-Unlimited row's is set to the $x value.

        Sheet-1 IDs whose simultaneous-users cell is the "{856$x}" sentinel
        (coral-175, coral-533) also get simultaneous_users set to the $x value.
        """
        x_value = (x_value or "").strip()

        if coral_id in self._sheet2:
            conditions = self._sheet2[coral_id]
            if "Unlimited" in x_value:
                return conditions.get("Unlimited")
            row = conditions.get("not_unlimited")
            if row is not None:
                return replace(row, simultaneous_users=x_value)
            return None

        if coral_id in self._sheet1:
            row = self._sheet1[coral_id]
            if coral_id in self._sheet1_x_ids:
                return replace(row, simultaneous_users=x_value)
            return row

        return None
