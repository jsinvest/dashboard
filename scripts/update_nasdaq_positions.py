"""Build the public weekly Nasdaq-100 positioning panel from CFTC TFF futures-only data."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from pathlib import Path
from string import Template
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1] / "nasdaq-positioning"
CODE = "209742"
FIRST = date(2020, 1, 7)
DATASET = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CURRENT = "https://www.cftc.gov/dea/futures/financial_lf.htm"
DATE = "report_date_as_yyyy_mm_dd"
CONTRACT = "cftc_contract_market_code"
FIELDS = ("lev_money_positions_long", "lev_money_positions_short", "open_interest_all")


def read_source(path, url):
    if path:
        return path.read_bytes()
    req = Request(url, headers={"User-Agent": "JsInvest-Nasdaq100-Weekly/1.0"})
    with urlopen(req, timeout=45) as response:
        return response.read()


def weekly(records, today):
    observations = {}
    for row in records:
        if row[CONTRACT] != CODE:
            raise ValueError("Unexpected CFTC contract code")
        day = date.fromisoformat(row[DATE][:10])
        if day in observations or not FIRST <= day <= today:
            raise ValueError(f"Duplicate or out-of-range observation: {day}")
        values = [int(str(row[key])) for key in FIELDS]
        long, short, oi = values
        if oi <= 0 or not (0 <= long <= oi and 0 <= short <= oi):
            raise ValueError(f"Invalid position or open interest on {day}")
        observations[day] = {"date": day.isoformat(), "long": long, "short": short, "oi": oi}

    if min(observations, default=None) != FIRST:
        raise ValueError("Missing first reporting week")
    weeks = {}
    for day in sorted(observations):
        monday = day - timedelta(days=day.weekday())
        weeks[monday] = observations[day]  # Last reported observation in each calendar week.
    if (max(weeks) - min(weeks)).days // 7 + 1 != len(weeks):
        raise ValueError("Missing reporting week in the CFTC archive")
    return list(weeks.values())


def check_current(raw, row):
    report = unescape(re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="replace")))
    stamp = re.search(r"Futures Only Positions as of\s+([A-Za-z]+ \d{1,2}, \d{4})", report)
    block = re.search(r"CFTC Code\s+#209742\s+Open Interest is\s+([\d,]+)\s+Positions\s+"
                      r"((?:[\d,]+[ \t]+){13}[\d,]+)", report)
    if not stamp or not block:
        raise ValueError("Current official TFF futures-only report could not be verified")
    day = datetime.strptime(stamp[1], "%B %d, %Y").date().isoformat()
    columns = block[2].replace(",", "").split()
    expected = (day, int(columns[6]), int(columns[7]), int(block[1].replace(",", "")))
    if expected != (row["date"], row["long"], row["short"], row["oi"]):
        raise ValueError("Current report and historical dataset disagree")


def render(rows, estimates, digest):
    latest = rows[-1]
    table = []
    prev = None
    for row in rows:
        net = row["long"] - row["short"]
        delta = "—" if prev is None else f"{net - prev:+,}"
        table.append(f'<tr><td>{row["date"]}</td><td>{row["long"]:,}</td>'
                     f'<td>{row["short"]:,}</td><td>{net:+,}</td><td>{delta}</td>'
                     f'<td>{row["oi"]:,}</td><td>{100 * net / row["oi"]:+.2f}%</td></tr>')
        prev = net
    estimates_html = []
    observed = set()
    for obs in sorted(estimates, key=lambda item: item["published"], reverse=True):
        day = date.fromisoformat(obs["published"])
        source = obs["source"]
        key = day, obs["provider"]
        if urlparse(source).scheme != "https" or key in observed:
            raise ValueError("Invalid CTA estimate source or duplicate")
        observed.add(key)
        amount = int(obs["usd"])
        side = "순숏" if amount < 0 else ("순롱" if amount else "중립")
        estimates_html.append(f'<li>{day} 공개 · {escape(obs["provider"])} 추정 '
                              f'{abs(amount) / 100_000_000:,.1f}억 달러 {side} '
                              f'<a href="{escape(source, quote=True)}" target="_blank" rel="noopener">출처</a></li>')
    net = latest["long"] - latest["short"]
    previous = rows[-2]["long"] - rows[-2]["short"] if len(rows) > 1 else None
    return Template((ROOT / "panel.template.html").read_text(encoding="utf-8")).substitute(
        latest=latest["date"], first=rows[0]["date"], count=len(rows), digest=digest,
        side="순숏" if net < 0 else ("순롱" if net else "중립"),
        net=f"{abs(net):,}", delta="—" if previous is None else f"{net - previous:+,}",
        share=f'{100 * net / latest["oi"]:+.2f}%', table="\n".join(reversed(table)),
        estimates="".join(estimates_html) or "<li>확인된 공개 자료 없음</li>")


def publish_if_changed(path, body):
    if path.exists() and path.read_bytes() == body:
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, help="Offline CFTC rows in the API field format")
    parser.add_argument("--current-report", type=Path, help="Offline official current TFF report")
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    params = {"$select": ",".join((DATE, CONTRACT, *FIELDS)), CONTRACT: CODE,
              "$where": f"{DATE} >= '2020-01-01T00:00:00'", "$order": DATE, "$limit": 50000}
    blob = read_source(args.source_json, DATASET + "?" + urlencode(params))
    rows = weekly(json.loads(blob), datetime.now(timezone.utc).date())
    check_current(read_source(args.current_report, CURRENT), rows[-1])
    output = args.output_dir
    history = output / "history.json"
    if history.exists() and json.loads(history.read_bytes())["as_of"] > rows[-1]["date"]:
        raise ValueError("Refusing to replace newer published data")
    digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
    snapshot = {"schema": 1, "contract_code": CODE, "report": "TFF futures only",
                "group": "Leveraged Funds", "as_of": rows[-1]["date"], "weeks": len(rows),
                "sha256": digest, "source": DATASET, "history": rows}
    estimates = json.loads((ROOT / "cta_estimates.json").read_bytes())
    panel = render(rows, estimates, digest)
    output.mkdir(parents=True, exist_ok=True)
    publish_if_changed(history, (json.dumps(snapshot, separators=(",", ":")) + "\n").encode())
    publish_if_changed(output / "index.html", panel.encode())
    print(f'{rows[0]["date"]} .. {rows[-1]["date"]}: {len(rows)} weeks, sha256={digest}')


if __name__ == "__main__":
    main()
