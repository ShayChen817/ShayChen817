"""Publish aggregate counts only; never persist repository or activity details."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
USER = "ShayChen817"


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
    since = (now - timedelta(days=365)).date().isoformat()
    # Prevent a public-only or expired authorization from replacing combined counts.
    if search_count("issues", f"author:{USER} is:pr is:private") == 0:
        raise RuntimeError("Private PR access could not be verified; retaining previous counts")
    commits = search_count("commits", f"author:{USER} author-date:>={since}")
    prs = search_count("issues", f"author:{USER} is:pr created:>={since}")
    merged = search_count("issues", f"author:{USER} is:pr is:merged merged:>={since}")
    cards = []
    for i, (name, count, accent) in enumerate([
        ("COMMITS", commits, "#ffffff"),
        ("PULL REQUESTS OPENED", prs, "#ff5270"),
        ("PULL REQUESTS MERGED", merged, "#ffcc66"),
    ]):
        x = 16 + i * 394
        cards.append(f'<rect x="{x}" y="12" width="380" height="166" rx="16" fill="#15151b" stroke="#303039"/>'
                     f'<rect x="{x+24}" y="36" width="26" height="3" rx="1.5" fill="{accent}"/>'
                     f'<text x="{x+24}" y="104" fill="{accent}" font-size="54" font-weight="700">{count:,}</text>'
                     f'<text x="{x+24}" y="143" fill="#bcbcc9" font-size="13" letter-spacing="1.5">{name}</text>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="195" viewBox="0 0 1200 195" role="img">'
           '<title>Public and private GitHub activity over the past 365 days</title>'
           '<g font-family="Arial,Helvetica,sans-serif">' + ''.join(cards) + '</g></svg>\n')
    rows = [f'<sub>Public + private · past 365 days · updated {now:%Y-%m-%d} UTC · counts only.</sub>',
            '<br /><sub>GitHub-indexed activity visible to the authorized account. Repository names and activity details are never published.</sub>']
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
