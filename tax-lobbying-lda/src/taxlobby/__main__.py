"""Command line:  python -m taxlobby <command> [--years 2016-2019]

  test       check the connection to lda.gov (asks for your API key)
  download   download filings for the chosen years (asks for your API key; resumable)
  build      build the research dataset from the downloaded files
  analyze    tables, charts and results/summary.md
  all        download + build + analyze
"""
import argparse
import sys

from . import config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m taxlobby", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["test", "download", "build", "analyze", "all"])
    ap.add_argument("--years", help="e.g. 2016-2019 or 2016,2018 (default: config.yaml)")
    ap.add_argument("--config", help="path to a config.yaml (default: the one in the repository)")
    a = ap.parse_args(argv)

    cfg = config.load(a.config)
    if a.years:
        cfg["years"] = config.parse_years(a.years)
    from . import classify
    classify.COUNT_INTERNS = bool(cfg["count_interns"])
    print(f"years: {cfg['years']}")

    if a.command in ("test", "download", "all"):
        from .download import ask_api_key, download, test_connection
        key = ask_api_key()
        if a.command == "test":
            test_connection(key)
            return
        download(cfg["years"], cfg["raw_dir"], key)
    if a.command in ("build", "all"):
        from .build import build
        build(cfg["raw_dir"], cfg["processed_dir"], cfg["years"])
    if a.command in ("analyze", "all"):
        from .analyze import analyze
        analyze(cfg["processed_dir"], cfg["results_dir"])


if __name__ == "__main__":
    sys.exit(main())
