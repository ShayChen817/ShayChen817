"""Publish aggregate counts only; never persist repository or activity details."""
from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
USER = "ShayChen817"


def contribution_total(now):
    """Sum disjoint calendar years, including GitHub's restricted contributions.

    Calendar totals already include reviews and private contribution counts.
    Never add restrictedContributionsCount or the PR/commit cards a second time.
    """
    result = subprocess.run(
        ["gh", "api", f"users/{USER}", "--jq", ".created_at"],
        check=True, capture_output=True, encoding="utf-8",
    )
    created = datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00"))
    now = now.astimezone(timezone.utc)
    query = """query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { totalContributions }
        }
      }
    }"""
    total = 0
    for year in range(created.year, now.year + 1):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        # Match GitHub's calendar-year selector, including today in the user's timezone.
        end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}",
             "-f", f"login={USER}", "-f", f"from={start.isoformat()}",
             "-f", f"to={end.isoformat()}"],
            check=True, capture_output=True, encoding="utf-8",
        )
        data = json.loads(result.stdout)
        if data.get("errors"):
            raise RuntimeError("Contribution query failed; retaining previous counts")
        count = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("Invalid contribution count")
        total += count
    return total


def search_count(kind, query):
    result = subprocess.run(
        ["gh", "api", "--method", "GET", f"search/{kind}",
         "-f", f"q={query}", "-f", "per_page=1", "--jq",
         "{total_count, incomplete_results}"],
        check=True, capture_output=True, encoding="utf-8",
    )
    data = json.loads(result.stdout)
    if data.get("incomplete_results"):
        raise RuntimeError("Incomplete search; retaining previous counts")
    count = data["total_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("Invalid activity count")
    return count


def render(now):
    # Prevent a public-only or expired authorization from replacing combined counts.
    if search_count("issues", f"author:{USER} is:pr is:private") == 0:
        raise RuntimeError("Private PR access could not be verified; retaining previous counts")
    contributions = contribution_total(now)
    commits = search_count("commits", f"author:{USER}")
    prs = search_count("issues", f"author:{USER} is:pr")
    merged = search_count("issues", f"author:{USER} is:pr is:merged")
    cards = []
    for i, (name, count, accent) in enumerate([
        ("CONTRIBUTIONS", contributions, "#ffcc66"),
        ("COMMITS", commits, "#ffffff"),
        ("PULL REQUESTS OPENED", prs, "#ff5270"),
        ("PULL REQUESTS MERGED", merged, "#ff8a9d"),
    ]):
        x, y = 12 + (i % 2) * 600, 12 + (i // 2) * 198
        fill = "#21181b" if i == 0 else "#15151b"
        border = "#695036" if i == 0 else "#303039"
        cards.append(f'<rect x="{x}" y="{y}" width="576" height="182" rx="20" fill="{fill}" stroke="{border}"/>'
                     f'<rect x="{x+28}" y="{y+30}" width="4" height="22" rx="2" fill="{accent}"/>'
                     f'<text x="{x+46}" y="{y+47}" fill="#c8c5cd" font-size="17" letter-spacing="1.5">{name}</text>'
                     f'<text x="{x+28}" y="{y+133}" fill="{accent}" font-size="68" font-weight="700">{count:,}</text>'
                     f'<path d="M{x+28} {y+157}h520" stroke="{border}"/>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="404" viewBox="0 0 1200 404" role="img">'
           '<title>Public and private GitHub activity across all time</title>'
           '<g font-family="Arial,Helvetica,sans-serif">' + ''.join(cards) + '</g></svg>\n')
    rows = [f'<p align="center"><sub>Public + private &nbsp; · &nbsp; All time &nbsp; · &nbsp; Updated {now:%Y-%m-%d} UTC</sub></p>',
            '', '<details>', '<summary>About these numbers</summary>', '',
            'Contributions follow GitHub’s calendar rules, including eligible code reviews and private activity. Commit and PR counts use GitHub search; the cards are not additive.', '',
            'Only aggregate counts visible to the authorized account are published.', '', '</details>']
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    pattern = r"<!-- ACTIVITY:START -->.*?<!-- ACTIVITY:END -->"
    if len(re.findall(pattern, readme, flags=re.S)) != 1:
        raise RuntimeError("Expected exactly one activity block")
    updated = re.sub(pattern, lambda _: "<!-- ACTIVITY:START -->\n" + "\n".join(rows) + "\n<!-- ACTIVITY:END -->", readme, flags=re.S)
    # A content-addressed URL prevents stale GitHub image caches after a refresh.
    version = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:12]
    updated, image_count = re.subn(
        r'src="assets/activity(?:-[a-f0-9]{12})?\.svg(?:\?v=[a-f0-9]+)?"',
        f'src="assets/activity-{version}.svg"', updated,
    )
    if image_count != 1:
        raise RuntimeError("Expected exactly one activity image")
    (ROOT / "assets/activity.svg").write_text(svg, encoding="utf-8")
    image_path = ROOT / "assets" / f"activity-{version}.svg"
    image_path.write_text(svg, encoding="utf-8")
    for old_image in (ROOT / "assets").glob("activity-*.svg"):
        if re.fullmatch(r"activity-[a-f0-9]{12}\.svg", old_image.name) and old_image != image_path:
            old_image.unlink()
    readme_path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    render(datetime.now(timezone.utc))
