"""Strict state vocabulary shared by ingestion and geographic read paths.

Names/aliases come from the existing dashboard boundary names, SPELLING map,
and historical CSV. Numeric/table residue is never stripped into a valid state.
Ladakh stays separate from Jammu and Kashmir (only the old map combines outlines).
"""

STATES = frozenset("""
ANDAMAN AND NICOBAR ISLANDS
ANDHRA PRADESH
ARUNACHAL PRADESH
ASSAM
BIHAR
CHANDIGARH
CHHATTISGARH
DADRA AND NAGAR HAVELI
DAMAN AND DIU
DELHI
GOA
GUJARAT
HARYANA
HIMACHAL PRADESH
JAMMU AND KASHMIR
JHARKHAND
KARNATAKA
KERALA
LADAKH
LAKSHADWEEP
MADHYA PRADESH
MAHARASHTRA
MANIPUR
MEGHALAYA
MIZORAM
NAGALAND
ODISHA
PUDUCHERRY
PUNJAB
RAJASTHAN
SIKKIM
TAMIL NADU
TELANGANA
TRIPURA
UTTAR PRADESH
UTTARAKHAND
WEST BENGAL
MULTI STATE
""".strip().splitlines())
ALIASES = {
    'CHHATISGARH': 'CHHATTISGARH',
    'A AND N ISLANDS': 'ANDAMAN AND NICOBAR ISLANDS',
    'D AND N HAVELI': 'DADRA AND NAGAR HAVELI',
    'PONDICHERRY': 'PUDUCHERRY', 'NCT OF DELHI': 'DELHI',
    'ORISSA': 'ODISHA', 'UTTARANCHAL': 'UTTARAKHAND',
    'ANDHRA PRADESH .': 'ANDHRA PRADESH',
}
UNRECOGNIZED = 'UNRECOGNIZED'

def canonical_state(value):
    if not isinstance(value, str):
        return None
    key = ' '.join(value.upper().replace('&', ' AND ').split())
    key = ALIASES.get(key, key)
    return key if key in STATES else None

def state_bucket(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return canonical_state(value) or UNRECOGNIZED
