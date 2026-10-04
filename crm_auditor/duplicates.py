"""
Fuzzy duplicate detection: normalize each contact once, generate candidate
pairs, score each pair from independent signals, keep the ones worth reviewing.
"""

import re
from dataclasses import dataclass
from itertools import combinations
from typing import Iterator

from rapidfuzz import fuzz

from .loader import Row
from .validation import validate_email, validate_phone

# Values that mean "nothing here". They are treated like blanks, so two rows that
# both say "N/A" never count as matching on that field.
PLACEHOLDERS = {"n/a", "na", "none", "null", "-", "--", "unknown", "tbd", "test"}


def _clean(value: str | None) -> str | None:
    if value is None or value.strip().lower() in PLACEHOLDERS | {""}:
        return None
    return value.strip()


# --- Normalization -----------------------------------------------------------

# nickname -> canonical first name
NICKNAMES = {
    "jim": "james", "jimmy": "james", "jamie": "james",
    "mike": "michael", "mikey": "michael",
    "rob": "robert", "robbie": "robert", "bob": "robert", "bobby": "robert",
    "will": "william", "bill": "william", "billy": "william", "liam": "william",
    "tom": "thomas", "tommy": "thomas",
    "joe": "joseph", "joey": "joseph",
    "charlie": "charles", "chuck": "charles",
    "ed": "edward", "eddie": "edward",
    "ben": "benjamin", "benny": "benjamin",
    "sam": "samuel", "sammy": "samuel",
    "matt": "matthew",
    "andy": "andrew", "drew": "andrew",
    "chris": "christopher",
    "nate": "nathan",
    "sally": "sarah",
    "vicky": "victoria", "vicki": "victoria", "tori": "victoria",
    "dave": "david",
    "dan": "daniel", "danny": "daniel",
    "alex": "alexander",
    "pete": "peter",
    "nick": "nicholas",
    "steve": "stephen",
    "tony": "anthony",
    "liz": "elizabeth", "beth": "elizabeth",
    "jen": "jennifer", "jenny": "jennifer",
    "kate": "katherine", "katie": "katherine",
}


def normalize_name(value: str | None) -> str | None:
    """'Cook,  CHRIS' -> 'christopher cook'."""
    name = _clean(value)
    if name is None:
        return None
    if "," in name:
        last, _, first = name.partition(",")
        name = f"{first} {last}"
    tokens = re.sub(r"[\W_]+", " ", name.lower().replace("'", "")).split()
    return " ".join(NICKNAMES.get(t, t) for t in tokens) or None


# Free-mail providers: a shared domain here says nothing about a shared employer.
PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com",
    "hotmail.co.uk", "outlook.com", "live.com", "msn.com", "aol.com",
    "icloud.com", "me.com", "protonmail.com", "proton.me", "gmx.com",
}


def normalize_email(value: str | None) -> tuple[str, str] | None:
    """Return (local_part, domain), lowercased, or None if missing/invalid."""
    check = validate_email(_clean(value))
    if not check.is_valid:
        return None
    local, _, domain = check.normalized.rpartition("@")
    return local, domain


def normalize_phone(value: str | None) -> str | None:
    """Digits only, in international form, or None if missing/invalid/placeholder."""
    check = validate_phone(_clean(value))
    if not check.is_valid:
        return None
    if re.fullmatch(r"(\d)\1*", re.sub(r"\D", "", value)):  # 0000000000 etc.
        return None
    return re.sub(r"\D", "", check.normalized)


LEGAL_SUFFIXES = {"inc", "incorporated", "co", "company", "ltd", "limited", "llc", "corp", "corporation", "plc"}
# Suffixes also stripped when glued on ("AcmeInc"). "co"/"company" are left out
# here because stripping them from e.g. "Tesco" or "Costco" would mangle the name.
_GLUED_SUFFIXES = ("incorporated", "inc", "limited", "ltd", "llc")


def normalize_company(value: str | None) -> str | None:
    """'ACME, Inc.' / 'Acme Incorporated' / 'AcmeInc' -> 'acme'.

    Spaces are removed in the result so spacing differences don't matter.
    """
    company = _clean(value)
    if company is None:
        return None
    tokens = re.sub(r"[\W_]+", " ", company.lower().replace("&", " and ")).split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    squashed = "".join(tokens)
    for suffix in _GLUED_SUFFIXES:
        if squashed.endswith(suffix) and len(squashed) - len(suffix) >= 3:
            squashed = squashed[: -len(suffix)]
            break
    return squashed or None


@dataclass
class Contact:
    row: Row
    name: str | None
    email: tuple[str, str] | None
    phone: str | None
    company: str | None


def normalize_record(row: Row) -> Contact:
    return Contact(
        row=row,
        name=normalize_name(row.get("full_name")),
        email=normalize_email(row.get("email")),
        phone=normalize_phone(row.get("phone")),
        company=normalize_company(row.get("company")),
    )


# --- Candidate generation ------------------------------------------------------

def candidate_pairs(contacts: list[Contact]) -> Iterator[tuple[int, int]]:
    """Index pairs to score. Right now that's every pair.

    All-pairs is O(n^2): fine for hundreds of rows, ~50M comparisons at 10k.
    To scale, swap this for blocking: bucket contacts by cheap keys (e.g.
    normalized company, the first 3 letters of the surname, email local part)
    and only yield pairs that share at least one bucket. Using several keys
    keeps recall up, since a pair only needs to agree on one of them. Nothing
    downstream needs to change.
    """
    return combinations(range(len(contacts)), 2)


# --- Scoring --------------------------------------------------------------------

# Max points each signal can add. Raw total is 135; the score is capped at 100.
#
# Name and email local part say who the *person* is, so they carry the weight.
# Company and domain say where they *work*. Coworkers share those, so together
# they top out at 30, well below the high band (70). Phone sits in between: a
# matching mobile is strong, but an office switchboard is shared, so company +
# domain + phone (55) still only reaches "medium".
#
# A full name match (50) plus a company match (20) reaches exactly 70 ("high")
# with no email help, which covers the "same person, personal Gmail" case.
WEIGHTS = {
    "name": 50,
    "email_local": 30,
    "company": 20,
    "email_domain": 10,
    "phone": 25,
}

# Fuzzy similarities (0-100) below RAMP_FLOOR earn nothing. Unrelated short
# strings routinely score 40-65 under rapidfuzz, so a straight linear mapping
# would let random noise add up. Points scale linearly from the floor to 100.
RAMP_FLOOR = 70
# A signal "fires" (strong evidence, worth calling out) at or above these.
FIRE_AT = {"name": 85, "email_local": 85, "company": 90}

BANDS = (("high", 70), ("medium", 50), ("low", 35))
MIN_SCORE = BANDS[-1][1]

MISSING_NOTE = "missing or invalid on at least one side"


def band_for(score: float) -> str | None:
    return next((name for name, floor in BANDS if score >= floor), None)


def _fuzzy_signal(name: str, a: str | None, b: str | None, scorer) -> dict:
    if a is None or b is None:
        return {"similarity": None, "points": 0.0, "max_points": WEIGHTS[name],
                "fired": False, "values": [a, b], "note": MISSING_NOTE}
    sim = scorer(a, b)
    points = WEIGHTS[name] * max(0.0, (sim - RAMP_FLOOR) / (100 - RAMP_FLOOR))
    return {"similarity": round(sim, 1), "points": round(points, 1),
            "max_points": WEIGHTS[name], "fired": sim >= FIRE_AT[name], "values": [a, b]}


def _exact_signal(name: str, a: str | None, b: str | None, note: str | None = None) -> dict:
    if a is None or b is None or note:
        return {"similarity": None, "points": 0.0, "max_points": WEIGHTS[name],
                "fired": False, "values": [a, b], "note": note or MISSING_NOTE}
    match = a == b
    return {"similarity": 100.0 if match else 0.0, "points": float(WEIGHTS[name]) if match else 0.0,
            "max_points": WEIGHTS[name], "fired": match, "values": [a, b]}


def score_pair(a: Contact, b: Contact) -> tuple[float, dict[str, dict]]:
    local_a, domain_a = a.email or (None, None)
    local_b, domain_b = b.email or (None, None)
    personal = {domain_a, domain_b} & PERSONAL_DOMAINS
    domain_note = f"personal domain ({', '.join(sorted(personal))}) is not employer evidence" if personal else None

    signals = {
        "name": _fuzzy_signal("name", a.name, b.name, fuzz.token_sort_ratio),
        "email_local": _fuzzy_signal("email_local", local_a, local_b, fuzz.ratio),
        "company": _fuzzy_signal("company", a.company, b.company, fuzz.ratio),
        "email_domain": _exact_signal("email_domain", domain_a, domain_b, domain_note),
        "phone": _exact_signal("phone", a.phone, b.phone),
    }
    score = min(100.0, sum(s["points"] for s in signals.values()))
    return round(score, 1), signals


def find_duplicates(rows: list[Row], min_score: float = MIN_SCORE) -> list[dict]:
    contacts = [normalize_record(row) for row in rows]
    pairs = []
    for i, j in candidate_pairs(contacts):
        score, signals = score_pair(contacts[i], contacts[j])
        if score < min_score:
            continue
        pairs.append({
            "score": score,
            "band": band_for(score),
            "fired_signals": [name for name, s in signals.items() if s["fired"]],
            "signals": signals,
            "record_a": contacts[i].row,
            "record_b": contacts[j].row,
        })
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs
