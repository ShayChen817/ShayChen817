"""Render public GitHub search activity; no private repository data is published."""
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
USER = "ShayChen817"


def search(kind, query, sort, limit=5):
    result = subprocess.run(
        ["gh", "api", "--method", "GET", f"search/{kind}",
         "-f", f"q={query}", "-f", f"sort={sort}", "-f", "order=desc",
         "-f", f"per_page={limit}"],
        check=True, capture_output=True, encoding="utf-8",
    )
    data = json.loads(result.stdout)
    if data.get("incomplete_results"):
        raise RuntimeError("GitHub search returned incomplete results; retaining previous output")
    return data


def label(value, limit=88):
    value = value.splitlines()[0]
    if len(value) > limit:
        value = value[:limit - 1] + "…"
    return escape(value).replace("|", "&#124;").replace("[", "&#91;").replace("]", "&#93;").replace("`", "&#96;")


def render(now):
    since = (now - timedelta(days=365)).date().isoformat()
    commits = search("commits", f"author:{USER} is:public author-date:>={since}", "committer-date")
    prs = search("issues", f"author:{USER} is:pr is:public created:>={since}", "updated")
    merged = search("issues", f"author:{USER} is:pr is:public is:merged merged:>={since}", "updated", 1)
    cards = []
    for i, (name, count, accent) in enumerate([
        ("COMMITS", commits["total_count"], "#ffffff"),
        ("PULL REQUESTS OPENED", prs["total_count"], "#ff5270"),
        ("PULL REQUESTS MERGED", merged["total_count"], "#ffcc66"),
    ]):
        x = 16 + i * 394
        cards.append(f'<rect x="{x}" y="12" width="380" height="166" rx="16" fill="#15151b" stroke="#303039"/>'
                     f'<rect x="{x+24}" y="36" width="26" height="3" rx="1.5" fill="{accent}"/>'
                     f'<text x="{x+24}" y="104" fill="{accent}" font-size="54" font-weight="700">{count:,}</text>'
                     f'<text x="{x+24}" y="143" fill="#bcbcc9" font-size="13" letter-spacing="1.5">{name}</text>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="195" viewBox="0 0 1200 195" role="img">'
           '<title>Public GitHub activity over the past 365 days</title>'
           '<g font-family="Arial,Helvetica,sans-serif">' + ''.join(cards) + '</g></svg>\n')
    rows = ["### Pull requests", "", "| Status | Pull request | Repository |", "| :--- | :--- | :--- |"]
    for item in prs["items"]:
        status = "🟣 Merged" if item["pull_request"].get("merged_at") else ("🟢 Open" if item["state"] == "open" else "⚪ Closed")
        repo = item["repository_url"].split("/repos/", 1)[1]
        rows.append(f'| {status} | [{label(item["title"])}]({item["html_url"]}) | {label(repo)} |')
    if not prs["items"]:
        rows.append("| — | No public pull requests in this period. | — |")
    rows += ["", "### Latest commits", "", "| Commit | Change | Repository |", "| :--- | :--- | :--- |"]
    for item in commits["items"]:
        if item["repository"].get("private", False):
            raise RuntimeError("Unexpected private repository in public search")
        rows.append(f'| [`{item["sha"][:7]}`]({item["html_url"]}) | {label(item["commit"]["message"])} | {label(item["repository"]["full_name"])} |')
    if not commits["items"]:
        rows.append("| — | No indexed public commits in this period. | — |")
    rows += ["", f'<sub>Public activity · past 365 days · updated {now:%Y-%m-%d} UTC. Counts follow GitHub search indexing; private work is excluded. PRs are sorted by recent updates.</sub>']
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    pattern = r"<!-- ACTIVITY:START -->.*?<!-- ACTIVITY:END -->"
    if len(re.findall(pattern, readme, flags=re.S)) != 1:
        raise RuntimeError("Expected exactly one activity block")
    updated = re.sub(pattern, lambda _: "<!-- ACTIVITY:START -->\n" + "\n".join(rows) + "\n<!-- ACTIVITY:END -->", readme, flags=re.S)
    (ROOT / "assets/activity.svg").write_text(svg, encoding="utf-8")
    readme_path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    render(datetime.now(timezone.utc))
