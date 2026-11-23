"""Holt Beitragskalender und Daten der Featured-Repos von der GitHub-GraphQL-API.

Schreibt data/contributions.json und data/repos.json. Läuft täglich in der
GitHub Action; lokal:  GH_TOKEN=$(gh auth token) python scripts/fetch_data.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from config import USER, FEATURED_REPOS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("GH_TOKEN oder GITHUB_TOKEN fehlt")


def graphql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        sys.exit(f"GraphQL-Fehler: {body['errors']}")
    return body["data"]


CAL = """query($login:String!){user(login:$login){contributionsCollection{
  contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""

REPO = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
  name description url stargazerCount forkCount pushedAt
  primaryLanguage{name color}
  languages(first:4,orderBy:{field:SIZE,direction:DESC}){nodes{name}}}}"""


def main() -> None:
    cal = graphql(CAL, {"login": USER})["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[{"date": d["date"], "count": d["contributionCount"]} for d in w["contributionDays"]]
             for w in cal["weeks"]]
    contrib = {
        "user": USER,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": cal["totalContributions"],
        "weeks": weeks,
    }

    repos = []
    for full in FEATURED_REPOS:
        owner, name = full.split("/")
        r = graphql(REPO, {"owner": owner, "name": name})["repository"]
        if r:
            repos.append(r)

    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    (data / "contributions.json").write_text(json.dumps(contrib, indent=1), encoding="utf-8")
    (data / "repos.json").write_text(json.dumps(repos, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{contrib['total']} Beiträge, {len(repos)} Repos gespeichert")


if __name__ == "__main__":
    main()
