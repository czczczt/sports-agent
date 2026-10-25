"""Разведка площадок, недоступных с зарубежного IP (ERRORS.md, E1).

Запускать из российской сети (VPN выключен):
    python recon_blocked.py

Сохраняет в data/recon/: HTML страниц, найденные в JS адреса API и summary.json.
Персональных данных не собирает — только главные страницы и списки стартов.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

SITES = [
    "https://results.runc.run/",
    "https://grom.place/?sort=past",
    "https://myfinish.info/races",
    "https://new.myfinish.info/9504",  # протоколы myfinish; с IP в США не открывается (E19)
]
OUT = Path(__file__).parent / "data" / "recon"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
SPA_MARKERS = r'id="(root|app|__next|__nuxt)"|__NUXT__|__NEXT_DATA__|ng-version|<app-root'  # app-root: Angular (myfinish)


def egress_country() -> str:
    try:
        r = requests.get("https://ipinfo.io/country", timeout=10)
    except requests.RequestException as e:
        return f"не определена ({type(e).__name__})"
    return r.text.strip() if r.ok else f"не определена (HTTP {r.status_code})"  # 429 — лимит сервиса


def probe(url: str) -> dict:
    host = urlparse(url).netloc
    info: dict = {"url": url}
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except requests.RequestException as e:
        info["error"] = f"{type(e).__name__}: {e}"[:300]
        return info
    if "charset" not in r.headers.get("Content-Type", "").lower():
        r.encoding = r.apparent_encoding  # иначе requests берёт latin-1 и кириллица ломается (myfinish)
    html = r.text
    (OUT / f"{host}.html").write_text(html, encoding="utf-8")
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
    links = sorted({a for a in re.findall(r'href="([^"#]+)"', html) if not a.endswith((".css", ".ico", ".png", ".svg"))})
    info.update({
        "status": r.status_code, "final_url": r.url, "bytes": len(r.content),
        "title": title.group(1).strip()[:100] if title else None,
        "spa": bool(re.search(SPA_MARKERS, html)),
        "tables": html.lower().count("<table"),
        "links_sample": links[:60],
    })
    # адреса API в JS-бандлах (для SPA)
    endpoints = set()
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html)[:30]:
        try:
            js = requests.get(urljoin(url, src), headers=UA, timeout=30).text
        except requests.RequestException:
            continue
        endpoints |= set(re.findall(r'["\'`](/?(?:api|graphql|v\d)/[A-Za-z0-9_/\-{}$.]{2,80})', js))
    info["api_endpoints"] = sorted(endpoints)[:80]
    # та же платформа, что у russiarunning?
    try:
        p = requests.post(urljoin(url, "/api/events/list"),
                          json={"page": {"skip": 0, "take": 1}, "language": "ru"}, headers=UA, timeout=20)
        info["rr_platform"] = p.status_code == 200 and p.text.startswith('{"list"')
    except requests.RequestException:
        info["rr_platform"] = False
    return info


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"egress_country": egress_country(), "sites": []}
    print("Страна исходящего IP:", summary["egress_country"])
    for url in SITES:
        info = probe(url)
        summary["sites"].append(info)
        print(f"{url:35s} -> {info.get('status', info.get('error'))}")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Готово: {OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
