"""Cases taken from real 2017 LDA filings. Run: pytest"""
import pytest

from taxlobby import classify as C


@pytest.mark.parametrize("text,own,expected", [
    ("Tax Counsel, Senate Finance Committee", (), "tax"),
    ("Staff, Joint Committee on Taxation", (), "tax"),
    ("Deputy Asst Secretary, Treasury", (), "tax"),
    ("Staff Dir., Ways&Means Subcom. on Select Reven.", (), "tax"),
    ("Chief of Staff, Sen. Jones", (), "other"),
    ("Senior Policy Advisor, Speaker John Boehner", (), "other"),
    ("Member of Congress (OH-15) 1993-2009", (), "other"),
    ("Senior Counsel, U.S. Securities & Exchange Commission", (), "other"),
    ("US Ambassador to Canada (2005-2009)", (), "other"),
    ("Professional Staff Member", (), "other"),
    ("2018: Intern, Senate Finance Cmte; 2019: Intern, House Ways and Means Cmte", (), "intern_only"),
    ("Vice President of Federal Affairs", (), "non_government"),               # current corporate job
    ("Director, Public Affairs and Government Relations", (), "non_government"),
    ("President and CEO, Representative of German Industry and Trade",
     ("REPRESENTATIVE OF GERMAN INDUSTRY AND TRADE",), "non_government"),        # own organisation's name
    ("Tax Director, Chubb", ("CHUBB INA HOLDINGS INC.",), "non_government"),
    ("N/A", (), "none"),
    (None, (), "none"),
])
def test_classify_position(text, own, expected):
    assert C.classify_position(text, own) == expected


def test_garbled_separators_are_repaired():
    t = "Staff Director, Senate Agriculture CommitteeÍ¾ Staff Director, Senate Finance Subcmte on Int'l Trade"
    assert C.classify_position(t) == "tax"


def test_members_named_skips_months():
    t = "LA/Comm Director, Rep. Jim Gibbons Aug 1997-Sep 2000; Policy Advisor, Majority Leader Boehner"
    assert C.members_named(t) == ["gibbons", "boehner"]


@pytest.mark.parametrize("registrant,client,expected", [
    ("TENABLE, INC.", "TENABLE INC", True),
    ("AT&T SERVICES, INC. AND ITS AFFILIATES", "AT&T SERVICES, INC.", True),
    ("AMERICAN BANKERS ASSOCIATION", "AMERICAN BANKERS ASSOCIATION", True),
    ("TIBER CREEK HEALTH STRATEGIES, INC.", "TIBER CREEK GROUP (ON BEHALF OF MERCK & CO INC)", False),
    ("CGCN GROUP, LLC", "AMERICAN INVESTMENT COUNCIL", False),
    ("MILLER & CHEVALIER, CHTD", "TOYOTA MOTOR NORTH AMERICA, INC.", False),
])
def test_is_self_filer(registrant, client, expected):
    assert C.is_self_filer(registrant, client) == expected


def test_person_key_ignores_case_and_punctuation():
    assert C.person_key("Jane", "Doe", None) == C.person_key("JANE", "DOE", "") == "doe|jane|"
