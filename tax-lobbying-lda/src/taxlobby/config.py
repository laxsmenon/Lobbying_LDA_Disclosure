"""Settings, read from config.yaml (all paths relative to the repository root)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "years": [2016, 2017, 2018, 2019],
    "raw_dir": "data/raw",
    "processed_dir": "data/processed",
    "results_dir": "results",
    "count_interns": False,
}


def parse_years(text):
    """'2016-2019' -> [2016, ..., 2019]; '2016,2018' -> [2016, 2018]."""
    years = []
    for part in str(text).replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-")
            years += list(range(int(a), int(b) + 1))
        elif part:
            years.append(int(part))
    return years


def load(path=None):
    cfg = dict(DEFAULTS)
    path = Path(path) if path else ROOT / "config.yaml"
    if path.exists():
        cfg.update(yaml.safe_load(path.read_text()) or {})
    if isinstance(cfg["years"], str):
        cfg["years"] = parse_years(cfg["years"])
    for k in ("raw_dir", "processed_dir", "results_dir"):
        p = Path(cfg[k])
        cfg[k] = p if p.is_absolute() else ROOT / p
    return cfg
