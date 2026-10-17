"""Offline checks for the public statistics generator."""
from datetime import datetime, timezone
import importlib.util
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "activity", Path(__file__).resolve().parents[1] / "scripts/update_activity.py"
)
activity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activity)


def calendar_response(total, restricted):
    return SimpleNamespace(stdout=json.dumps({"data": {"user": {
        "contributionsCollection": {
            "contributionCalendar": {"totalContributions": total},
            "restrictedContributionsCount": restricted,
        }
    }}}))


class ContributionTests(unittest.TestCase):
    def test_refresh_updates_both_responsive_images_with_identical_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            readme = root / "README.md"
            readme.write_text('<picture><source media="(max-width: 600px)" '
                              'srcset="assets/activity-mobile.svg" />'
                              '<img src="assets/activity.svg" /></picture>'
                              '<!-- ACTIVITY:START --><!-- ACTIVITY:END -->', encoding="utf-8")
            old_paths = []
            for total in (953, 954):
                with patch.object(activity, "ROOT", root), patch.object(
                    activity, "contribution_total", return_value=total
                ), patch.object(activity, "search_count", side_effect=[1, 680, 115, 111]):
                    activity.render(datetime(2026, 10, 18, tzinfo=timezone.utc))
                paths = [root / path for path in re.findall(
                    r'(?:src|srcset)="([^"]+)"', readme.read_text(encoding="utf-8"))]
                for path, viewbox in zip(paths, ("0 0 600 480", "0 0 1200 320")):
                    svg = ET.parse(path).getroot()
                    self.assertEqual(svg.attrib["viewBox"], viewbox)
                    numbers = [node.text for node in svg.iter() if node.attrib.get("font-weight") == "700"]
                    self.assertEqual(numbers, [str(total), "680", "115", "111"])
                for old_path in old_paths:
                    self.assertTrue(old_path.exists())
                old_paths = paths[:2]

    def test_history_has_disjoint_years_and_no_private_double_count(self):
        responses = [
            SimpleNamespace(stdout="2024-11-07T13:09:39Z"),
            calendar_response(3, 2), calendar_response(16, 3),
            calendar_response(953, 824),
        ]
        with patch.object(activity.subprocess, "run", side_effect=responses) as run:
            total = activity.contribution_total(datetime(2026, 10, 17, tzinfo=timezone.utc))
        self.assertEqual(total, 972)
        queries = [call.args[0] for call in run.call_args_list[1:]]
        self.assertIn("from=2024-01-01T00:00:00+00:00", queries[0])
        self.assertIn("to=2024-12-31T23:59:59+00:00", queries[0])
        self.assertIn("from=2025-01-01T00:00:00+00:00", queries[1])
        self.assertIn("to=2025-12-31T23:59:59+00:00", queries[1])
        self.assertIn("from=2026-01-01T00:00:00+00:00", queries[2])
        self.assertIn("to=2026-12-31T23:59:59+00:00", queries[2])

    def test_graphql_error_cannot_be_published_as_partial_history(self):
        responses = [SimpleNamespace(stdout="2024-11-07T13:09:39Z"),
                     calendar_response(3, 2),
                     SimpleNamespace(stdout='{"errors":[{"message":"test"}]}')]
        with patch.object(activity.subprocess, "run", side_effect=responses):
            with self.assertRaises(RuntimeError):
                activity.contribution_total(datetime(2026, 10, 17, tzinfo=timezone.utc))

    def test_new_year_retains_completed_year_and_queries_new_year_once(self):
        with patch.object(activity.subprocess, "run", side_effect=[
            SimpleNamespace(stdout="2024-11-07T13:09:39Z"),
            calendar_response(3, 2), calendar_response(0, 0),
        ]) as run:
            self.assertEqual(activity.contribution_total(
                datetime(2025, 1, 1, tzinfo=timezone.utc)), 3)
        self.assertEqual(run.call_count, 3)
        self.assertIn("to=2025-12-31T23:59:59+00:00", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
