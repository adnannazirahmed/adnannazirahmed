import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_stats


class ContributionFeedTests(unittest.TestCase):
    def test_parses_github_calendar_counts_and_zero_days(self):
        markup = """
        <td data-date="2026-10-12" data-count="3"></td>
        <td data-date="2026-10-13" aria-label="No contributions on Oct 13"></td>
        <td data-date="2026-10-14" aria-label="2 contributions on Oct 14"></td>
        <td data-date="2026-10-15"><tool-tip>No contributions on Oct 15</tool-tip></td>
        """

        self.assertEqual(
            update_stats.parse_contributions(markup),
            [
                (date(2026, 10, 12), 3),
                (date(2026, 10, 13), 0),
                (date(2026, 10, 14), 2),
                (date(2026, 10, 15), 0),
            ],
        )

    def test_parses_current_github_calendar_tooltips_by_cell_id(self):
        markup = """
        <td data-date="2026-10-12" id="contribution-day-component-1-41" data-level="4"></td>
        <td data-date="2026-10-13" id="contribution-day-component-2-41" data-level="0"></td>
        <tool-tip for="contribution-day-component-1-41">56 contributions on October 12th.</tool-tip>
        <tool-tip for="contribution-day-component-2-41">No contributions on October 13th.</tool-tip>
        """

        self.assertEqual(
            update_stats.parse_contributions(markup),
            [(date(2026, 10, 12), 56), (date(2026, 10, 13), 0)],
        )

    def test_fills_missing_days_in_requested_feed_window(self):
        markup = '<td data-date="2026-10-12" data-count="3"></td>'

        self.assertEqual(
            update_stats.parse_contributions(
                markup, date(2026, 10, 12), date(2026, 10, 14)
            ),
            [
                (date(2026, 10, 12), 3),
                (date(2026, 10, 13), 0),
                (date(2026, 10, 14), 0),
            ],
        )

    def test_motd_reports_metrics_and_recent_months_without_svg(self):
        today = date.today()
        days = [
            (today - timedelta(days=2), 1),
            (today - timedelta(days=1), 2),
            (today, 0),
        ]
        motd = update_stats.render_motd(days)

        self.assertIn("CLOUD INFRASTRUCTURE + CYBERSECURITY", motd)
        self.assertIn("CURRENT STREAK   2 days (active through yesterday)", motd)
        self.assertIn("LONGEST STREAK   2 days", motd)
        self.assertIn("CONTRIBUTIONS    3 total / 2 active days", motd)
        self.assertIn("MONTHLY (last 12 months)", motd)
        self.assertIn(f"activity through {today.isoformat()}", motd)
        self.assertNotIn("<svg", motd)

    def test_readme_motd_replacement_preserves_surrounding_sections(self):
        readme = (
            "before\n" + update_stats.MOTD_START + "old block"
            + update_stats.MOTD_END + "\nafter"
        )

        updated = update_stats.replace_motd_section(readme, "new block")

        self.assertEqual(updated, "before\nnew block\nafter")

    def test_readme_motd_replacement_rejects_missing_or_duplicate_markers(self):
        with self.assertRaisesRegex(RuntimeError, "exactly one pair"):
            update_stats.replace_motd_section("no generated section", "new block")
        duplicate = update_stats.MOTD_START + update_stats.MOTD_END * 2
        with self.assertRaisesRegex(RuntimeError, "exactly one pair"):
            update_stats.replace_motd_section(duplicate, "new block")

    def test_current_day_activity_is_reported_as_live_and_singular(self):
        today = date.today()
        motd = update_stats.render_motd([(today, 1)])

        self.assertIn("CURRENT STREAK   1 day (active today)", motd)
        self.assertIn("LONGEST STREAK   1 day", motd)


if __name__ == "__main__":
    unittest.main()

