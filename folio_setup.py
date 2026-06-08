"""
Build a FolioClient and fetch all reference-data UUIDs needed at startup.
"""

import os
import logging
from dotenv import load_dotenv
from folioclient import FolioClient

load_dotenv()

log = logging.getLogger(__name__)


def build_client():
    return FolioClient(
        os.environ["FOLIO_OKAPI_URL"],
        os.environ["FOLIO_TENANT"],
        os.environ["FOLIO_USERNAME"],
        os.environ["FOLIO_PASSWORD"],
    )


def load_ref_data(fc):
    """
    Fetch all UUIDs needed for holdings creation and suppression.
    Returns a flat dict of logical-name -> UUID (or name->UUID sub-dict).
    Raises ValueError if any required name is not found in FOLIO.
    """
    ref = {}

    ref["holdings_type_electronic"] = _lookup_id(
        fc, "/holdings-types", "holdingsTypes", "Electronic"
    )
    ref["location_electronic"] = _lookup_id(fc, "/locations", "locations", "Electronic")
    ref["call_number_type_other"] = _lookup_id(
        fc, "/call-number-types", "callNumberTypes", "Other scheme"
    )
    ref["statistical_code_delete_h"] = _lookup_id(
        fc, "/statistical-codes", "statisticalCodes", "delete-h", field="code"
    )
    ref["holdings_source_folio"] = _lookup_id(
        fc, "/holdings-sources", "holdingsRecordsSources", "FOLIO"
    )
    ref["ea_relationship_resource"] = _lookup_id(
        fc,
        "/electronic-access-relationships",
        "electronicAccessRelationships",
        "Resource",
    )

    ref["ill_policies"] = _lookup_all(fc, "/ill-policies", "illPolicies")
    ref["holdings_note_types"] = _lookup_all(
        fc, "/holdings-note-types", "holdingsNoteTypes"
    )

    log.info("Reference data loaded successfully.")
    return ref


def _lookup_id(fc, path, key, value, field="name"):
    items = fc.folio_get(path, key=key, query_params={"limit": 200})
    for item in items:
        if item.get(field, "").strip() == value:
            return item["id"]
    raise ValueError(
        f"Required reference data not found in FOLIO: {field}={value!r} at {path}. "
        "Create it in FOLIO settings before running."
    )


def _lookup_all(fc, path, key):
    items = fc.folio_get(path, key=key, query_params={"limit": 200})
    return {item["name"].strip(): item["id"] for item in items}
