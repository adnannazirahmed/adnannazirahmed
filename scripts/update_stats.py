"""Refresh the profile's GitHub data and cloud-security MOTD section."""

from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = os.environ.get("PROFILE_GITHUB_USER", "adnannazirahmed")
TOKEN = os.environ.get("GH_TOKEN")
ROOT = Path(__file__).resolve().parents[1]
OVERVIEW_OUTPUT = ROOT / "assets" / "github-overview.svg"
README_PATH = ROOT / "README.md"
MOTD_START = "<!-- contribution-motd:start -->"
MOTD_END = "<!-- contribution-motd:end -->"
CONTRIBUTIONS_URL = f"https://github.com/users/{USERNAME}/contributions"


def github_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def collect_stats() -> tuple[int, int, int]:
    user = github_json(f"https://api.github.com/users/{USERNAME}")
    repos = github_json(
        f"https://api.github.com/users/{USERNAME}/repos"
        "?per_page=100&type=owner&sort=updated"
    )
    languages = {repo.get("language") for repo in repos if repo.get("language")}
    return user["public_repos"], user["followers"], len(languages)


def render_stats(repositories: int, followers: int, languages: int) -> str:
    cards = (
        ("PUBLIC REPOSITORIES", repositories, "#58a6ff"),
        ("FOLLOWERS", followers, "#3fb950"),
        ("LANGUAGES USED", languages, "#a371f7"),
    )
    card_markup = []
    for index, (label, value, color) in enumerate(cards):
        x = 40 + index * 385
        card_markup.append(
            f'''  <g transform="translate({x} 112)">
    <rect width="350" height="112" rx="9" fill="#0d1117" stroke="#30363d"/>
    <circle cx="24" cy="27" r="5" fill="{color}"/>
    <text x="42" y="32" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="12">{label}</text>
    <text x="22" y="82" fill="#e6ebf5" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="38" font-weight="700">{value}</text>
  </g>'''
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="270" viewBox="0 0 1200 270" role="img" aria-labelledby="title desc">
  <title id="title">Adnan Ahmed's GitHub statistics</title>
  <desc id="desc">Automatically updated public repository, follower, and language totals.</desc>
  <rect width="1200" height="270" rx="12" fill="#161b22" stroke="#30363d" stroke-width="2"/>
  <text x="40" y="43" fill="#3fb950" font-family="JetBrains Mono, Consolas, monospace" font-size="15">LIVE — GITHUB STATS</text>
  <text x="40" y="83" fill="#e6ebf5" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="30" font-weight="700">Public work at a glance</text>
{chr(10).join(card_markup)}
  <text x="40" y="252" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="12">Automatically checked every 12 hours via GitHub Actions</text>
</svg>
'''


class ContributionParser(HTMLParser):
    """Read daily counts from GitHub's accessible contribution calendar."""

    def __init__(self) -> None:
        super().__init__()
        self.days: dict[date, int] = {}
        self.day_ids: dict[str, date] = {}
        self.pending_cell: tuple[date, list[str]] | None = None
        self.pending_tooltip: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        day_value = attributes.get("data-date")
        if day_value:
            try:
                day = date.fromisoformat(day_value)
            except ValueError:
                day = None
            if day is not None:
                day_id = attributes.get("id")
                if day_id:
                    self.day_ids[day_id] = day
                count_value = attributes.get("data-count")
                label = attributes.get("aria-label") or attributes.get("title") or ""
                count = self._count_from_label(label)
                if count_value is not None and count_value.isdigit():
                    self.days[day] = int(count_value)
                elif count is not None:
                    self.days[day] = count
                else:
                    self.pending_cell = (day, [])

        # GitHub links accessible tooltips to cells by id in current markup.
        if tag == "tool-tip" and attributes.get("for"):
            self.pending_tooltip = (attributes["for"] or "", [])

    def handle_data(self, data: str) -> None:
        if self.pending_tooltip is not None:
            self.pending_tooltip[1].append(data)
        if self.pending_cell is not None:
            self.pending_cell[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tool-tip" and self.pending_tooltip is not None:
            day_id, parts = self.pending_tooltip
            day = self.day_ids.get(day_id)
            count = self._count_from_label(" ".join(parts))
            if day is not None and count is not None:
                self.days[day] = count
            self.pending_tooltip = None

        if tag == "td" and self.pending_cell is not None:
            day, parts = self.pending_cell
            count = self._count_from_label(" ".join(parts))
            if count is not None:
                self.days[day] = count
            self.pending_cell = None

    @staticmethod
    def _count_from_label(label: str) -> int | None:
        match = re.search(r"(\d+) contributions?", label, re.IGNORECASE)
        if match:
            return int(match.group(1))
        if re.search(r"no contributions", label, re.IGNORECASE):
            return 0
        return None


def parse_contributions(
    markup: str, start: date | None = None, end: date | None = None
) -> list[tuple[date, int]]:
    parser = ContributionParser()
    parser.feed(markup)
    if not parser.days:
        raise RuntimeError("GitHub contributions page contains no daily data")
    if start is not None and end is not None:
        return [
            (day, parser.days.get(day, 0))
            for day in (
                start + timedelta(days=offset)
                for offset in range((end - start).days + 1)
            )
        ]
    return sorted(parser.days.items())


def render_motd(days: list[tuple[date, int]]) -> str:
    """Render a compact, text-only cloud and cybersecurity profile welcome."""
    if not days:
        raise RuntimeError("Cannot render the contribution MOTD without daily data")

    total = sum(count for _, count in days)
    active_days = sum(count > 0 for _, count in days)
    best_day = max(count for _, count in days)
    average = total / active_days if active_days else 0

    current_days = days
    if days[-1][0] == date.today() and days[-1][1] == 0:
        current_days = days[:-1]
    current_streak = 0
    for _, count in reversed(current_days):
        if count == 0:
            break
        current_streak += 1

    longest_streak = 0
    running_streak = 0
    running_start = days[0][0]
    longest_start = days[0][0]
    longest_end = days[0][0]
    for day, count in days:
        if count > 0:
            if running_streak == 0:
                running_start = day
            running_streak += 1
            if running_streak > longest_streak:
                longest_streak = running_streak
                longest_start = running_start
                longest_end = day
        else:
            running_streak = 0

    monthly: OrderedDict[tuple[int, int], int] = OrderedDict()
    for day, count in days:
        key = (day.year, day.month)
        monthly[key] = monthly.get(key, 0) + count
    recent_months = list(monthly.items())[-12:]

    month_rows: list[str] = []
    for offset in range(0, len(recent_months), 6):
        group = recent_months[offset : offset + 6]
        labels = " ".join(f"{datetime(year, month, 1):%b}".upper().rjust(4) for (year, month), _ in group)
        values = " ".join(f"{value:>4}" for _, value in group)
        month_rows.extend((f"  {labels}", f"  {values}"))

    if current_streak and days[-1][0] == date.today() and days[-1][1] > 0:
        current_note = "active today"
    elif current_streak:
        current_note = "active through yesterday"
    else:
        current_note = "ready for the next contribution"
    current_unit = "day" if current_streak == 1 else "days"
    longest_unit = "day" if longest_streak == 1 else "days"
    longest_range = (
        f"{longest_start.strftime('%b')} {longest_start.day}"
        f"-{longest_end.strftime('%b')} {longest_end.day}"
        if longest_streak
        else "no active days yet"
    )
    latest_day = days[-1][0]

    lines = [
        MOTD_START,
        f"### `{USERNAME}@github:~$ motd --cloud-security`",
        "",
        "```text",
        "ADNAN AHMED / CLOUD INFRASTRUCTURE + CYBERSECURITY",
        "AWS / AZURE / IAM / PRACTICAL DEFENSE",
        "",
        f"CURRENT STREAK   {current_streak} {current_unit} ({current_note})",
        f"LONGEST STREAK   {longest_streak} {longest_unit} ({longest_range})",
        f"CONTRIBUTIONS    {total} total / {active_days} active days",
        f"BEST DAY         {best_day} / AVG {average:.1f} per active day",
        "MONTHLY (last 12 months)",
        *month_rows,
        "",
        f"activity through {latest_day.isoformat()} / refreshes every 12 hours",
        "```",
        MOTD_END,
    ]
    return "\n".join(lines)


def replace_motd_section(readme: str, section: str) -> str:
    """Replace exactly one generated block while preserving the rest of README."""
    if readme.count(MOTD_START) != 1 or readme.count(MOTD_END) != 1:
        raise RuntimeError("README must contain exactly one pair of MOTD markers")
    start = readme.index(MOTD_START)
    end = readme.index(MOTD_END)
    if start >= end:
        raise RuntimeError("README MOTD markers are out of order")
    end += len(MOTD_END)
    return readme[:start] + section + readme[end:]


def refresh_contributions() -> None:
    today = date.today()
    start = today - timedelta(days=364)
    counts: dict[date, int] = {}
    for year in range(start.year, today.year + 1):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        url = f"{CONTRIBUTIONS_URL}?from={year_start.isoformat()}&to={year_end.isoformat()}"
        request = Request(
            url,
            headers={"Accept": "text/html", "User-Agent": f"{USERNAME}-profile-stats"},
        )
        with urlopen(request, timeout=30) as response:
            markup = response.read().decode("utf-8")
        counts.update(parse_contributions(markup))

    days = []
    for offset in range((today - start).days + 1):
        day = start + timedelta(days=offset)
        if day not in counts:
            raise RuntimeError(f"GitHub contribution calendar is missing {day.isoformat()}")
        days.append((day, counts[day]))

    existing_readme = README_PATH.read_text(encoding="utf-8")
    updated_readme = replace_motd_section(existing_readme, render_motd(days))
    if updated_readme != existing_readme:
        README_PATH.write_text(updated_readme, encoding="utf-8")


def main() -> None:
    OVERVIEW_OUTPUT.write_text(render_stats(*collect_stats()), encoding="utf-8")
    refresh_contributions()


if __name__ == "__main__":
    main()

