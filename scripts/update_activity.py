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


def activity_svg(metrics, mobile=False):
    width, height = (600, 420) if mobile else (1200, 210)
    parts = []
    colors = ("#eac16a", "#79b8ff", "#7bc99a", "#bda0ef")
    fills = ("#191810", "#111a24", "#111d18", "#1b1624")
    borders = ("#3d3523", "#24364b", "#263e31", "#3b2d4e")
    for i, (name, count) in enumerate(metrics):
        x = (i % 2) * 308 if mobile else i * 304
        y = (i // 2) * 218 if mobile else 0
        card_width = 292 if mobile else 288
        label_size = 34 if mobile else 26
        number_size = 70 if mobile else 64
        parts.append(f'<rect x="{x+1}" y="{y+1}" width="{card_width-2}" height="200" rx="10" fill="{fills[i]}" stroke="{borders[i]}" stroke-width="2"/>')
        parts.append(f'<text x="{x+22}" y="{y+99}" fill="{colors[i]}" font-size="{number_size}" font-weight="700" letter-spacing="-2">{count:,}</text>')
        parts.append(f'<text x="{x+22}" y="{y+158}" fill="#c9cdd3" font-size="{label_size}">{name}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
            '<title>Public and private GitHub activity across all time</title>'
            '<g font-family="Arial,Helvetica,sans-serif">' + ''.join(parts) + '</g></svg>\n')


def render(now):
    # Prevent a public-only or expired authorization from replacing combined counts.
    if search_count("issues", f"author:{USER} is:pr is:private") == 0:
        raise RuntimeError("Private PR access could not be verified; retaining previous counts")
    contributions = contribution_total(now)
    commits = search_count("commits", f"author:{USER}")
    prs = search_count("issues", f"author:{USER} is:pr")
    merged = search_count("issues", f"author:{USER} is:pr is:merged")
    metrics = [
        ("Contributions", contributions),
        ("Commits", commits),
        ("PRs opened", prs),
        ("PRs merged", merged),
    ]
    svg = activity_svg(metrics)
    mobile_svg = activity_svg(metrics, mobile=True)
    rows = [f'<p align="center"><sub>Public + private &nbsp; · &nbsp; All time &nbsp; · &nbsp; Updated {now:%Y-%m-%d} UTC</sub></p>',
            '', '<details>', '<summary>About these numbers</summary>', '',
            'Contributions follow GitHub’s calendar rules, including eligible code reviews and private activity. Commit and PR counts use GitHub search; the cards are not additive.', '',
            'Only aggregate counts visible to the authorized account are published.', '',
            '</details>']
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
    (ROOT / "assets/activity.svg").write_text(svg, encoding="utf-8")
    image_path = ROOT / "assets" / f"activity-{version}.svg"
    image_path.write_text(svg, encoding="utf-8")
    mobile_path = ROOT / "assets" / f"activity-mobile-{version}.svg"
    mobile_path.write_text(mobile_svg, encoding="utf-8")
    # Keep versioned images so cached README pages and resized picture elements stay valid.
    readme_path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    render(datetime.now(timezone.utc))
