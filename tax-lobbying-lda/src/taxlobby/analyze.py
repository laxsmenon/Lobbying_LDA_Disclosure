"""Tables, figures and a plain-language summary from the processed dataset."""
from pathlib import Path

import numpy as np
import pandas as pd

GROUPS = ["career only", "other revolver", "tax revolver"]
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"   # colour-blind-checked palette
C3 = dict(zip(GROUPS, [BLUE, ORANGE, AQUA]))
C_SIDE = {"in-house": BLUE, "outside firm": ORANGE}
INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"


def _style(plt):
    plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.spines.top": False,
                         "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
                         "axes.titlelocation": "left", "legend.frameon": False})


def _lines(plt, tab, title, path, colors, ylim=None):
    fig, ax = plt.subplots(figsize=(max(7, 0.55 * len(tab) + 2.5), 3.6))
    x = np.arange(len(tab))
    for col in tab.columns:
        ax.plot(x, tab[col].values, marker="o", linewidth=2, markersize=6, color=colors[col], label=col,
                markeredgecolor=BG, markeredgewidth=1.5)
    top = (ylim or (0, min(1, tab.max().max() * 1.25 + .02)))[1]
    ends = sorted([[tab[c].iloc[-1], tab[c].iloc[-1]] for c in tab.columns if pd.notna(tab[c].iloc[-1])])
    for i in range(1, len(ends)):                         # spread end labels so they never overlap
        ends[i][1] = max(ends[i][1], ends[i - 1][1] + top * 0.06)
    for v, yl in ends:
        ax.annotate(f"{v:.0%}", (x[-1], v), xytext=(x[-1] + 0.08 * max(1, len(x) / 4), yl), textcoords="data",
                    va="center", color=INK2, fontsize=9)
    ax.set_xlim(-0.3, len(x) - 1 + 0.35 * max(1, len(x) / 4))
    ax.set_xticks(x, tab.index, rotation=45 if len(tab) > 6 else 0, ha="right" if len(tab) > 6 else "center")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylim(*(ylim or (0, min(1, tab.max().max() * 1.25 + .02))))
    ax.grid(axis="y", color=GRID); ax.set_axisbelow(True); ax.legend(fontsize=9, loc="best")
    ax.set_title(title); fig.tight_layout(); fig.savefig(path, dpi=200, bbox_inches="tight"); plt.close(fig)


def analyze(processed_dir, results_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    processed_dir, out = Path(processed_dir), Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    T = pd.read_csv(processed_dir / "tax_issues.csv.gz", low_memory=False)
    M = pd.read_csv(processed_dir / "tax_spend.csv")
    P = pd.read_csv(processed_dir / "tax_lobbyists.csv")
    F = pd.read_csv(processed_dir / "tax_firms.csv")
    T["rev"], T["trev"] = T.n_rev > 0, T.n_tax_rev > 0
    money = lambda x: f"${x / 1e6:,.1f}m"
    lines = ["# Tax lobbying: results summary", "",
             f"Quarters: {', '.join(sorted(T.quarter.unique()))} | TAX issues in quarterly reports: {len(T):,}", ""]

    # 1. revolver presence ----------------------------------------------------------
    rs = T.groupby(["quarter", "side"]).rev.mean().unstack().reindex(columns=["in-house", "outside firm"])
    rs.to_csv(out / "table_revolver_share_by_quarter.csv")
    _lines(plt, rs, "Share of TAX issues with a revolver on them", out / "fig_revolver_share.png", C_SIDE, (0, 1))
    side = T.groupby("side")[["rev", "trev"]].mean()
    lines += ["## Who lobbies", f"- Outside firms: **{side.loc['outside firm', 'rev']:.0%}** of TAX issues have a revolver "
              f"({side.loc['outside firm', 'trev']:.0%} a tax revolver); in-house: {side.loc['in-house', 'rev']:.0%} "
              f"({side.loc['in-house', 'trev']:.0%})."]
    port = P.groupby("type").clients.agg(["size", "mean", "median"]).round(1)
    port.to_csv(out / "table_lobbyist_portfolios.csv")
    srt = P.sort_values("clients", ascending=False)
    lines += [f"- {len(P):,} people lobbied on TAX; tax revolvers average **{port.loc['tax revolver', 'mean'] if 'tax revolver' in port.index else float('nan'):.1f}** "
              f"tax clients vs {port.loc['career', 'mean']:.1f} for career lobbyists.",
              f"- The top 10% of lobbyists hold {srt.clients.head(len(srt) // 10).sum() / srt.clients.sum():.0%} of lobbyist–client links; "
              f"{(srt.head(100).type != 'career').mean():.0%} of the 100 busiest are revolvers.",
              f"- Largest outside tax firms: " + "; ".join(f"{n} ({c} clients, {t} tax revolvers)" for n, c, t in
                                                           zip(F.registrant_name.head(5), F.tax_clients.head(5), F["tax revolvers"].head(5))), ""]

    # 2. money -----------------------------------------------------------------------
    sp = M.groupby(["quarter", "side"]).tax_spend.sum().unstack()
    sp.to_csv(out / "table_tax_spend_by_quarter.csv")
    o = M[M.side == "outside firm"]
    split = o.groupby("group").tax_spend.sum().reindex(GROUPS)
    split = split / split.sum()
    fees = o[(o.n_areas == 1) & (o.amount > 0)].groupby("group").amount.agg(["size", "median", "mean"]).reindex(GROUPS)
    fees.to_csv(out / "table_taxonly_fees.csv")
    p = o[o.amount > 0].copy(); p["l"] = np.log(p.amount)
    p["dm"] = p.l - p.groupby(["registrant_id", "quarter"]).l.transform("mean")
    mixed = p.groupby(["registrant_id", "quarter"]).group.transform("nunique") > 1
    g = p[mixed].groupby("group").dm.mean()
    prem = (np.exp(g - g.get("career only", 0)) - 1)
    lines += ["## Money (estimated TAX share of each report, weighted by lobbyists on the TAX issue)",
              f"- Estimated TAX lobbying spend: {money(M.tax_spend.sum())} "
              f"(in-house {money(M[M.side == 'in-house'].tax_spend.sum())}, outside {money(o.tax_spend.sum())}).",
              f"- Outside-firm TAX money: " + ", ".join(f"{k} {v:.0%}" for k, v in split.items()) + ".",
              f"- Median quarterly fee on TAX-only reports: " + ", ".join(f"{k} ${v / 1000:,.0f}k" for k, v in fees["median"].items() if pd.notna(v)) + ".",
              f"- Within the same firm and quarter, revolver accounts cost " + ", ".join(f"{k} {v:+.0%}" for k, v in prem.items() if k != "career only")
              + " vs career-only accounts.", ""]
    fig, ax = plt.subplots(figsize=(7, 1.9)); left = 0
    for grp, v in split.items():
        ax.barh(0, v, left=left, color=C3[grp], height=.55, edgecolor=BG, linewidth=2)
        ax.text(left + v / 2, 0, f"{v:.0%}", ha="center", va="center", color="white", fontweight="bold")
        ax.text(left + v / 2, -.45, grp, ha="center", va="top", color=INK2, fontsize=9); left += v
    ax.set_xlim(0, 1); ax.set_ylim(-.8, .4); ax.axis("off")
    ax.set_title(f"Where outside-firm TAX money goes (estimated {money(o.tax_spend.sum())})")
    fig.tight_layout(); fig.savefig(out / "fig_outside_money.png", dpi=200, bbox_inches="tight"); plt.close(fig)

    # 3. disclosure --------------------------------------------------------------------
    lang = T.groupby(["side", "group"]).agg(texts=("description", "size"), specific=("specific", "mean"),
                                            names_bill=("names_bill", "mean"), generic_only=("generic_only", "mean"),
                                            copied=("copied", "mean"), median_words=("n_words", "median")).round(3)
    lang.to_csv(out / "table_language.csv")
    nb = T[T.side == "outside firm"].groupby(["quarter", "group"]).names_bill.mean().unstack().reindex(columns=GROUPS)
    nb.to_csv(out / "table_names_bill_by_quarter.csv")
    _lines(plt, nb, "Outside firms: share of TAX texts naming a bill, by lobbyist type", out / "fig_names_bill.png", C3)
    lines += ["## Disclosure",
              f"- Only 'tax reform' (nothing more specific): {T.generic_only.mean():.0%} of TAX texts; "
              f"{T.copied.mean():.0%} reuse wording filed for another client in the same quarter.",
              "- Share naming a bill, outside firms by lobbyist type and quarter: see `table_names_bill_by_quarter.csv` / `fig_names_bill.png`.",
              "- In-house vs outside: " + "; ".join(f"{s} names a bill {v:.0%}" for s, v in T.groupby("side").names_bill.mean().items()), ""]

    # 4. what was lobbied ----------------------------------------------------------------
    pc = [c for c in T.columns if c.startswith("p_")]
    heat = T.groupby("quarter")[pc].mean().T.rename(index=lambda s: s[2:])
    heat = heat.loc[heat.mean(axis=1).sort_values(ascending=False).index]
    heat.to_csv(out / "table_provisions_by_quarter.csv")
    h = heat.head(14)
    fig, ax = plt.subplots(figsize=(max(7.5, .6 * h.shape[1] + 4), .36 * len(h) + 1.4))
    ax.imshow(h.values, aspect="auto", cmap="Blues", vmin=0)
    ax.set_xticks(range(h.shape[1]), h.columns, rotation=45 if h.shape[1] > 6 else 0, ha="right" if h.shape[1] > 6 else "center")
    ax.set_yticks(range(len(h)), h.index)
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            v = h.values[i, j]
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=8, color="white" if v > h.values.max() * .6 else INK)
    ax.spines[:].set_visible(False); ax.tick_params(length=0)
    ax.set_title("Share of TAX texts mentioning each item, by quarter")
    fig.tight_layout(); fig.savefig(out / "fig_provisions.png", dpi=200, bbox_inches="tight"); plt.close(fig)
    top = heat.max(axis=1).sort_values(ascending=False).head(5)
    lines += ["## What was lobbied", "- Peak share of TAX texts mentioning: " + "; ".join(f"{k} {v:.0%}" for k, v in top.items()), ""]

    # 5. make or buy ---------------------------------------------------------------------
    B = T[T.strategy == "both"]
    if len(B):
        mk = B.groupby(np.where(B.side == "in-house", "in-house", "outside: " + B.group)).agg(
            texts=("description", "size"), with_revolver=("rev", "mean"), specific=("specific", "mean"),
            names_bill=("names_bill", "mean"), median_words=("n_words", "median")).round(3)
        mk.to_csv(out / "table_make_or_buy.csv")
        lines += ["## Companies lobbying on TAX both in-house and through outside firms",
                  f"- {B.company.nunique():,} companies; their in-house texts name a specific provision or bill "
                  f"{B[B.side == 'in-house'].specific.mean():.0%} of the time vs {B[B.side == 'outside firm'].specific.mean():.0%} for their outside firms.", ""]

    lines += ["## Caveats",
              "- Revolver status comes from disclosures in the downloaded years only (a lower bound); download earlier years to improve it.",
              "- TAX spend is estimated: LDA reports one amount per report for all issues.",
              "- Descriptive associations, not causal effects."]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"results written to {out} — start with summary.md")
