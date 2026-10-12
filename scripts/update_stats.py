"""Generate the profile statistics SVG from public GitHub data."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = os.environ.get("PROFILE_GITHUB_USER", "adnannazirahmed")
TOKEN = os.environ.get("GH_TOKEN")
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"
CONTRIBUTIONS_OUTPUT = (
    Path(__file__).resolve().parents[1] / "assets" / "contributions.svg"
)
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


def main() -> None:
    OUTPUT.write_text(render_stats(*collect_stats()), encoding="utf-8")
    refresh_contributions()


if __name__ == "__main__":
    main()

