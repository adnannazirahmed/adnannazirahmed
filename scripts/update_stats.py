"""Generate the profile statistics SVG from public GitHub data."""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = os.environ.get("PROFILE_GITHUB_USER", "adnannazirahmed")
TOKEN = os.environ.get("GH_TOKEN")
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "github-overview.svg"
CONTRIBUTIONS_OUTPUT = (
    Path(__file__).resolve().parents[1] / "assets" / "contributions.svg"
)
STREAKS_OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "streak-stats.svg"
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

        # Current GitHub markup places each accessible tooltip after the grid
        # and links it to a day cell by id instead of nesting it in the <td>.
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


def render_contributions(days: list[tuple[date, int]]) -> str:
    if not days:
        raise RuntimeError("Cannot render an empty contribution calendar")

    start = days[0][0]
    end = days[-1][0]
    calendar_start = start - timedelta(days=start.weekday())
    calendar_end = end + timedelta(days=(6 - end.weekday()))
    weeks = (calendar_end - calendar_start).days // 7 + 1
    count_by_day = dict(days)
    max_count = max((count for _, count in days), default=0)
    colors = ("#0d1117", "#0e4429", "#006d32", "#26a641", "#39d353")

    cells = []
    month_labels = []
    previous_month = None
    for week in range(weeks):
        x = 42 + week * 15
        for weekday in range(7):
            day = calendar_start + timedelta(days=week * 7 + weekday)
            if day > end or day < start:
                continue
            count = count_by_day.get(day, 0)
            level = 0 if count == 0 else min(4, max(1, (count * 4 + max_count - 1) // max_count))
            y = 30 + weekday * 15
            cells.append(
                f'<rect x="{x}" y="{y}" width="12" height="12" rx="2" '
                f'fill="{colors[level]}"><title>{day.isoformat()}: '
                f'{count} contributions</title></rect>'
            )
            if day.day == 1 or previous_month is None:
                month_labels.append(
                    f'<text x="{x}" y="18" fill="#cecece" '
                    f'font-family="Segoe UI, sans-serif" font-size="12">'
                    f'{day.strftime("%b")}</text>'
                )
            previous_month = day.month

    weekday_labels = "".join(
        f'<text x="0" y="{39 + row * 30}" fill="#cecece" '
        'font-family="Segoe UI, sans-serif" font-size="12">'
        f'{label}</text>'
        for row, label in ((0, "Mon"), (2, "Wed"), (4, "Fri"))
    )
    width = 54 + weeks * 15
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="145" '
        f'viewBox="0 0 {width} 145" role="img" aria-label="GitHub contributions">'
        f'<g>{weekday_labels}{"".join(month_labels)}{"".join(cells)}</g></svg>'
    )


def render_streak_stats(days: list[tuple[date, int]]) -> str:
    if not days:
        raise RuntimeError("Cannot render streak statistics without contribution days")
    total = sum(count for _, count in days)
    active_days = sum(count > 0 for _, count in days)
    best_day = max(count for _, count in days)
    average = total / active_days if active_days else 0

    current_streak = 0
    current_days = days
    if days[-1][0] == date.today() and days[-1][1] == 0:
        current_days = days[:-1]
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
    month_values = list(monthly.items())[-12:]
    highest_month = max((value for _, value in month_values), default=1) or 1

    bars = []
    for index, ((year, month), value) in enumerate(month_values):
        height = round(118 * value / highest_month)
        x = 800 + index * 28
        y = 306 - height
        label = datetime(year, month, 1).strftime("%b")[0]
        bars.append(
            f'''    <g>
      <title>{datetime(year, month, 1).strftime("%B %Y")}: {value} contributions</title>
      <rect x="{x}" y="{y}" width="18" height="{height}" rx="3" fill="#3fb950" opacity="{0.45 + (0.55 * value / highest_month):.2f}"/>
      <text x="{x + 9}" y="329" text-anchor="middle" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="11">{label}</text>
    </g>'''
        )

    latest_day = days[-1][0]
    longest_range = (
        f"{longest_start.strftime('%b')} {longest_start.day} — "
        f"{longest_end.strftime('%b')} {longest_end.day}"
    )
    current_note = "active through yesterday" if current_streak else "ready for the next commit"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="455" viewBox="0 0 1200 455" role="img" aria-labelledby="title desc">
  <title id="title">Adnan Ahmed's contribution streaks</title>
  <desc id="desc">Current streak, longest streak, contribution totals, active days, best day, average, and monthly activity.</desc>
  <rect width="1200" height="455" rx="12" fill="#161b22" stroke="#30363d" stroke-width="2"/>
  <text x="40" y="42" fill="#3fb950" font-family="JetBrains Mono, Consolas, monospace" font-size="15">LIVE — CONTRIBUTION MOMENTUM</text>
  <text x="40" y="82" fill="#e6ebf5" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="31" font-weight="700">Consistency, visualized</text>

  <g transform="translate(40 110)">
    <rect width="340" height="125" rx="9" fill="#0d1117" stroke="#30363d"/>
    <text x="20" y="31" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="13">$ CURRENT STREAK</text>
    <text x="20" y="80" fill="#3fb950" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="42" font-weight="700">{current_streak}<tspan fill="#8b949e" font-size="18"> days</tspan></text>
    <text x="20" y="106" fill="#8b949e" font-family="Inter, Segoe UI, sans-serif" font-size="13">{current_note}</text>
  </g>

  <g transform="translate(400 110)">
    <rect width="340" height="125" rx="9" fill="#0d1117" stroke="#30363d"/>
    <text x="20" y="31" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="13">$ LONGEST STREAK</text>
    <text x="20" y="80" fill="#e6ebf5" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="42" font-weight="700">{longest_streak}<tspan fill="#8b949e" font-size="18"> days</tspan></text>
    <text x="20" y="106" fill="#8b949e" font-family="Inter, Segoe UI, sans-serif" font-size="13">{longest_range}</text>
  </g>

  <g font-family="JetBrains Mono, Consolas, monospace">
    <g transform="translate(40 255)">
      <rect width="160" height="90" rx="8" fill="#0d1117" stroke="#30363d"/>
      <text x="16" y="27" fill="#8b949e" font-size="11">CONTRIBUTIONS</text>
      <text x="16" y="65" fill="#e6ebf5" font-size="27" font-weight="700">{total}</text>
    </g>
    <g transform="translate(220 255)">
      <rect width="160" height="90" rx="8" fill="#0d1117" stroke="#30363d"/>
      <text x="16" y="27" fill="#8b949e" font-size="11">ACTIVE DAYS</text>
      <text x="16" y="65" fill="#e6ebf5" font-size="27" font-weight="700">{active_days}</text>
    </g>
    <g transform="translate(400 255)">
      <rect width="160" height="90" rx="8" fill="#0d1117" stroke="#30363d"/>
      <text x="16" y="27" fill="#8b949e" font-size="11">BEST DAY</text>
      <text x="16" y="65" fill="#e6ebf5" font-size="27" font-weight="700">{best_day}</text>
    </g>
    <g transform="translate(580 255)">
      <rect width="160" height="90" rx="8" fill="#0d1117" stroke="#30363d"/>
      <text x="16" y="27" fill="#8b949e" font-size="11">AVG / ACTIVE DAY</text>
      <text x="16" y="65" fill="#e6ebf5" font-size="27" font-weight="700">{average:.1f}</text>
    </g>
  </g>

  <g>
    <rect x="780" y="110" width="380" height="235" rx="9" fill="#0d1117" stroke="#30363d"/>
    <text x="800" y="137" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="12">CONTRIBUTIONS / MONTH</text>
{chr(10).join(bars)}
  </g>

  <path d="M40 382H1160" stroke="#30363d"/>
  <text x="40" y="416" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="13">public activity through {latest_day.isoformat()}</text>
  <text x="1160" y="416" text-anchor="end" fill="#3fb950" font-family="JetBrains Mono, Consolas, monospace" font-size="13">refreshed every 12 hours</text>
</svg>
'''


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
            headers={
                "Accept": "text/html",
                "User-Agent": f"{USERNAME}-profile-stats",
            },
        )
        with urlopen(request, timeout=30) as response:
            markup = response.read().decode("utf-8")
        counts.update(parse_contributions(markup))

    days = []
    for offset in range((today - start).days + 1):
        day = start + timedelta(days=offset)
        if day not in counts:
            raise RuntimeError(
                f"GitHub contribution calendar is missing {day.isoformat()}"
            )
        days.append((day, counts[day]))
    svg = render_contributions(days)
    CONTRIBUTIONS_OUTPUT.write_text(svg, encoding="utf-8")
    STREAKS_OUTPUT.write_text(render_streak_stats(days), encoding="utf-8")


def main() -> None:
    OUTPUT.write_text(render_stats(*collect_stats()), encoding="utf-8")
    refresh_contributions()


if __name__ == "__main__":
    main()

