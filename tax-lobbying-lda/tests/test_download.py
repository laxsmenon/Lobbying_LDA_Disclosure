"""Flattening real API output, resumable download (offline), and the key prompt."""
import json
from pathlib import Path

from taxlobby import download as D

PAGE = json.loads((Path(__file__).parent / "fixtures" / "filings_2017q1_page.json").read_text())


def test_flatten_lobbyists_real_filing():
    rows = D.flatten_lobbyists(PAGE["results"][0])
    assert len(rows) == 10
    assert rows[2]["last_name"] == "GEDULDIG" and "Majority Whip" in rows[2]["covered_position"]
    assert rows[0]["issue_code"] == "TAX"


def test_flatten_issues_real_filing():
    rows = D.flatten_issues(PAGE["results"][0])
    assert rows[0]["description"].startswith("Tax issues affecting private equity")
    assert rows[0]["self_filer"] is False                       # CGCN lobbying for a client
    assert D.flatten_issues(PAGE["results"][1])[0]["self_filer"] is True   # association filing for itself


def test_download_offline_is_resumable(tmp_path, monkeypatch):
    calls = []
    def fake_get(session, url, params=None):
        calls.append(params)
        return {"count": 2, "next": None, "results": PAGE["results"]}
    monkeypatch.setattr(D, "get", fake_get)
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    D.download([2017], tmp_path, api_key="x", periods=["first_quarter"])
    assert (tmp_path / "2017_first_quarter.done").exists()
    assert len((tmp_path / "2017_first_quarter.jsonl").read_text().splitlines()) == 14
    assert len((tmp_path / "issues" / "2017_first_quarter.jsonl").read_text().splitlines()) == 3
    D.download([2017], tmp_path, api_key="x", periods=["first_quarter"])   # second run skips the finished quarter
    assert len(calls) == 1


def test_key_from_environment(monkeypatch):
    monkeypatch.setenv("LDA_API_KEY", "abc123")
    assert D.ask_api_key() == "abc123"


def test_key_prompt_hidden(monkeypatch):
    monkeypatch.delenv("LDA_API_KEY", raising=False)
    monkeypatch.setattr(D.getpass, "getpass", lambda prompt: "  typed-key  ")
    assert D.ask_api_key() == "typed-key"
