"""
Helpers for reading and modifying MARC fields inside FOLIO SRS source records.

FOLIO stores parsed MARC as a dict with a "fields" list where each element is
a one-key dict mapping the tag string to the field data:
  {"856": {"ind1": "4", "ind2": "0", "subfields": [{"u": "http://..."}, ...]}}
"""

import copy
import json


def get_parsed_content(source_record):
    """
    Return parsedRecord.content as a dict, decoding from JSON string if needed.
    """
    content = source_record["parsedRecord"]["content"]
    if isinstance(content, str):
        return json.loads(content)
    return content


def get_marc_fields(parsed_content, tag):
    """Return all field dicts for the given MARC tag."""
    return [field[tag] for field in parsed_content.get("fields", []) if tag in field]


def get_subfield(field, code):
    """Return the first value of subfield $code, or None."""
    for sf in field.get("subfields", []):
        if code in sf:
            return sf[code]
    return None


def get_all_subfields(field, code):
    """Return all values of subfield $code."""
    return [sf[code] for sf in field.get("subfields", []) if code in sf]


def has_coral_856(parsed_content):
    """True if any 856 field has $w starting with 'coral' (case-insensitive)."""
    for f856 in get_marc_fields(parsed_content, "856"):
        w = get_subfield(f856, "w")
        if w and w.strip().lower().startswith("coral"):
            return True
    return False


def group_856_by_coral_id(parsed_content):
    """
    Return {coral_id: [field_dict, ...]} for all 856 fields whose $w starts
    with 'coral'.  Order of coral IDs and fields within each group is preserved.
    """
    groups = {}
    for f856 in get_marc_fields(parsed_content, "856"):
        w = get_subfield(f856, "w")
        if w and w.strip().lower().startswith("coral"):
            key = w.strip()
            groups.setdefault(key, []).append(f856)
    return groups


def _is_coral_856(field):
    """Return True if this is an 856 field with $w starting with 'coral'."""
    if "856" not in field:
        return False
    w = get_subfield(field["856"], "w")
    return bool(w and w.strip().lower().startswith("coral"))


def strip_coral_856_fields(source_record):
    """
    Return a deep copy of source_record with only the migrated 856 fields removed —
    those whose $w starts with 'coral'.  Other 856 fields are left in place.
    Only parsedRecord.content is updated; FOLIO regenerates the raw MARC from it.
    """
    record = copy.deepcopy(source_record)
    content = get_parsed_content(record)
    content["fields"] = [f for f in content["fields"] if not _is_coral_856(f)]
    record["parsedRecord"]["content"] = content
    return record
