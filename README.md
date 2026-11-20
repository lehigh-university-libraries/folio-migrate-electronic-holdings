# folio-migrate-electronic-holdings

One-time migration utility that converts MARC 856 fields into proper FOLIO Electronic holdings records.

## What it does

For every non-suppressed MARC bibliographic instance whose SRS record contains at least one `856$w` starting with `coral`:

1. **Suppresses existing holdings** and marks them with the a statistical code. Holdings that have an attached purchase order are suppressed but not marked with the code; they are logged separately in `po_holdings.log`. Electronic holdings that this migration already created for one of the instance's coral IDs (for example, from an earlier run with `--keep-856`) are left alone, so re-running a record does not change anything.
2. **Creates a new Electronic holdings record** for each unique Coral ID found in the 856 fields, populated from two mapping spreadsheets in the project root (see [Data sources](#data-sources)).
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
- Statistical code: see `STATISTICAL_CODE_DELETE_HOLDING` in `folio_setup.py`.
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
| `po_holdings.log` | Instance and holdings HRIDs that were suppressed without the statistical code because a purchase order is attached |
| `needs_rederivation.log` | Instance/SRS record ids whose 856 fields were stripped but instance re-derivation could not be confirmed — review and manually re-trigger via change-manager |

All four files are in append mode; each run adds to the existing content.

## Data sources

The two mapping spreadsheets (`Conversion Worksheet 3 - Mapping from 856$w.csv` and `Conversion Worksheet 3 - Special Mapping (spec. no. of users).csv`) live in the project root and are not committed to the repository. They map each Coral ID to the holdings field values (agreement UUID, agreement name, ILL policy, call number, copy number). Columns for platform, provider type, purchase method, vendor title ID, DRM, expiration date, and public performance rights are ignored.

The `EResource Simultaneous Users` note is written in only two cases:
- **Sheet-1 rows whose Simultaneous Users cell is `{856$x}`:** the note holds the `856$x` value. Other sheet-1 Simultaneous Users text is never written.
- **Special-mapping Coral IDs:** the row is picked by whether `856$x` contains `Unlimited`. If it does, the note is the literal `Unlimited Users`. If it doesn't, the note holds the `856$x` value.

This is handled automatically.
