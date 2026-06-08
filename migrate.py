"""
One-time migration: convert MARC 856 fields into FOLIO Electronic holdings records.

Usage:
  python migrate.py                          # process all qualifying records, resumable
  python migrate.py --single <instance-hrid> # process one instance by HRID
  python migrate.py --keep-856               # skip deleting 856 fields
  python migrate.py --dry-run                # log actions without making API writes
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

import folio_setup
import srs_utils
from csv_lookup import load_collections
from holdings_builder import build_holdings_record
from state_manager import StateManager

load_dotenv()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging():
    log_file = os.environ.get("LOG_FILE", "migration.log")
    handlers = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file, mode="a", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def _unmatched_log():
    return open(
        os.environ.get("UNMATCHED_LOG", "unmatched_coral.log"), "a", encoding="utf-8"
    )


def _po_log():
    return open(
        os.environ.get("PO_HOLDINGS_LOG", "po_holdings.log"), "a", encoding="utf-8"
    )


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Migrate FOLIO electronic holdings from 856 fields to holdings records."
    )
    p.add_argument(
        "--single",
        metavar="INSTANCE_HRID",
        help="Process a single instance identified by its HRID.",
    )
    p.add_argument(
        "--keep-856",
        action="store_true",
        default=False,
        help="Do not delete 856 fields after processing.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Log actions but make no API writes.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# FOLIO helpers
# ---------------------------------------------------------------------------


def _get_instance_by_hrid(fc, hrid):
    results = fc.folio_get(
        "/instance-storage/instances",
        key="instances",
        query_params={"query": f'hrid=="{hrid}"', "limit": 1},
    )
    if not results:
        raise SystemExit(f"No instance found with HRID {hrid!r}.")
    return results[0]


def _get_srs_for_instance(fc, instance_id):
    return fc.folio_get(
        f"/source-storage/records/{instance_id}/formatted",
        query_params={"idType": "INSTANCE"},
    )


def _holdings_for_instance(fc, instance_id):
    return fc.folio_get(
        "/holdings-storage/holdings",
        key="holdingsRecords",
        query_params={"query": f'instanceId=="{instance_id}"', "limit": 200},
    )


def _holdings_has_po(fc, holdings_id):
    """Return True if any order line is associated with this holdings record."""
    result = fc.folio_get(f"/orders/holding-summary/{holdings_id}")
    return result.get("totalRecords", 0) > 0


# Fields returned by GET /holdings-storage/holdings that are derived/read-only
# and must be stripped before PUT.
_HOLDINGS_PUT_STRIP = {"holdingsItems", "bareHoldingsItems"}


def _clean_holdings_for_put(holdings):
    return {k: v for k, v in holdings.items() if k not in _HOLDINGS_PUT_STRIP}


def _coral_holdings_exists(fc, instance_id, coral_id, ref_data):
    """
    Return True if an Electronic holdings record for this coral_id already exists
    on the instance (used for idempotency on resume).
    """
    ea_location_id = ref_data["location_electronic"]
    existing = fc.folio_get(
        "/holdings-storage/holdings",
        key="holdingsRecords",
        query_params={
            "query": (
                f'instanceId=="{instance_id}" '
                f'AND permanentLocationId=="{ea_location_id}"'
            ),
            "limit": 200,
        },
    )
    note_type_id = ref_data["holdings_note_types"].get(
        "E Resource coral identifier", ""
    )
    for h in existing:
        for note in h.get("notes", []):
            if (
                note.get("holdingsNoteTypeId") == note_type_id
                and note.get("note", "").strip() == coral_id
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Per-record logic
# ---------------------------------------------------------------------------


def process_source_record(
    fc, source_record, ref_data, collections, args, unmatched_fh, po_fh
):
    """
    Process one SRS source record.  Returns "processed" or "skipped".
    """
    parsed = srs_utils.get_parsed_content(source_record)

    if not srs_utils.has_coral_856(parsed):
        return "skipped"

    instance_id = source_record["externalIdsHolder"]["instanceId"]
    instance_hrid = source_record["externalIdsHolder"].get("instanceHrid", instance_id)

    # Belt-and-suspenders: confirm the instance itself is not suppressed
    instance = fc.folio_get(f"/instance-storage/instances/{instance_id}")
    if instance.get("discoverySuppress", False):
        log.debug("Skipping suppressed instance %s (%s)", instance_hrid, instance_id)
        return "skipped"

    if args.dry_run:
        log.info("[DRY-RUN] Would process instance %s (%s)", instance_hrid, instance_id)
        return "processed"

    # Step 1: Suppress existing holdings (skip any that have a PO)
    _suppress_existing_holdings(fc, instance_id, instance_hrid, ref_data, po_fh)

    # Step 2: Group 856s by coral ID and create new Electronic holdings
    groups = srs_utils.group_856_by_coral_id(parsed)
    for coral_id, group_fields in groups.items():
        x_value = srs_utils.get_subfield(group_fields[0], "x") or ""
        collection_row = collections.lookup(coral_id, x_value)

        if collection_row is None:
            log.warning(
                "Coral ID %r not in spreadsheets — instance %s", coral_id, instance_hrid
            )
            unmatched_fh.write(f"{instance_hrid}\t{coral_id}\n")
            unmatched_fh.flush()
            continue

        if _coral_holdings_exists(fc, instance_id, coral_id, ref_data):
            log.info(
                "Holdings for %s on %s already exists — skipping (resume?)",
                coral_id,
                instance_hrid,
            )
            continue

        holdings = build_holdings_record(
            instance_id, coral_id, group_fields, collection_row, ref_data
        )
        fc.folio_post("/holdings-storage/holdings", payload=holdings)
        log.info("Created holdings for %s on instance %s", coral_id, instance_hrid)

    # Step 3: Optionally remove 856 fields from the SRS record
    if not args.keep_856:
        updated = srs_utils.strip_coral_856_fields(source_record)
        srs_id = source_record["id"]
        fc.folio_put(f"/source-storage/records/{srs_id}", payload=updated)
        log.info(
            "Stripped 856 fields from SRS record %s (instance %s)",
            srs_id,
            instance_hrid,
        )

    return "processed"


def _suppress_existing_holdings(fc, instance_id, instance_hrid, ref_data, po_fh):
    delete_h_code = ref_data["statistical_code_delete_h"]
    existing = _holdings_for_instance(fc, instance_id)

    for holdings in existing:
        hid = holdings["id"]
        hhrid = holdings.get("hrid", hid)

        if _holdings_has_po(fc, hid):
            log.warning(
                "Holdings %s (%s) on instance %s has a PO — skipping suppression",
                hhrid,
                hid,
                instance_hrid,
            )
            po_fh.write(f"{instance_hrid}\t{hhrid}\n")
            po_fh.flush()
            continue

        codes = holdings.get("statisticalCodeIds", [])
        if delete_h_code not in codes:
            codes.append(delete_h_code)
        holdings["statisticalCodeIds"] = codes
        holdings["discoverySuppress"] = True
        fc.folio_put(
            f"/holdings-storage/holdings/{hid}",
            payload=_clean_holdings_for_put(holdings),
        )
        log.info("Suppressed holdings %s on instance %s", hhrid, instance_hrid)


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------


def process_single(fc, hrid, ref_data, collections, args):
    instance = _get_instance_by_hrid(fc, hrid)
    instance_id = instance["id"]
    source_record = _get_srs_for_instance(fc, instance_id)
    if source_record is None:
        log.warning("No SRS record found for instance %s (%s)", hrid, instance_id)
        return

    with _unmatched_log() as unmatched_fh, _po_log() as po_fh:
        result = process_source_record(
            fc, source_record, ref_data, collections, args, unmatched_fh, po_fh
        )
    log.info("--single result: %s for instance %s", result, hrid)


def process_all(fc, ref_data, collections, args):
    state = StateManager(os.environ.get("STATE_FILE", "migration_state.json"))
    if state.is_complete:
        log.info("Migration already marked complete. Delete state file to re-run.")
        return

    batch_size = int(os.environ.get("BATCH_SIZE", "100"))
    offset = state.resume_offset
    log.info("Starting from offset %d", offset)

    with _unmatched_log() as unmatched_fh, _po_log() as po_fh:
        while True:
            batch = fc.folio_get(
                "/source-storage/source-records",
                key="sourceRecords",
                query_params={
                    "recordType": "MARC_BIB",
                    "suppressFromDiscovery": "false",
                    "deleted": "false",
                    "orderBy": "order,ASC",
                    "limit": batch_size,
                    "offset": offset,
                },
            )
            if not batch:
                break

            processed = skipped = errors = 0
            for sr in batch:
                try:
                    result = process_source_record(
                        fc, sr, ref_data, collections, args, unmatched_fh, po_fh
                    )
                    if result == "processed":
                        processed += 1
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                    inst_id = sr.get("externalIdsHolder", {}).get("instanceId", "?")
                    log.exception("Error processing instance %s", inst_id)

            offset += len(batch)
            state.record_batch(offset, processed, skipped, errors)

            if len(batch) < batch_size:
                break

    state.mark_complete()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    setup_logging()
    args = parse_args()

    log.info("Loading CSV mapping worksheets...")
    collections = load_collections()

    log.info("Connecting to FOLIO and loading reference data...")
    fc = folio_setup.build_client()
    ref_data = folio_setup.load_ref_data(fc)

    if args.single:
        process_single(fc, args.single, ref_data, collections, args)
    else:
        process_all(fc, ref_data, collections, args)


if __name__ == "__main__":
    main()
