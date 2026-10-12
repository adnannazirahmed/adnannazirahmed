"""Generate the profile statistics SVG from public GitHub data."""

from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = os.environ.get("PROFILE_GITHUB_USER", "adnannazirahmed")
TOKEN = os.environ.get("GH_TOKEN")
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"
CONTRIBUTIONS_OUTPUT = (
    Path(__file__).resolve().parents[1] / "assets" / "contributions.svg"
)
STREAKS_OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "streak-stats.svg"
CONTRIBUTIONS_URL = f"https://ghchart.xqsit94.in/dark:default/{USERNAME}"


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


def collect_stats() -> tuple[int, int, int, int]:
    user = github_json(f"https://api.github.com/users/{USERNAME}")
    repos = github_json(
        f"https://api.github.com/users/{USERNAME}/repos"
        "?per_page=100&type=owner&sort=updated"
    )

    stars = sum(repo.get("stargazers_count", 0) for repo in repos)
    languages = {repo.get("language") for repo in repos if repo.get("language")}
    return user["public_repos"], stars, user["followers"], len(languages)


def render_stats(repositories: int, stars: int, followers: int, languages: int) -> str:
    cards = (
        ("PUBLIC REPOSITORIES", repositories, "#58a6ff"),
        ("STARS RECEIVED", stars, "#f1e05a"),
        ("FOLLOWERS", followers, "#3fb950"),
        ("LANGUAGES USED", languages, "#a371f7"),
    )

    card_markup = []
    for index, (label, value, color) in enumerate(cards):
        x = 40 + index * 280
        card_markup.append(
            f'''  <g transform="translate({x} 112)">
    <rect width="250" height="112" rx="9" fill="#0d1117" stroke="#30363d"/>
    <circle cx="24" cy="27" r="5" fill="{color}"/>
    <text x="42" y="32" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="12">{label}</text>
    <text x="22" y="82" fill="#e6ebf5" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="38" font-weight="700">{value}</text>
  </g>'''
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="270" viewBox="0 0 1200 270" role="img" aria-labelledby="title desc">
  <title id="title">Adnan Ahmed's GitHub statistics</title>
  <desc id="desc">Automatically updated public repository, star, follower, and language totals.</desc>
  <rect width="1200" height="270" rx="12" fill="#161b22" stroke="#30363d" stroke-width="2"/>
  <text x="40" y="43" fill="#3fb950" font-family="JetBrains Mono, Consolas, monospace" font-size="15">LIVE — GITHUB STATS</text>
  <text x="40" y="83" fill="#e6ebf5" font-family="Space Grotesk, Segoe UI, sans-serif" font-size="30" font-weight="700">Public work at a glance</text>
{chr(10).join(card_markup)}
  <text x="40" y="252" fill="#8b949e" font-family="JetBrains Mono, Consolas, monospace" font-size="12">Automatically checked every 24 hours via GitHub Actions</text>
</svg>
'''


def contribution_days(svg: str) -> list[tuple[date, int]]:
    matches = re.findall(
        r"<title>(\d{4}-\d{2}-\d{2}): (\d+) contributions?</title>", svg
    )
    if not matches:
        raise RuntimeError("Contribution chart SVG contains no daily data")
    return [(datetime.strptime(day, "%Y-%m-%d").date(), int(count)) for day, count in matches]


def render_streak_stats(svg: str) -> str:
    days = contribution_days(svg)
    total = sum(count for _, count in days)
    active_days = sum(count > 0 for _, count in days)
    best_day = max(count for _, count in days)
    average = total / active_days if active_days else 0

    current_streak = 0
    for _, count in reversed(days):
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
    current_note = "active through latest day" if current_streak else "ready for the next commit"

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
  <text x="1160" y="416" text-anchor="end" fill="#3fb950" font-family="JetBrains Mono, Consolas, monospace" font-size="13">refreshed every 24 hours</text>
</svg>
'''


def refresh_contributions() -> None:
    request = Request(
        CONTRIBUTIONS_URL,
        headers={
            "Accept": "image/svg+xml",
            "User-Agent": f"{USERNAME}-profile-stats",
        },
    )
    with urlopen(request, timeout=30) as response:
        svg = response.read().decode("utf-8")

    width_match = re.search(r'(<svg\b[^>]*\bwidth=")(\d+)(")', svg)
    if not width_match:
        raise RuntimeError("Contribution chart SVG has no numeric width")

    original_width = int(width_match.group(2))
    padded_width = original_width + 32
    svg = (
        svg[: width_match.start(2)]
        + str(padded_width)
        + svg[width_match.end(2) :]
    )
    CONTRIBUTIONS_OUTPUT.write_text(svg, encoding="utf-8")
    STREAKS_OUTPUT.write_text(render_streak_stats(svg), encoding="utf-8")


def main() -> None:
    OUTPUT.write_text(render_stats(*collect_stats()), encoding="utf-8")
    refresh_contributions()


if __name__ == "__main__":
    main()

