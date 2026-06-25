"""
Build a FOLIO holdings record dict from a group of 856 fields and a CollectionRow.

Multiple 856 fields sharing the same coral ID produce a single holdings record
with one electronicAccess entry per $u URI.
"""

import logging
import os

from folio_setup import (
    NOTE_CORAL_ID,
    NOTE_PACKAGE_NAME,
    NOTE_PROVIDER,
    NOTE_PROVIDER_CODE,
    NOTE_ACCESS_METHOD,
    NOTE_ACCESS_METHOD_CODE,
)
from srs_utils import get_subfield, get_all_subfields

log = logging.getLogger(__name__)


def build_holdings_record(instance_id, coral_id, fields_856, collection_row, ref_data):
    """
    Return a holdings record dict ready for POST /holdings-storage/holdings.

    instance_id      -- FOLIO instance UUID
    coral_id         -- the 856$w value (e.g. "coral-160")
    fields_856       -- list of parsed MARC 856 field dicts sharing this coral_id
    collection_row   -- CollectionRow from csv_lookup
    ref_data         -- UUID map from folio_setup.load_ref_data()
    """
    notes = _build_notes(coral_id, collection_row, ref_data)
    electronic_access = _build_electronic_access(fields_856, ref_data)
    ill_policy_id = _resolve_ill_policy(collection_row.ill_policy, ref_data)

    record = {
        "instanceId": instance_id,
        "holdingsTypeId": ref_data["holdings_type_electronic"],
        "permanentLocationId": ref_data["location_electronic"],
        "callNumberTypeId": ref_data["call_number_type_other"],
        "callNumber": collection_row.call_number,
        "copyNumber": collection_row.copy_number,
        "sourceId": ref_data["holdings_source_folio"],
        "discoverySuppress": False,
        "notes": notes,
        "electronicAccess": electronic_access,
    }

    if ill_policy_id:
        record["illPolicyId"] = ill_policy_id

    return record


def _build_notes(coral_id, row, ref_data):
    note_types = ref_data["holdings_note_types"]
    notes = []

    _add_note(notes, note_types, NOTE_CORAL_ID, coral_id)
    _add_note(notes, note_types, NOTE_PACKAGE_NAME, row.package_name)
    _add_note(notes, note_types, NOTE_PROVIDER, row.provider)
    _add_note(notes, note_types, NOTE_PROVIDER_CODE, row.provider_code)

    if row.is_ebook:
        if row.access_method:
            _add_note(notes, note_types, NOTE_ACCESS_METHOD, row.access_method)
        if row.access_method_code:
            _add_note(notes, note_types, NOTE_ACCESS_METHOD_CODE, row.access_method_code)

    return notes


def _add_note(notes, note_types, type_name, value):
    if not value:
        return
    note_type_id = note_types.get(type_name)
    if note_type_id is None:
        raise ValueError(
            f"Holdings note type not found in FOLIO: {type_name!r}. "
            "Create it in Settings > Inventory > Holdings note types."
        )
    notes.append({
        "holdingsNoteTypeId": note_type_id,
        "note": value,
        "staffOnly": False,
    })


_INCLUDE_PUBLIC_NOTE = os.environ.get("INCLUDE_856_PUBLIC_NOTE", "true").lower() == "true"


def _build_electronic_access(fields_856, ref_data):
    """One electronicAccess entry per 856 $u, across all fields in the group."""
    relationship_id = ref_data["ea_relationship_resource"]
    ea_list = []

    for f856 in fields_856:
        uris = get_all_subfields(f856, "u")
        public_note = get_subfield(f856, "z") or "" if _INCLUDE_PUBLIC_NOTE else ""

        for uri in uris:
            entry = {
                "uri": uri,
                "relationshipId": relationship_id,
            }
            if public_note:
                entry["publicNote"] = public_note
            ea_list.append(entry)

    return ea_list


def _resolve_ill_policy(policy_name, ref_data):
    if not policy_name:
        return None
    return ref_data["ill_policies"].get(policy_name)
