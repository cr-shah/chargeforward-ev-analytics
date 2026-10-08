"""Fast static checks for the GitHub Pages case study."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[tuple[str, str]] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if tag in {"a", "link", "script"}:
            target = values.get("href") or values.get("src")
            if target:
                self.links.append((tag, target))
        if tag == "img" and values.get("src"):
            self.images.append(values["src"] or "")


def main() -> None:
    index = ROOT / "index.html"
    parser = PageParser()
    parser.feed(index.read_text(encoding="utf-8"))
    errors: list[str] = []

    for tag, target in parser.links:
        if target.startswith("#"):
            if target[1:] not in parser.ids:
                errors.append(f"missing anchor target: {target}")
            continue
        parsed = urlparse(target)
        if parsed.scheme in {"http", "https", "mailto"}:
            continue
        path = (ROOT / parsed.path).resolve()
        if ROOT not in path.parents and path != ROOT:
            errors.append(f"path escapes repository: {target}")
        elif not path.exists():
            errors.append(f"missing {tag} asset: {target}")

    for target in parser.images:
        parsed = urlparse(target)
        if not parsed.scheme and not (ROOT / parsed.path).exists():
            errors.append(f"missing image: {target}")

    required = [
        "assets/site-data.js",
        "assets/live-data.js",
        "assets/app.js",
        "assets/styles.css",
        "assets/favicon.svg",
        "assets/chargeforward-social.png",
        ".nojekyll",
    ]
    errors.extend(f"missing required file: {name}" for name in required if not (ROOT / name).exists())

    html = index.read_text(encoding="utf-8")
    site_data = (ROOT / "assets" / "site-data.js").read_text(encoding="utf-8")
    live_text = (ROOT / "assets" / "live-data.js").read_text(encoding="utf-8")
    for claim in ["92.95", "10.3%", "75.9%"]:
        if claim not in html:
            errors.append(f"missing verified headline claim: {claim}")
    for marker in ['"vehicles":298916', '"transactions":576457', '"mlBetterCounties":34']:
        if marker not in site_data:
            errors.append(f"missing verified data marker: {marker}")

    prefix = "window.CHARGEFORWARD_LIVE="
    try:
        live_payload = json.loads(live_text.split(prefix, 1)[1].rstrip().removesuffix(";"))
    except (IndexError, json.JSONDecodeError) as exc:
        errors.append(f"invalid live data bundle: {exc}")
        live_payload = {}
    if len(live_payload.get("counties", [])) != 39:
        errors.append("live bundle must include all 39 Washington counties")
    if live_payload.get("stateTotals", {}).get("public_ports", 0) <= 0:
        errors.append("live bundle has no public charging ports")
    if len(live_payload.get("stations", [])) <= 1000:
        errors.append("live bundle has unexpectedly few mapped charging stations")
    if not live_payload.get("sources", {}).get("ev_population", {}).get("rows_updated_at"):
        errors.append("live bundle is missing EV population freshness")
    for required_id in ["live", "live-map", "county-rank-list", "county-detail"]:
        if required_id not in parser.ids:
            errors.append(f"missing live explorer element: #{required_id}")

    if errors:
        raise SystemExit("Site verification failed:\n- " + "\n- ".join(errors))
    print(f"Site verification passed: {len(parser.ids)} ids, {len(parser.links)} linked resources")


if __name__ == "__main__":
    main()
