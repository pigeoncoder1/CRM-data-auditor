from crm_auditor.duplicates import (
    band_for,
    normalize_company,
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_record,
    score_pair,
)


def contact(**fields):
    row = {"full_name": None, "email": None, "phone": None, "company": None}
    return normalize_record({**row, **fields})



def test_name_lastname_first_case_and_whitespace():
    assert normalize_name("Cook, Christopher") == "christopher cook"
    assert normalize_name("  CHRISTOPHER    cook ") == "christopher cook"


def test_name_nicknames():
    assert normalize_name("Charlie Harris") == normalize_name("Charles Harris")
    assert normalize_name("Smith, Jim") == normalize_name("James Smith")
    assert normalize_name("Vicky Ward") == "victoria ward"


def test_name_blank_or_placeholder():
    assert normalize_name(None) is None
    assert normalize_name("   ") is None
    assert normalize_name("N/A") is None


def test_email_split_lowercased():
    assert normalize_email("  PETER.Morris@Vertex.COM ") == ("peter.morris", "vertex.com")


def test_email_invalid_is_none():
    for bad in [None, "", "n/a", "test@test", "@brightwave.com", "john.smith@", "jane..doe@company.com"]:
        assert normalize_email(bad) is None, bad


def test_company_legal_suffixes_and_spacing():
    variants = ["Acme Inc", "ACME INCORPORATED", "acme inc.", "AcmeInc", "Acme, LLC", "Acme Co."]
    assert {normalize_company(v) for v in variants} == {"acme"}


def test_company_punctuation_and_ampersand():
    assert normalize_company("Quill & Ink Media.") == normalize_company("Quill and Ink Media")
    assert normalize_company("HARBORLINE FOODS") == normalize_company("Harborline Foods")


def test_company_glued_co_not_stripped():
    assert normalize_company("Tesco") == "tesco"


def test_phone_digits_and_formats_agree():
    assert normalize_phone("(0350) 305-6413") == "443503056413"
    assert normalize_phone("+44 350 305 6413") == "443503056413"


def test_phone_invalid_is_none():
    for bad in [None, "", "N/A", "call office", "555-CALL-NOW", "12345", "0000000000"]:
        assert normalize_phone(bad) is None, bad


def test_both_missing_is_not_a_match():
    a = contact(full_name="Alice Archer")
    b = contact(full_name="Zed Zimmerman")
    score, signals = score_pair(a, b)
    assert score == 0
    assert not any(s["fired"] for s in signals.values())


def test_shared_placeholders_are_not_a_match():
    junk = dict(email="n/a", phone="N/A", company="N/A")
    a = contact(full_name="Alice Archer", **junk)
    b = contact(full_name="Zed Zimmerman", **junk)
    score, signals = score_pair(a, b)
    assert score == 0
    for name in ("email_local", "email_domain", "company", "phone"):
        assert signals[name]["similarity"] is None and not signals[name]["fired"], name


def test_shared_dummy_phone_is_not_a_match():
    a = contact(full_name="Alice Archer", phone="0000000000")
    b = contact(full_name="Zed Zimmerman", phone="0000000000")
    assert score_pair(a, b)[1]["phone"]["fired"] is False


def test_coworkers_are_not_high():
    a = contact(full_name="James Smith", email="james.smith@acme.com", company="Acme Inc", phone="0207 946 0000")
    b = contact(full_name="Matthew Parker", email="matthew.parker@acme.com", company="ACME", phone="0207 946 0000")
    score, _ = score_pair(a, b)
    assert band_for(score) != "high"


def test_name_and_company_with_personal_email_is_high():
    a = contact(full_name="Victoria Ward", email="victoria.ward@blueanchor.com", company="Blue Anchor Shipping")
    b = contact(full_name="Vicky Ward", email="vward1987@gmail.com", company="Blue Anchor Shipping Ltd")
    score, signals = score_pair(a, b)
    assert band_for(score) == "high"
    assert signals["email_domain"]["fired"] is False
