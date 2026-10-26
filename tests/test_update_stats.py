import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageChops

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

    def test_motd_alt_text_carries_live_metrics_and_profile_topics(self):
        today = date.today()
        days = [
            (today - timedelta(days=2), 1),
            (today - timedelta(days=1), 2),
            (today, 0),
        ]
        summary = update_stats.summarize_contributions(days)
        motd = update_stats.render_motd(summary)

        self.assertIn("cloud infrastructure", motd)
        self.assertIn("cybersecurity", motd)
        self.assertIn("current streak 2 days", motd)
        self.assertIn("longest streak 2 days", motd)
        self.assertIn("3 contributions over 2 active days", motd)
        self.assertIn(f"through {today.isoformat()}", motd)
        self.assertIn("cloud-security-motd.gif", motd)
        self.assertNotIn("<svg", motd)

    def test_animated_motd_gif_has_expected_frames_and_visible_animation(self):
        today = date.today()
        days = [(today - timedelta(days=1), 2), (today, 1)]
        summary = update_stats.summarize_contributions(days)
        output = Path(update_stats.ROOT) / "tests" / ".motd-test.gif"
        try:
            update_stats.render_motd_gif(summary, output)

            with Image.open(output) as gif:
                self.assertEqual(gif.format, "GIF")
                self.assertEqual(gif.n_frames, 12)
                self.assertEqual(gif.size, (960, 500))
                gif.seek(0)
                first_frame = gif.convert("RGB")
                gif.seek(6)
                later_frame = gif.convert("RGB")

            self.assertIsNotNone(ImageChops.difference(first_frame, later_frame).getbbox())
        finally:
            output.unlink(missing_ok=True)

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
        summary = update_stats.summarize_contributions([(today, 1)])
        motd = update_stats.render_motd(summary)

        self.assertIn("current streak 1 day", motd)
        self.assertIn("longest streak 1 day", motd)


if __name__ == "__main__":
    unittest.main()

