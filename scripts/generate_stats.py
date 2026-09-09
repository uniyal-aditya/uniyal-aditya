import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html import escape
from concurrent.futures import ThreadPoolExecutor, as_completed

OWNER = "uniyal-aditya"
OUT_DIR = "stats"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
EXCLUDED = {"Lavalink", "oldportfolio", "officialadityacreations"}
TOP_REPOS = [
    "Numexa-website",
    "numexa_legacy",
    "adityauniyal-portfolio",
    "Admitflow",
    "numexa",
]
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "uniyal-aditya-profile-stats",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def get_json(url, method="GET", body=None):
    data = None
    headers = dict(HEADERS)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def svg(text, width=900, height=420):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0f172a"/><stop offset="1" stop-color="#102a43"/></linearGradient>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0e7490"/><stop offset="1" stop-color="#22c55e"/></linearGradient>
</defs>
<rect width="100%" height="100%" rx="14" fill="url(#bg)" stroke="#334155"/>
{text}
</svg>'''


def text(x, y, value, size=18, weight=400, fill="#e2e8f0", anchor="start"):
    return f'<text x="{x}" y="{y}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}px" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(str(value))}</text>'


def line(x1, y1, x2, y2, stroke="#334155"):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}"/>'


def rect(x, y, w, h, fill="#172033", rx=10, stroke="none"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'


def save(name, content):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
        f.write(content)


def main():
    user = get_json(f"{API}/users/{OWNER}")
    repos = []
    page = 1
    while True:
        batch = get_json(f"{API}/users/{OWNER}/repos?type=owner&per_page=100&page={page}&sort=updated")
        if not batch:
            break
        repos.extend([r for r in batch if not r.get("fork")])
        if len(batch) < 100:
            break
        page += 1

    public_repos = [r for r in repos if r.get("visibility") == "public"]
    personal_repos = [r for r in public_repos if r["name"] not in EXCLUDED]
    personal_stars = sum(r.get("stargazers_count", 0) for r in personal_repos)
    all_stars = sum(r.get("stargazers_count", 0) for r in public_repos)

    language_totals = {}
    def fetch_lang(repo):
        return repo["name"], get_json(f"{API}/repos/{OWNER}/{urllib.parse.quote(repo['name'], safe='')}/languages")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_lang, r) for r in public_repos]
        for future in as_completed(futures):
            _, langs = future.result()
            for lang, count in langs.items():
                language_totals[lang] = language_totals.get(lang, 0) + count

    # GitHub GraphQL contribution calendar for the last year.
    gql = '''query($login:String!) {
      user(login:$login) {
        contributionsCollection {
          totalContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }'''
    graph = get_json("https://api.github.com/graphql", method="POST", body={"query": gql, "variables": {"login": OWNER}})
    cc = (((graph.get("data") or {}).get("user") or {}).get("contributionsCollection") or {})
    calendar = ((cc.get("contributionCalendar") or {}).get("weeks") or [])
    days = [d for w in calendar for d in w.get("contributionDays", [])]
    contrib_total = cc.get("totalContributions", 0)
    counts = {d["date"]: d["contributionCount"] for d in days}

    current = 0
    cursor = date.today()
    # GitHub's contribution calendar can lag by a day; allow the last contribution today/yesterday.
    if counts.get(cursor.isoformat(), 0) == 0:
        cursor -= timedelta(days=1)
    while counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    for d in days:
        if d.get("contributionCount", 0) > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    # Summary card.
    s = []
    s += [text(40, 46, "GitHub Impact", 24, 700), text(40, 74, "Live data generated by GitHub Actions", 13, 400, "#94a3b8")]
    cards = [
        ("Personal stars", personal_stars),
        ("Public repos", len(public_repos)),
        ("Followers", user.get("followers", 0)),
        ("Contributions", contrib_total),
        ("Current streak", f"{current} days"),
        ("Longest streak", f"{longest} days"),
    ]
    for i, (label, value) in enumerate(cards):
        col = i % 3
        row = i // 3
        x = 40 + col * 280
        y = 105 + row * 125
        s.append(rect(x, y, 250, 100, "#111827", 12, "#334155"))
        s.append(text(x + 20, y + 35, value, 28, 700, "#e2e8f0"))
        s.append(text(x + 20, y + 68, label, 13, 400, "#94a3b8"))
    s.append(text(40, 370, f"{len(personal_repos)} personal public repositories included • Excluded: {', '.join(sorted(EXCLUDED))}", 12, 400, "#64748b"))
    save("summary.svg", svg("".join(s), 900, 400))

    # Top languages card.
    top_langs = sorted(language_totals.items(), key=lambda x: x[1], reverse=True)[:8]
    total_bytes = max(sum(language_totals.values()), 1)
    l = [text(40, 46, "Top Languages", 24, 700), text(40, 74, "Aggregated from public owned repositories", 13, 400, "#94a3b8")]
    y = 105
    for lang, count in top_langs:
        pct = count / total_bytes
        l.append(text(40, y + 16, lang, 14, 600))
        l.append(rect(170, y + 3, 600, 14, "#1e293b", 7))
        l.append(rect(170, y + 3, max(3, int(600 * pct)), 14, "url(#dummy)", 7))
        l.append(f'<rect x="170" y="{y+3}" width="{max(3, int(600*pct))}" height="14" rx="7" fill="url(#accent)"/>')
        l.append(text(790, y + 16, f"{pct*100:.1f}%", 13, 500, "#94a3b8", "end"))
        y += 35
    save("languages.svg", svg("".join(l), 900, 410))

    # Streak card.
    st = [text(40, 48, "Contribution Streak", 24, 700), text(40, 76, "Last 12 months • GitHub contribution calendar", 13, 400, "#94a3b8")]
    st += [text(220, 150, current, 56, 700, "#e2e8f0", "middle"), text(220, 177, "current streak", 14, 400, "#94a3b8", "middle")]
    st += [text(500, 150, longest, 56, 700, "#e2e8f0", "middle"), text(500, 177, "longest streak", 14, 400, "#94a3b8", "middle")]
    st += [text(760, 150, contrib_total, 56, 700, "#e2e8f0", "middle"), text(760, 177, "contributions", 14, 400, "#94a3b8", "middle")]
    # mini calendar
    start_x, start_y = 55, 235
    cell = 13
    gap = 3
    # 26 weeks x 7 days, newest on right.
    recent = days[-182:]
    for idx, d in enumerate(recent):
        col = idx // 7
        row = idx % 7
        c = d.get("contributionCount", 0)
        shade = "#0f172a" if c == 0 else ("#14532d" if c < 3 else ("#15803d" if c < 6 else "#22c55e"))
        st.append(rect(start_x + col*(cell+gap), start_y + row*(cell+gap), cell, cell, shade, 3))
    save("streak.svg", svg("".join(st), 900, 340))

    # Top repositories card, intentionally curated to avoid upstream/public repos.
    by_name = {r["name"]: r for r in public_repos}
    tr = [text(40, 46, "Top Repositories", 24, 700), text(40, 74, "Selected personal projects • live star counts", 13, 400, "#94a3b8")]
    for i, name in enumerate(TOP_REPOS):
        repo = by_name.get(name, {})
        stars = repo.get("stargazers_count", 0)
        x = 40 + (i % 2) * 430
        y = 105 + (i // 2) * 92
        if i == 4:
            x = 40
        tr.append(rect(x, y, 390, 70, "#111827", 10, "#334155"))
        tr.append(text(x + 18, y + 29, name, 15, 600))
        tr.append(text(x + 365, y + 29, f"★ {stars}", 16, 700, "#22c55e", "end"))
        tr.append(text(x + 18, y + 52, f"github.com/{OWNER}/{name}", 11, 400, "#64748b"))
    save("top-repos.svg", svg("".join(tr), 900, 360))


if __name__ == "__main__":
    main()
