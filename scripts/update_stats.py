"""Refresh the profile's GitHub data and cloud-security MOTD section."""

from __future__ import annotations

import json
import math
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont


USERNAME = os.environ.get("PROFILE_GITHUB_USER", "adnannazirahmed")
TOKEN = os.environ.get("GH_TOKEN")
ROOT = Path(__file__).resolve().parents[1]
OVERVIEW_OUTPUT = ROOT / "assets" / "github-overview.svg"
MOTD_IMAGE_PATH = ROOT / "assets" / "cloud-security-motd.gif"
README_PATH = ROOT / "README.md"
MOTD_START = "<!-- contribution-motd:start -->"
MOTD_END = "<!-- contribution-motd:end -->"
CONTRIBUTIONS_URL = f"https://github.com/users/{USERNAME}/contributions"


@dataclass(frozen=True)
class ContributionSummary:
    total: int
    active_days: int
    best_day: int
    average: float
    current_streak: int
    current_note: str
    longest_streak: int
    longest_start: date | None
    longest_end: date | None
    months: tuple[tuple[date, int], ...]
    latest_day: date


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


def summarize_contributions(days: list[tuple[date, int]]) -> ContributionSummary:
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
    running_start: date | None = None
    longest_start: date | None = None
    longest_end: date | None = None
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
            running_start = None

    monthly: OrderedDict[tuple[int, int], int] = OrderedDict()
    for day, count in days:
        key = (day.year, day.month)
        monthly[key] = monthly.get(key, 0) + count
    months = tuple(
        (date(year, month, 1), count)
        for (year, month), count in list(monthly.items())[-12:]
    )

    if current_streak and days[-1][0] == date.today() and days[-1][1] > 0:
        current_note = "active today"
    elif current_streak:
        current_note = "active through yesterday"
    else:
        current_note = "ready for the next contribution"

    return ContributionSummary(
        total=total,
        active_days=active_days,
        best_day=best_day,
        average=average,
        current_streak=current_streak,
        current_note=current_note,
        longest_streak=longest_streak,
        longest_start=longest_start,
        longest_end=longest_end,
        months=months,
        latest_day=days[-1][0],
    )


def render_motd(summary: ContributionSummary) -> str:
    """Render accessible profile Markdown around the animated terminal card."""
    current_unit = "day" if summary.current_streak == 1 else "days"
    longest_unit = "day" if summary.longest_streak == 1 else "days"
    longest_range = (
        f"{summary.longest_start:%b} {summary.longest_start.day}-"
        f"{summary.longest_end:%b} {summary.longest_end.day}"
        if summary.longest_start and summary.longest_end
        else "no active days yet"
    )
    alt = (
        "Animated cloud infrastructure and cybersecurity stats: "
        f"current streak {summary.current_streak} {current_unit}, "
        f"longest streak {summary.longest_streak} {longest_unit} ({longest_range}), "
        f"{summary.total} contributions over {summary.active_days} active days, "
        f"best day {summary.best_day}, average {summary.average:.1f} per active day, "
        f"through {summary.latest_day.isoformat()}."
    )
    lines = [
        MOTD_START,
        f"### `{USERNAME}@github:~$ motd --cloud-security`",
        "",
        f'<img src="./assets/cloud-security-motd.gif" width="100%" alt="{alt}" />',
        "",
        "<sub>AWS · Azure · IAM · practical defense · refreshed every 12 hours</sub>",
        MOTD_END,
    ]
    return "\n".join(lines)


def _load_mono_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_paths = (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "C:/Windows/Fonts/consolab.ttf")
        if bold
        else ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf")
    )
    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_motd_gif(summary: ContributionSummary, output_path: Path) -> None:
    """Draw a responsive terminal card with a subtle cursor and status pulse."""
    width, height = 960, 500
    frames: list[Image.Image] = []
    font_tiny = _load_mono_font(12)
    font_small = _load_mono_font(14)
    font_body = _load_mono_font(16)
    font_metric = _load_mono_font(27, bold=True)
    font_title = _load_mono_font(22, bold=True)

    background = (11, 16, 23)
    panel = (17, 25, 35)
    inner = (12, 18, 26)
    border = (42, 56, 70)
    white = (232, 240, 248)
    muted = (142, 160, 179)
    green = (128, 228, 154)
    green_dim = (46, 111, 69)
    blue = (131, 184, 255)
    months_max = max((value for _, value in summary.months), default=1) or 1
    current_month = (summary.latest_day.year, summary.latest_day.month)
    longest_range = (
        f"{summary.longest_start:%b} {summary.longest_start.day}–"
        f"{summary.longest_end:%b} {summary.longest_end.day}"
        if summary.longest_start and summary.longest_end
        else "no active days yet"
    )
    command = f"{USERNAME}@github:~$ motd --cloud-security"

    for frame_index in range(12):
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((16, 14, 944, 486), radius=16, fill=panel, outline=border, width=2)

        for x, color in ((40, (255, 108, 99)), (58, (255, 196, 87)), (76, (101, 214, 127))):
            draw.ellipse((x, 29, x + 9, 38), fill=color)
        draw.text((100, 24), command, font=font_body, fill=white)
        command_width = draw.textlength(command, font=font_body)
        if frame_index < 6:
            draw.rounded_rectangle((104 + command_width, 27, 109 + command_width, 44), radius=1, fill=green)

        pulse = (1 + math.sin((frame_index / 12) * math.tau)) / 2
        live_color = (int(55 + pulse * 73), int(131 + pulse * 97), int(82 + pulse * 72))
        draw.ellipse((803, 28, 812, 37), fill=live_color)
        draw.text((820, 25), "LIVE · 12H", font=font_tiny, fill=green)
        draw.line((34, 57, 926, 57), fill=border, width=1)

        draw.text((40, 72), "CLOUD INFRASTRUCTURE / CYBERSECURITY", font=font_title, fill=white)
        draw.text((40, 104), "AWS / AZURE / IAM / PRACTICAL DEFENSE", font=font_small, fill=blue)

        hero_cards = (
            (40, "CURRENT STREAK", f"{summary.current_streak} {('day' if summary.current_streak == 1 else 'days')}", summary.current_note),
            (490, "LONGEST STREAK", f"{summary.longest_streak} {('day' if summary.longest_streak == 1 else 'days')}", longest_range),
        )
        for x, label, value, note in hero_cards:
            draw.rounded_rectangle((x, 137, x + 430, 220), radius=10, fill=inner, outline=border, width=1)
            draw.text((x + 17, 149), label, font=font_tiny, fill=muted)
            draw.text((x + 17, 168), value, font=font_metric, fill=green if label == "CURRENT STREAK" else white)
            draw.text((x + 210, 180), note, font=font_tiny, fill=muted)

        metric_cards = (
            ("CONTRIBUTIONS", str(summary.total)),
            ("ACTIVE DAYS", str(summary.active_days)),
            ("BEST DAY", str(summary.best_day)),
            ("AVG / ACTIVE DAY", f"{summary.average:.1f}"),
        )
        for index, (label, value) in enumerate(metric_cards):
            x = 40 + index * 225
            draw.rounded_rectangle((x, 232, x + 210, 300), radius=9, fill=inner, outline=border, width=1)
            draw.text((x + 13, 242), label, font=font_tiny, fill=muted)
            draw.text((x + 13, 260), value, font=font_metric, fill=white)

        draw.rounded_rectangle((40, 312, 920, 442), radius=10, fill=inner, outline=border, width=1)
        draw.text((57, 322), "MONTHLY CONTRIBUTIONS · LAST 12 MONTHS", font=font_tiny, fill=muted)
        baseline = 414
        bar_width = 32
        for index, (month, value) in enumerate(summary.months):
            x = 76 + index * 70
            bar_height = round(48 * value / months_max)
            bar_color = green if (month.year, month.month) == current_month else green_dim
            if value:
                draw.rounded_rectangle(
                    (x, baseline - bar_height, x + bar_width, baseline),
                    radius=5,
                    fill=bar_color,
                )
                draw.text((x + 4, baseline - bar_height - 17), str(value), font=font_tiny, fill=muted)
            draw.text((x - 1, 420), month.strftime("%b").upper(), font=font_tiny, fill=green if (month.year, month.month) == current_month else muted)

        draw.text((40, 455), f"activity through {summary.latest_day.isoformat()}", font=font_tiny, fill=muted)
        draw.text((760, 455), "AWS · AZURE · IAM", font=font_tiny, fill=green)
        frames.append(image)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    palette_frames = [frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for frame in frames]
    palette_frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=palette_frames[1:],
        duration=360,
        loop=0,
        optimize=True,
        disposal=2,
    )


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

    summary = summarize_contributions(days)
    render_motd_gif(summary, MOTD_IMAGE_PATH)

    existing_readme = README_PATH.read_text(encoding="utf-8")
    updated_readme = replace_motd_section(existing_readme, render_motd(summary))
    if updated_readme != existing_readme:
        README_PATH.write_text(updated_readme, encoding="utf-8")


def main() -> None:
    OVERVIEW_OUTPUT.write_text(render_stats(*collect_stats()), encoding="utf-8")
    refresh_contributions()


if __name__ == "__main__":
    main()

