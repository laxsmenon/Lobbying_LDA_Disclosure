"""Classify lobbyists' disclosed government posts and detect in-house filers.

Every function here is pure (no network, no files except the optional
tax-committee member list) so it can be tested and reused.
"""
import re
from pathlib import Path

import pandas as pd

COUNT_INTERNS = False     # set True (or `count_interns: true` in config.yaml) to treat internships as revolving-door posts


# ------------------------------------------------ covered-position coding
EMPTY = re.compile(r"^\s*(n/?a|none|no|not applicable|-+|\.|0)?\s*$", re.I)

TAX = re.compile(
    r"ways\s*(and|&)\s*means|\bw\s*&\s*m\b|\bwm\b|"
    r"senate\s+finance|\bsfc\b|"
    r"(?<!financial services )finance\s+(comm|cmte|cte|committee)|"
    r"joint\s+(comm\w*|cmte)\.?\s+(on\s+)?tax|\bjct\b|"
    r"\btax|internal\s+revenue|\birs\b|"
    r"treasury|office\s+of\s+tax\s+policy|\botp\b|tax\s+legislative\s+counsel",
    re.I)

INTERN = re.compile(r"\b(intern|internship|fellow|fellowship|page)\b", re.I)

# Some filers wrongly put the lobbyist's CURRENT private job in the field
# (e.g. "Vice President, Representative of German Industry and Trade").
# A disclosure only counts if it contains a marker of federal government.
GOV = re.compile(
    r"\bsenator\b|\bcongress|\brep\b\.?|\bsen\b\.?|\bhouse\b|\bsenate\b|"
    r"committee|\bcmte\b|subcommittee|white\s+house|\bomb\b|department|"
    r"\bdept\b|treasury|\birs\b|internal\s+revenue|\bjct\b|ways\s+and\s+means|"
    r"administration|\bagency\b|secretary|commissioner|chief\s+of\s+staff|"
    r"legislative\s+(assistant|director|correspondent|counsel|aide)|"
    r"\bla\b|\bld\b|federal|executive\s+office|schedule\s+c|\bnec\b|\bcea\b|"
    r"\bcommission\b|\bto\s+(the\s+)?president\b|professional\s+staff|\bcong\b\.?|"
    r"\bleg\.?\s*(ass'?t|asst|ast|assistant|dir|director|counsel|corr)\b|\blegast\b|\bleg\.?\s*aide\b|"
    r"ways\s*(and|&)\s*means|\bw\s*&\s*m\b|\bsubcom\w*|\bcomm\b\.?|\bcmte\b|\bambassador\b|"
    r"state\s+department|department\s+of\s+state|\bsenate\b|\bu\.?s\.?\s+house\b|"
    r"\bspeaker\b|\bwhip\b|majority|minority|\bleader\b|\bcaucus\b|"
    r"republican\s+conference|democratic\s+(conference|caucus)|"
    r"member\s+of\s+congress|\bcongressional\b|\bcapitol\b",
    re.I)

# Corporate job titles that mention "federal/government affairs" are the
# lobbyist's CURRENT private job, not a government post: removed before GOV.
CORPORATE_TITLE = re.compile(
    r"\b((senior |executive |deputy |assistant |associate )?(vice[- ]president|vp|svp|evp|"
    r"director|manager|head|chief|counsel|representative|specialist|lead)"
    r"[,\s]+(of\s+|for\s+)?(\w+\s+){0,2}(federal|government|governmental|public|legislative|"
    r"regulatory|congressional)\s+(affairs|relations|policy)|"
    r"(federal|government|governmental|public|legislative|regulatory)\s+(affairs|relations)\s+"
    r"(director|manager|representative|specialist|counsel|lead))\b", re.I)


# Names of members a lobbyist worked for, e.g. "LD - Rep. Kevin Brady (TX-08)"
MEMBER = re.compile(
    r"(?:\bRep\b\.?|\bREP\b\.?|\bSen\b\.?|\bSEN\b\.?|Senator|SENATOR|"
    r"Congress(?:man|woman)|Representative|Speaker|"
    r"(?:Majority|Minority|Republican|Democratic)\s+(?:Leader|Whip))\s+"
    r"((?:[A-Z][A-Za-z'.-]+\s*){1,3})")

# OPTIONAL: tax_committee_members.csv with a column `last_name` listing
# members who sat on Ways & Means or Senate Finance in your period.
# If present, personal-office staff of those members are coded
# 'tax_member_staff' (e.g. LD to Rep. Kevin Brady, W&M chair).
TAX_MEMBERS_FILE = Path("config/tax_committee_members.csv")
TAX_MEMBERS = set()
if TAX_MEMBERS_FILE.exists():
    TAX_MEMBERS = set(pd.read_csv(TAX_MEMBERS_FILE).last_name
                      .str.lower().str.strip())


MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
          "sep", "oct", "nov", "dec"}


def members_named(text):
    """Surnames of members of Congress named in a position text."""
    if not isinstance(text, str):
        return []
    out = []
    for m in MEMBER.finditer(text):
        tokens = []
        for t in re.split(r"\s+", m.group(1).strip()):
            if t.strip(".,").lower()[:3] in MONTHS:          # "Gibbons Aug 1997"
                break
            if t and not re.match(r"^[A-Z]\.?$", t):          # drop initials
                tokens.append(t)
        if tokens:
            out.append(tokens[-1].strip(".,").lower())
    return out


def repair(t):
    """Fix garbled characters from the source (e.g. 'Í¾' for ';')."""
    try:
        from ftfy import fix_text
        t = fix_text(t)
    except ImportError:
        pass
    return (t.replace("Í¾", ";").replace("\u037e", ";").replace("â€‹", "")
             .replace("\u200b", ""))


def classify_position(text, own_names=()):
    """Return one of: none, non_government, intern_only, tax,
    tax_member_staff, other.  `own_names` = registrant and client names,
    removed first so a firm called 'Representative of ...' or
    'Treasury Wine' does not look like a government job."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "none"
    t = repair(str(text)).strip()
    if EMPTY.match(t):
        return "none"
    for name in own_names:
        if isinstance(name, str) and len(name) > 3:
            t = re.sub(re.escape(name), " ", t, flags=re.I)
    # an entry can hold several jobs separated by ; or , — drop pure
    # internships when deciding, unless COUNT_INTERNS
    parts = [p for p in re.split(r"[;\n]|,\s*(?=\d{4}|former|fmr)", t)
             if p.strip()]
    gov = [p for p in parts if GOV.search(CORPORATE_TITLE.sub(" ", p))]
    if not gov:
        return "non_government"
    real = gov if COUNT_INTERNS else [p for p in gov if not INTERN.search(p)]
    if not real:
        return "intern_only"
    if any(TAX.search(p) for p in real):
        return "tax"
    if TAX_MEMBERS and any(m in TAX_MEMBERS
                           for p in real for m in members_named(p)):
        return "tax_member_staff"
    return "other"


def person_key(first, last, suffix=""):
    """Name key for matching the same person across lobbying firms.
    The API lobbyist id is registrant-specific, so names are the only
    cross-firm link. Check common names by hand (see flags output)."""
    f = re.sub(r"[^a-z]", "", str(first or "").lower())
    l = re.sub(r"[^a-z]", "", str(last or "").lower())
    s = re.sub(r"[^a-z]", "", str(suffix or "").lower())
    s = "" if s in ("", "none", "nan") else s
    return f"{l}|{f}|{s}"


# ---- in-house (self-filer) detection -----------------------------------------
# The API's registrant and client names for an in-house filer often differ only
# in punctuation/suffixes ("TENABLE, INC." vs "TENABLE INC"), so an exact match
# misses ~20% of in-house filers. Compare cleaned names instead; a client filed
# "on behalf of" someone else is a subcontract, never in-house.
_SELF_STOP = (r"\b(the|inc|incorporated|llc|l l c|corp|corporation|co|company|companies|holdings?|group|"
              r"ltd|lp|l p|plc|na|usa|us|u s|and|of|various|subsidiaries|affiliates|its|fka|formerly|"
              r"known|as|dba|d b a|services?|pac)\b")


def _name_key(n):
    n = re.sub(r"\(.*?\)", " ", str(n).lower())
    n = re.sub(r"\b(formerly|f/k/a|fka|a subsidiary of|previously)\b.*", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(re.sub(_SELF_STOP, " ", n).split())


def is_self_filer(registrant_name, client_name, api_flag=None):
    """True if the registrant is lobbying for itself (in-house)."""
    if api_flag is True:
        return True
    if "behalf of" in str(client_name).lower():
        return False
    a, b = _name_key(registrant_name), _name_key(client_name)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted([a, b], key=len)
    return len(short) >= 8 and len(short.split()) >= 2 and f" {short} " in f" {long_} "
