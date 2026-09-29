# tax-lobbying-lda

A reproducible pipeline for **US tax lobbying disclosures**, built from the official
Lobbying Disclosure Act (LDA) filings at [lda.gov](https://lda.gov).

It downloads every quarterly lobbying report, identifies **revolving-door lobbyists**
(former government officials, including former tax-writing staff at Ways & Means,
Senate Finance, the Joint Committee on Taxation, Treasury and the IRS), separates
**in-house** from **outside-firm** lobbying, estimates **spending on tax**, and measures
how **specific** each disclosure is (bills, code sections, named provisions).

Developed for Paper 2 of the PhD thesis *The Complexity of Control* (Lakshmi Menon,
University College Dublin).

---

## Quick start

```bash
git clone https://github.com/<your-username>/tax-lobbying-lda.git
cd tax-lobbying-lda
pip install -e .                    # installs the `taxlobby` package and its dependencies

python -m taxlobby test             # checks the connection to lda.gov
python -m taxlobby download         # downloads the years in config.yaml (resumable)
python -m taxlobby build            # builds the research dataset
python -m taxlobby analyze          # tables, charts and results/summary.md
```

**API key.** `test` and `download` ask for your lda.gov API key in the terminal
(input is hidden). The key is used for that run only and is **never saved**.
Get one free at <https://lda.gov/api/register/>. Press Enter to continue without a
key (works, but about 8× slower). To avoid typing it, you can set the environment
variable `LDA_API_KEY` for your session.

**Years.** Set them in `config.yaml`, or per command: `python -m taxlobby download --years 2016-2019`.
A full year takes roughly 35–40 minutes with a key. If a download stops, run it again —
finished quarters are skipped and an interrupted quarter resumes from its last page.

## What you get

| File | Contents |
|---|---|
| `data/processed/tax_issues.csv.gz` | One row per TAX issue in a quarterly report: text, in-house/outside, lobbyist counts by type, specificity measures, provisions mentioned, agencies contacted, make-or-buy strategy |
| `data/processed/tax_spend.csv` | Estimated TAX spend per report |
| `data/processed/tax_lobbyists.csv` | Everyone who lobbied on TAX: type, number of clients, disclosed government posts |
| `data/processed/tax_firms.csv` | Outside lobbying firms: tax clients, lobbyists, revolvers |
| `data/processed/validation_sample.csv` | 300 disclosed posts for hand-coding classifier accuracy |
| `results/summary.md` | Key findings in plain language |
| `results/table_*.csv`, `results/fig_*.png` | Tables and charts |

## How it works

```
lda.gov API ──download──► data/raw/            (one JSON-lines file per quarter, lobbyists + issues)
                 build ──► data/processed/      (research dataset)
               analyze ──► results/             (tables, figures, summary)
```

**Revolvers.** The LDA requires each lobbyist's "covered official positions" held in the
previous 20 years to be disclosed — but only the first time they lobby for a given client.
Status is therefore assigned per person and carried forward from the quarter it was first
disclosed. Posts are classified as *tax* (tax-writing committees, JCT, Treasury/IRS, tax
counsel), *other* government posts, *internships* (excluded by default), or not
governmental (e.g. a lobbyist's current corporate job entered by mistake). See
`src/taxlobby/classify.py` and the test cases in `tests/`.

**In-house vs outside.** A report is in-house when the registrant and client are the same
organisation, matched on cleaned names (exact matching misses about 20% of in-house filers).

**Spend.** LDA reports one amount per report covering all issues. TAX spend is estimated by
the share of the report's lobbyists working on the TAX issue; reports where TAX is the only
issue give exact figures.

## Limitations

- Covered executive-branch officials are defined narrowly (mainly political appointees), so
  career Treasury and IRS staff are largely not observed.
- Revolver status is a lower bound unless earlier years are downloaded.
- Lobbyists are matched across firms by name.
- Disclosures are self-reported; the results are descriptive, not causal.

## Tests

```bash
pytest
```
The tests use real 2017 filings and cover the classifier, in-house detection, flattening
the API output, resumable downloads and the key prompt. They run offline.

## Optional: tax-committee members

List Ways & Means / Senate Finance members (column `last_name`) in
`config/tax_committee_members.csv` to code personal-office staff of those members
(e.g. "Legislative Director, Rep. Kevin Brady") as tax revolvers.

## Data and licence

- **Code:** MIT licence (`LICENSE`).
- **Derived data:** LDA filings are public records published by the US Congress. Released
  datasets built with this code are shared under CC BY 4.0.
- This repository does not redistribute LobbyView data; if you link to LobbyView, download it
  yourself and cite Kim (2018).

## Citation

See `CITATION.cff`, or cite as: Menon, L. (2026). *tax-lobbying-lda: a reproducible pipeline for
US tax lobbying disclosures* (v0.1.0) [software].
