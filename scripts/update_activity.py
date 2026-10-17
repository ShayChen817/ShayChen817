"""Publish aggregate counts only; never persist repository or activity details."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
USER = "ShayChen817"
PROFILE_TIMEZONE = timezone(timedelta(hours=8))


def current_commit_streak(now):
    """Count consecutive commit days in Shanghai; today may still be in progress."""
    today = now.astimezone(PROFILE_TIMEZONE).date()
    days = set()
    for page in range(1, 11):
        result = subprocess.run(
            ["gh", "api", "--method", "GET", "search/commits", "-f", f"q=author:{USER}",
             "-f", "sort=author-date", "-f", "order=desc", "-f", "per_page=100",
             "-f", f"page={page}", "--jq",
             "{total_count, incomplete_results, dates: [.items[].commit.author.date]}"],
            check=True, capture_output=True, encoding="utf-8",
        )
        data = json.loads(result.stdout)
        if data.get("incomplete_results"):
            raise RuntimeError("Incomplete commit history; retaining previous streak")
        for value in data["dates"]:
            day = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(PROFILE_TIMEZONE).date()
            if day <= today:
                days.add(day)
        cursor = today if today in days else today - timedelta(days=1)
        streak = 0
        while cursor in days:
            streak += 1
            cursor -= timedelta(days=1)
        # A fetched day older than the gap proves all newer days were searched.
        if (days and min(days) < cursor) or page * 100 >= data["total_count"]:
            return streak
    raise RuntimeError("Streak exceeds searchable history; refusing to publish a truncated count")


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


def activity_svg(metrics, mobile=False):
    cards = []
    for i, (name, count, accent) in enumerate(metrics):
        x, y = (12, 12 + i * 198) if mobile else (12 + (i % 2) * 600, 12 + (i // 2) * 198)
        fill = "#21181b" if i == 0 else "#15151b"
        border = "#695036" if i == 0 else "#303039"
        label_size = 36 if mobile else 17
        number_size = 84 if mobile else 68
        cards.append(f'<rect x="{x}" y="{y}" width="576" height="182" rx="20" fill="{fill}" stroke="{border}"/>'
                     f'<rect x="{x+28}" y="{y+30}" width="4" height="22" rx="2" fill="{accent}"/>'
                     f'<text x="{x+46}" y="{y+49}" fill="#dedbe3" font-size="{label_size}" letter-spacing="1">{name}</text>'
                     f'<text x="{x+28}" y="{y+136}" fill="{accent}" font-size="{number_size}" font-weight="700">{count:,}</text>'
                     f'<path d="M{x+28} {y+157}h520" stroke="{border}"/>')
    width, height = (600, 800) if mobile else (1200, 404)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
            '<title>Public and private GitHub activity across all time</title>'
            '<g font-family="Arial,Helvetica,sans-serif">' + ''.join(cards) + '</g></svg>\n')


def render(now):
    # Prevent a public-only or expired authorization from replacing combined counts.
    if search_count("issues", f"author:{USER} is:pr is:private") == 0:
        raise RuntimeError("Private PR access could not be verified; retaining previous counts")
    contributions = contribution_total(now)
    commits = search_count("commits", f"author:{USER}")
    prs = search_count("issues", f"author:{USER} is:pr")
    merged = search_count("issues", f"author:{USER} is:pr is:merged")
    streak = current_commit_streak(now)
    streak_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="194" viewBox="0 0 600 194" role="img">'
        '<title>Current consecutive commit days, public and private, Asia/Shanghai</title>'
        '<rect x="12" y="8" width="576" height="178" rx="20" fill="#21181b" stroke="#695036"/>'
        '<g font-family="Arial,Helvetica,sans-serif">'
        '<text x="40" y="47" fill="#dedbe3" font-size="32" letter-spacing="1">CURRENT COMMIT STREAK</text>'
        f'<text x="40" y="126" fill="#ffcc66" font-size="80" font-weight="700">{streak}</text>'
        '<text x="552" y="122" text-anchor="end" fill="#ffcc66" font-size="22">DAYS</text>'
        '<text x="40" y="162" fill="#c8c5cd" font-size="21">Public + private · Asia/Shanghai</text>'
        '</g></svg>\n'
    )
    metrics = [
        ("CONTRIBUTIONS", contributions, "#ffcc66"),
        ("COMMITS", commits, "#ffffff"),
        ("PULL REQUESTS OPENED", prs, "#ff5270"),
        ("PULL REQUESTS MERGED", merged, "#ff8a9d"),
    ]
    svg = activity_svg(metrics)
    mobile_svg = activity_svg(metrics, mobile=True)
    rows = [f'<p align="center"><sub>Public + private &nbsp; · &nbsp; All time &nbsp; · &nbsp; Updated {now:%Y-%m-%d} UTC</sub></p>',
            '', '<details>', '<summary>About these numbers</summary>', '',
            'Contributions follow GitHub’s calendar rules, including eligible code reviews and private activity. Commit and PR counts use GitHub search; the cards are not additive.', '',
            'Only aggregate counts visible to the authorized account are published.', '',
            'The commit streak counts consecutive author-date days in Asia/Shanghai. If there is no commit today yet, a streak ending yesterday stays active. PRs and reviews do not extend it.', '', '</details>']
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    pattern = r"<!-- ACTIVITY:START -->.*?<!-- ACTIVITY:END -->"
    if len(re.findall(pattern, readme, flags=re.S)) != 1:
        raise RuntimeError("Expected exactly one activity block")
    updated = re.sub(pattern, lambda _: "<!-- ACTIVITY:START -->\n" + "\n".join(rows) + "\n<!-- ACTIVITY:END -->", readme, flags=re.S)
    # A content-addressed URL prevents stale GitHub image caches after a refresh.
    version = hashlib.sha256((svg + mobile_svg).encode("utf-8")).hexdigest()[:12]
    updated, image_count = re.subn(
        r'src="assets/activity(?:-[a-f0-9]{12})?\.svg(?:\?v=[a-f0-9]+)?"',
        f'src="assets/activity-{version}.svg"', updated,
    )
    if image_count != 1:
        raise RuntimeError("Expected exactly one activity image")
    updated, source_count = re.subn(
        r'srcset="assets/activity-mobile(?:-[a-f0-9]{12})?\.svg"',
        f'srcset="assets/activity-mobile-{version}.svg"', updated,
    )
    if source_count != 1:
        raise RuntimeError("Expected exactly one mobile activity source")
    streak_version = hashlib.sha256(streak_svg.encode("utf-8")).hexdigest()[:12]
    updated, streak_count = re.subn(
        r'src="assets/streak(?:-[a-f0-9]{12})?\.svg"',
        f'src="assets/streak-{streak_version}.svg"', updated,
    )
    if streak_count != 1:
        raise RuntimeError("Expected exactly one streak image")
    (ROOT / "assets/activity.svg").write_text(svg, encoding="utf-8")
    image_path = ROOT / "assets" / f"activity-{version}.svg"
    image_path.write_text(svg, encoding="utf-8")
    mobile_path = ROOT / "assets" / f"activity-mobile-{version}.svg"
    mobile_path.write_text(mobile_svg, encoding="utf-8")
    streak_path = ROOT / "assets" / f"streak-{streak_version}.svg"
    streak_path.write_text(streak_svg, encoding="utf-8")
    # Keep versioned images so cached README pages and resized picture elements stay valid.
    readme_path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    render(datetime.now(timezone.utc))
