# folio-migrate-electronic-holdings

One-time migration utility that converts MARC 856 fields into proper FOLIO Electronic holdings records.

## What it does

For every non-suppressed MARC bibliographic instance whose SRS record contains at least one `856$w` starting with `coral`:

1. **Suppresses existing holdings** and marks them with the a statistical code. Holdings that have an attached purchase order are suppressed but not marked with the code; they are logged separately in `po_holdings.log`.
2. **Creates a new Electronic holdings record** for each unique Coral ID found in the 856 fields, populated from two mapping spreadsheets in `.claudedoc/`.
3. **Removes the coral 856 fields** from the SRS record and triggers re-derivation of the FOLIO instance record via the change-manager API, so the instance's electronic access fields reflect the deletion (unless `--keep-856` is passed).

## Prerequisites

### Python

Python 3.10 or later. Install dependencies:

```
pip install -r requirements.txt
```

### FOLIO setup

The following must exist in your FOLIO instance before running:

**Holdings note types** (Settings → Inventory → Holdings note types) — see `NOTE_*` constants in `folio_setup.py` for exact names.

**Other reference data** — these are standard and should already exist:
- Holdings type: `Electronic`
- Location: `Electronic`
- Call number type: `Other scheme`
- Statistical code: see `STATISTICAL_CODE_DELETE_H` in `folio_setup.py`.
- Electronic access relationship: `Resource`
- Holdings source: `FOLIO`

## Configuration

Copy `.env.example` to `.env` and fill in your FOLIO connection details and any optional settings. The script reads configuration exclusively from environment variables (or the `.env` file).

```
cp .env.example .env
```

## Running

```
# Dry run on a single instance — no writes, shows what would happen
python migrate.py --dry-run --single <instance-hrid>

# Process a single instance for real
python migrate.py --single <instance-hrid>

# Process all qualifying records (resumable)
python migrate.py

# Process all records but leave 856 fields in place
python migrate.py --keep-856
```

The full run is resumable: if it is interrupted, re-running `python migrate.py` picks up from where it left off. Delete `migration_state.json` to start over from the beginning.

## Output files

| File | Contents |
|------|----------|
| `migration.log` | Full run log (append mode) |
| `unmatched_coral.log` | Instance HRIDs and Coral IDs that were not found in the mapping spreadsheets — review and handle manually |
| `po_holdings.log` | Instance and holdings HRIDs that were skipped because a purchase order is attached |

All three files are in append mode; each run adds to the existing content.

## Data sources

The two mapping spreadsheets (`Conversion Worksheet 2 - 1 - Mapping from 856$w.csv` and `Conversion Worksheet 2 - 2 - Mapping from 856$w.csv`) live in the project root and are not committed to the repository. They map each Coral ID to the holdings field values (provider, access method, ILL policy, call number type, etc.). Two Coral IDs have conditional logic based on the value of `856$x`; this is handled automatically.
