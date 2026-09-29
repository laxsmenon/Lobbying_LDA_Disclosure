"""Build the research dataset from the raw downloads.

Outputs (in <processed_dir>):
    tax_issues.csv.gz      one row per TAX issue in a quarterly report (latest version),
                           with issue text, lobbyist counts by type, specificity measures,
                           in-house/outside, company key and make-or-buy strategy
    tax_spend.csv          estimated TAX spend per report (effort-weighted)
    tax_lobbyists.csv      one row per person lobbying on TAX: type, clients, disclosed posts
    tax_firms.csv          outside firms: tax clients, lobbyists, revolvers
    validation_sample.csv  300 disclosed posts to hand-code (classifier accuracy)
"""
import glob
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import classify as C

PERIOD_ORDER = {"first_quarter": 1, "second_quarter": 2, "third_quarter": 3, "fourth_quarter": 4}
QUARTERLY = r"^(Q[1-4]|[1-4][A-Z@]+)$"          # quarterly reports and their amendments / terminations

# ---- specificity dictionary ------------------------------------------------------------
LEGAL = re.compile(r"\b(sec(?:tion)?s?\.?\s*\d+[A-Za-z]?(?:\(\w+\))*|§+\s*\d+|I\.?R\.?C\.?|internal revenue code|"
                   r"H\.?\s?R\.?\s*\d+|S\.\s*\d+|H\.?\s?Res\.?\s*\d+|P\.?L\.?\s*\d+-\d+|public law|title\s+[IVX]+\b)", re.I)
BILL = r"\b(?:H\.?\s?R\.?\s*\d+|S\.\s*\d+|public law|P\.?L\.?\s*\d+-\d+)"
PROVISIONS = {
    "border adjustment / Blueprint": r"border[- ]adjust\w*|\bBAT\b|blueprint",
    "GILTI / FDII / BEAT": r"\bGILTI\b|\bFDII\b|\bBEAT\b|base erosion",
    "international (general)": r"international",
    "repatriation / territorial / FTC": r"repatriat\w*|territorial|subpart f|foreign tax credit|inversion",
    "corporate rate / reform": r"corporate (?:tax )?(?:rate|reform)|corporate integration",
    "interest deductibility": r"interest (?:expense )?deduct\w*",
    "depreciation / expensing": r"depreciat\w*|expensing|cost recovery|section 179\b",
    "pass-through / partnership": r"pass[- ]through|partnership|\bMLP\b|199A",
    "estate / death tax": r"estate tax|death tax",
    "charitable": r"charit\w*",
    "energy credits": r"solar|wind|renewable|energy (?:tax )?credit|biodiesel|\bPTC\b|\bITC\b|179d|\b45Q\b",
    "health taxes": r"cadillac|medical device|affordable care|\bACA\b|health insurance tax|\bHSA\b|individual mandate",
    "housing (LIHTC, historic)": r"LIHTC|low[- ]income housing|historic",
    "retirement / benefits": r"retirement|pension|401\(k\)|annuit\w*|employee benefit|ESOP",
    "municipal / tax-exempt bonds": r"municipal bond|tax[- ]exempt (?:bond|financ)|private activity bond|advance refunding",
    "state tax (Mobile Workforce, SALT)": r"mobile workforce|state income|internet (?:sales )?tax|marketplace fairness|state and local|\bSALT\b",
    "R&D / section 174": r"research (?:and development )?credit|\bR&D\b|section 174",
    "excise": r"excise",
    "carried interest": r"carried interest",
    "Tax Cuts and Jobs Act / H.R. 1": r"tax cuts and jobs act|\bH\.?\s?R\.?\s*1\b(?!\d)|\bTCJA\b",
    "Pillar Two / global minimum tax": r"pillar (?:two|2)|global minimum tax|\bGloBE\b|\bOECD\b",
    "corporate AMT (CAMT)": r"corporate alternative minimum|\bCAMT\b|book minimum tax",
}
BROAD = {"corporate rate / reform", "international (general)"}      # topics, but too broad to count as "specific"
GENERIC = r"tax reform|tax issues|tax policy|tax legislation"

_CO_STOP = (r"\b(the|inc|incorporated|llc|corp|corporation|co|company|companies|holdings?|group|ltd|lp|plc|na|usa|us|"
            r"and|of|various|subsidiaries|affiliates|fka|formerly|known|as)\b")


def company_key(n):
    n = re.sub(r"\(.*?\)", " ", str(n).lower())
    n = re.sub(r"\bon behalf of\b.*", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(re.sub(_CO_STOP, " ", n).split())


def _read(pattern, years):
    files = sorted(f for y in years for f in glob.glob(pattern.format(y=y)))
    if not files:
        raise FileNotFoundError(f"no files match {pattern} for years {list(years)} — run `download` first")
    print(f"  reading {len(files)} files: {[os.path.basename(f) for f in files]}")
    return pd.concat((pd.read_json(f, lines=True, dtype=False) for f in files), ignore_index=True).drop_duplicates()


def build(raw_dir, processed_dir, years):
    from ftfy import fix_text
    raw_dir, processed_dir = Path(raw_dir), Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    print("1/5 loading raw files")
    lob = _read(str(raw_dir / "{y}_*.jsonl"), years).dropna(subset=["last_name"])
    iss = _read(str(raw_dir / "issues" / "{y}_*.jsonl"), years)
    for df in (lob, iss):
        pnum = df.filing_period.map(PERIOD_ORDER).fillna(0).astype(int)
        df["q"] = df.filing_year * 10 + pnum
        df["quarter"] = df.filing_year.astype(str) + " Q" + pnum.astype(str)
    iss["description"] = iss.description.fillna("").map(fix_text).str.replace(r"\s+", " ", regex=True).str.strip()
    for c in ["income", "expenses"]:
        iss[c] = pd.to_numeric(iss[c], errors="coerce")

    print("2/5 quarterly reports: latest versions, in-house detection")
    rep = iss[iss.filing_type.str.match(QUARTERLY)].copy()
    latest = (rep.drop_duplicates("filing_uuid").sort_values("dt_posted")
                 .drop_duplicates(["registrant_id", "client_id", "q"], keep="last").filing_uuid)
    rep = rep[rep.filing_uuid.isin(set(latest))]
    flag = rep["client_self_select"] if "client_self_select" in rep else pd.Series([None] * len(rep), index=rep.index)
    rep["self_filer"] = [C.is_self_filer(r, c, a) for r, c, a in zip(rep.registrant_name, rep.client_name, flag)]
    rep["side"] = np.where(rep.self_filer, "in-house", "outside firm")
    rep["amount"] = np.where(rep.self_filer, rep.expenses, rep.income)

    print("3/5 classifying lobbyists (revolver status carried forward from first disclosure)")
    lob["person_key"] = [C.person_key(a, b, c) for a, b, c in zip(lob.first_name, lob.last_name, lob.suffix)]
    lob["pc"] = [C.classify_position(t, (r, c)) for t, r, c in zip(lob.covered_position, lob.registrant_name, lob.client_name)]
    kind = {"tax": "tax", "tax_member_staff": "tax", "other": "other"}
    disc = lob[lob.pc.isin(kind)].assign(k=lambda x: x.pc.map(kind))
    first = disc.groupby(["person_key", "k"]).q.min().unstack().reindex(columns=["tax", "other"])
    lob = lob.join(first.add_prefix("first_"), on="person_key")
    lob["is_tax_rev"] = lob.first_tax <= lob.q
    lob["is_rev"] = lob.is_tax_rev | (lob.first_other <= lob.q)
    lob["ptype"] = np.select([lob.is_tax_rev, lob.is_rev], ["tax revolver", "other revolver"], "career")
    positions = disc.groupby("person_key").covered_position.agg(lambda x: " | ".join(sorted(set(map(str, x))))[:400])

    print("4/5 building the TAX issue panel")
    tl = lob[(lob.issue_code == "TAX") & lob.filing_uuid.isin(set(rep.filing_uuid))] \
        .drop_duplicates(["filing_uuid", "activity_order", "person_key"])
    who = tl.groupby(["filing_uuid", "activity_order"]).agg(
        n_lob=("person_key", "nunique"), n_rev=("is_rev", "sum"), n_tax_rev=("is_tax_rev", "sum"),
        positions=("person_key", lambda x: " || ".join(positions.reindex(x).dropna())[:500]))
    T = rep[rep.issue_code == "TAX"].merge(who, on=["filing_uuid", "activity_order"], how="left")
    for c in ["n_lob", "n_rev", "n_tax_rev"]:
        T[c] = T[c].fillna(0).astype(int)
    T["group"] = np.select([T.n_tax_rev > 0, T.n_rev > 0], ["tax revolver", "other revolver"], "career only")
    T["n_words"] = T.description.str.split().str.len()
    for name, pat in PROVISIONS.items():
        T["p_" + name] = T.description.str.contains(pat, case=False, regex=True)
    T["n_prov"] = T[["p_" + n for n in PROVISIONS if n not in BROAD]].sum(axis=1)
    T["n_legal"] = T.description.map(lambda t: len(LEGAL.findall(t)))
    T["specific"] = (T.n_prov + T.n_legal) > 0
    T["names_bill"] = T.description.str.contains(BILL, case=False, regex=True)
    T["generic_only"] = T.description.str.contains(GENERIC, case=False) & (T.n_prov == 0) & (T.n_legal == 0)
    norm = T.description.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
    T["copied"] = T.assign(n=norm).groupby(["quarter", "n"]).client_name.transform("nunique") > 1
    T["company"] = T.client_name.map(company_key)
    s = T.groupby(["quarter", "company"]).side.agg(ih=lambda x: (x == "in-house").any(), out=lambda x: (x == "outside firm").any())
    s["strategy"] = np.select([s.ih & s.out, s.ih], ["both", "in-house only"], "outside only")
    T = T.join(s.strategy, on=["quarter", "company"])
    ge = T.government_entities.fillna("")
    T["contacted_treasury"] = ge.str.contains("Treasury", case=False)
    T["contacted_irs"] = ge.str.contains("Internal Revenue", case=False)
    T.to_csv(processed_dir / "tax_issues.csv.gz", index=False)

    print("5/5 spend estimates, lobbyists, firms, validation sample")
    slots = rep.groupby("filing_uuid").n_lobbyists.transform("sum")
    nact = rep.groupby("filing_uuid").issue_code.transform("size")
    rep["w"] = np.where(slots > 0, rep.n_lobbyists / slots.replace(0, np.nan), 1 / nact)
    rep["n_areas"] = rep.groupby("filing_uuid").issue_code.transform("nunique")
    M = (rep[rep.issue_code == "TAX"].groupby("filing_uuid")
           .agg(quarter=("quarter", "first"), side=("side", "first"), client=("client_name", "first"),
                registrant_id=("registrant_id", "first"), amount=("amount", "first"), w=("w", "sum"),
                n_areas=("n_areas", "first")))
    M["tax_spend"] = M.amount * M.w
    M = M.join(T.groupby("filing_uuid").group.agg(
        lambda g: "tax revolver" if (g == "tax revolver").any() else ("other revolver" if (g == "other revolver").any() else "career only")))
    M.to_csv(processed_dir / "tax_spend.csv")

    tq = tl.merge(rep[["filing_uuid", "side"]].drop_duplicates(), on="filing_uuid")
    last_type = tq.sort_values("q").groupby("person_key").ptype.last()
    people = tq.groupby("person_key").agg(first_name=("first_name", "first"), last_name=("last_name", "first"),
                                          clients=("client_name", "nunique"), firms=("registrant_id", "nunique"),
                                          inhouse=("side", lambda x: (x == "in-house").all()))
    people["type"] = last_type
    people["positions_disclosed"] = positions.reindex(people.index)
    people.to_csv(processed_dir / "tax_lobbyists.csv")

    o = tq[tq.side == "outside firm"]
    firm = o.groupby("registrant_name").agg(tax_clients=("client_name", "nunique"), lobbyists=("person_key", "nunique"))
    for g in ["tax revolver", "other revolver"]:
        firm[g + "s"] = o[o.person_key.map(last_type) == g].groupby("registrant_name").person_key.nunique()
    firm.fillna(0).astype(int).sort_values("tax_clients", ascending=False).to_csv(processed_dir / "tax_firms.csv")

    pool = lob[lob.pc != "none"].drop_duplicates("covered_position")
    sample = pool.sample(min(300, len(pool)), random_state=42)[["covered_position", "registrant_name", "client_name", "pc"]]
    sample = sample.rename(columns={"pc": "machine_code"}).assign(hand_code="")
    sample.to_csv(processed_dir / "validation_sample.csv", index=False)

    print(f"done: {len(T):,} TAX issues, {people.shape[0]:,} lobbyists, {len(firm):,} outside firms -> {processed_dir}")
    return T
