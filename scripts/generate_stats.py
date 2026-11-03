#!/usr/bin/env python3
"""Genera las tarjetas SVG del perfil (estadísticas, lenguajes y actividad).

Usa solo la librería estándar y la API GraphQL de GitHub. Se ejecuta desde
.github/workflows/stats.yml y escribe los SVG en assets/ (versión clara y oscura).

Variables de entorno:
  GITHUB_TOKEN   token con acceso de lectura (obligatorio salvo con --demo)
  GH_USER        usuario de GitHub (por defecto: luchoweb)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("GH_USER", "luchoweb")
OUT = Path(__file__).resolve().parent.parent / "assets"

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"

THEMES = {
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "title": "#f0f6fc", "text": "#c9d1d9",
        "muted": "#8b949e", "track": "#21262d",
        "ramp": ["#161b22", "#2d333b", "#545d68", "#8b949e", "#e6edf3"],
        "bars": ["#e6edf3", "#adbac7", "#768390", "#545d68", "#373e47"],
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "title": "#1f2328", "text": "#1f2328",
        "muted": "#656d76", "track": "#eaeef2",
        "ramp": ["#ebedf0", "#d0d7de", "#8c959f", "#57606a", "#1f2328"],
        "bars": ["#1f2328", "#424a53", "#6e7781", "#8c959f", "#afb8c1"],
    },
}

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    createdAt
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def graphql(token: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats-generator"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def fetch(token: str) -> dict:
    cursor, repos, user = None, [], None
    while True:
        user = graphql(token, {"login": USER, "cursor": cursor})
        page = user["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    langs: dict[str, int] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            langs[edge["node"]["name"]] = langs.get(edge["node"]["name"], 0) + edge["size"]

    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return {
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "contributions": cc["contributionCalendar"]["totalContributions"],
        "languages": langs,
        "days": days,
    }


def demo() -> dict:
    import random
    random.seed(7)
    today = dt.date.today()
    start = today - dt.timedelta(days=364 + (today.weekday() + 1) % 7)
    days = []
    d = start
    while d <= today:
        n = random.choice([0, 0, 0, 1, 2, 3, 5, 8]) if d.weekday() < 5 else random.choice([0, 0, 1])
        days.append({"date": d.isoformat(), "contributionCount": n})
        d += dt.timedelta(days=1)
    return {
        "stars": 42, "repos": 37, "followers": 120, "commits": 812, "prs": 64, "issues": 18,
        "reviews": 51, "contributions": sum(x["contributionCount"] for x in days),
        "languages": {"TypeScript": 520000, "JavaScript": 310000, "Python": 120000,
                      "CSS": 90000, "HTML": 40000, "Shell": 8000},
        "days": days,
    }


def fmt(n: int) -> str:
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 10000 else f"{n:,}".replace(",", ".")


def frame(w: int, h: int, t: dict, title: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
<style>
  .t {{ font: 600 14px {FONT}; fill: {t['title']}; letter-spacing: .2px; }}
  .l {{ font: 400 12px {FONT}; fill: {t['muted']}; }}
  .v {{ font: 600 20px {FONT}; fill: {t['text']}; }}
  .s {{ font: 400 12px {FONT}; fill: {t['text']}; }}
  .m {{ font: 400 11px {MONO}; fill: {t['muted']}; }}
</style>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="8" fill="{t['bg']}" stroke="{t['border']}"/>
<text x="24" y="36" class="t">{escape(title)}</text>
{body}
</svg>
"""


def card_stats(data: dict, t: dict) -> str:
    items = [
        ("Contribuciones (12 m)", data["contributions"]),
        ("Commits (12 m)", data["commits"]),
        ("Pull requests", data["prs"]),
        ("Code reviews", data["reviews"]),
        ("Repositorios", data["repos"]),
        ("Estrellas", data["stars"]),
    ]
    w, h, cols = 495, 195, 3
    cw = (w - 48) / cols
    parts = []
    for i, (label, value) in enumerate(items):
        x = 24 + (i % cols) * cw
        y = 82 + (i // cols) * 62
        parts.append(f'<text x="{x:.0f}" y="{y}" class="v">{fmt(value)}</text>'
                     f'<text x="{x:.0f}" y="{y + 20}" class="l">{escape(label)}</text>')
    parts.append(f'<line x1="24" x2="{w-24}" y1="52" y2="52" stroke="{t["track"]}"/>')
    return frame(w, h, t, "Actividad en GitHub", "\n".join(parts))


def card_langs(data: dict, t: dict) -> str:
    w, h = 495, 195
    langs = sorted(data["languages"].items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in langs) or 1
    top = langs[:5]
    other = total - sum(v for _, v in top)
    if other > 0 and len(langs) > 5:
        top = top[:4] + [("Otros", other + top[4][1])]
    bar_w = w - 48
    parts = [f'<line x1="24" x2="{w-24}" y1="52" y2="52" stroke="{t["track"]}"/>',
             f'<clipPath id="c"><rect x="24" y="70" width="{bar_w}" height="8" rx="4"/></clipPath>',
             f'<rect x="24" y="70" width="{bar_w}" height="8" rx="4" fill="{t["track"]}"/>']
    x = 24.0
    segs = []
    for i, (_, size) in enumerate(top):
        sw = bar_w * size / total
        segs.append(f'<rect x="{x:.2f}" y="70" width="{max(sw - 2, 0):.2f}" height="8" fill="{t["bars"][i]}"/>')
        x += sw
    parts.append(f'<g clip-path="url(#c)">{"".join(segs)}</g>')
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        lx = 24 + col * (bar_w / 2)
        ly = 108 + row * 26
        pct = 100 * size / total
        parts.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" fill="{t["bars"][i]}"/>'
                     f'<text x="{lx + 18}" y="{ly}" class="s">{escape(name)}</text>'
                     f'<text x="{lx + bar_w/2 - 24}" y="{ly}" class="m" text-anchor="end">{pct:.1f}%</text>')
    if not top:
        parts.append('<text x="24" y="110" class="l">Sin datos todavía</text>')
    return frame(w, h, t, "Lenguajes más usados", "\n".join(parts))


def streaks(days: list[dict]) -> tuple[int, int]:
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)
    current = 0
    seq = list(days)
    if seq and seq[-1]["contributionCount"] == 0:  # hoy aún sin contribuciones no rompe la racha
        seq = seq[:-1]
    for d in reversed(seq):
        if d["contributionCount"] == 0:
            break
        current += 1
    return current, longest


def card_calendar(data: dict, t: dict) -> str:
    days = data["days"]
    gap = 3
    weeks: list[list[dict]] = []
    for d in days:
        wd = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7  # domingo = 0
        if not weeks or wd == 0:
            weeks.append([])
        weeks[-1].append((wd, d))
    w = 1000
    cell = max(int((w - 48 + gap) / max(len(weeks), 1)) - gap, 6)
    x0 = (w - (len(weeks) * (cell + gap) - gap)) / 2
    h = 68 + 7 * (cell + gap) + 44
    counts = sorted(c["contributionCount"] for c in days if c["contributionCount"] > 0)

    def level(n: int) -> int:
        if n == 0 or not counts:
            return 0
        q = [counts[int(len(counts) * p)] for p in (.25, .5, .75)]
        return 1 + sum(n > x for x in q)

    parts = [f'<line x1="24" x2="{w-24}" y1="52" y2="52" stroke="{t["track"]}"/>']
    for wi, week in enumerate(weeks):
        for wd, d in week:
            x = x0 + wi * (cell + gap)
            y = 68 + wd * (cell + gap)
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                         f'fill="{t["ramp"][level(d["contributionCount"])]}"><title>{d["date"]}: {d["contributionCount"]}</title></rect>')
    cur, best = streaks(days)
    y = 68 + 7 * (cell + gap) + 26
    summary = [("Racha actual", f"{cur} días"), ("Racha más larga", f"{best} días"),
               ("Total", fmt(data["contributions"]))]
    for i, (label, value) in enumerate(summary):
        parts.append(f'<text x="{24 + i * 150}" y="{y}" class="l">{escape(label)} '
                     f'<tspan class="s" dx="4">{escape(value)}</tspan></text>')
    lx = w - 24 - 30 - 5 * 13 + 3
    parts.append(f'<text x="{lx - 6}" y="{y}" class="m" text-anchor="end">menos</text>')
    for i, c in enumerate(t["ramp"]):
        parts.append(f'<rect x="{lx + i * 13}" y="{y - 9}" width="10" height="10" rx="2" fill="{c}"/>')
    parts.append(f'<text x="{w - 24}" y="{y}" class="m" text-anchor="end">más</text>')
    return frame(w, h, t, "Contribuciones del último año", "\n".join(parts))


def main() -> None:
    if "--demo" in sys.argv:
        data = demo()
    elif "--empty" in sys.argv:  # marcador inicial hasta la primera ejecución del workflow
        data = demo()
        data.update({k: 0 for k in ("stars", "repos", "followers", "commits", "prs",
                                     "issues", "reviews", "contributions")}, languages={})
        for d in data["days"]:
            d["contributionCount"] = 0
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("Falta GITHUB_TOKEN")
        data = fetch(token)
    OUT.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        (OUT / f"stats-{name}.svg").write_text(card_stats(data, theme), encoding="utf-8")
        (OUT / f"languages-{name}.svg").write_text(card_langs(data, theme), encoding="utf-8")
        (OUT / f"activity-{name}.svg").write_text(card_calendar(data, theme), encoding="utf-8")
    print(f"SVG generados en {OUT}")


if __name__ == "__main__":
    main()
