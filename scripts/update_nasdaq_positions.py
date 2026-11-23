"""Build the public weekly Nasdaq-100 positioning panel from CFTC TFF futures-only data."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from pathlib import Path
from string import Template
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1] / "nasdaq-positioning"
CODE = "209742"
FIRST = date(2020, 1, 7)
DATASET = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CURRENT = "https://www.cftc.gov/dea/futures/financial_lf.htm"
DATE = "report_date_as_yyyy_mm_dd"
CONTRACT = "cftc_contract_market_code"
FIELDS = ("lev_money_positions_long", "lev_money_positions_short", "open_interest_all")
NDX_FIELDS = ("open", "high", "low", "close")
NDX_MIRROR = ("https://raw.githubusercontent.com/zid036116-ship-it/-/refs/heads/main/"
              "market_data/Nasdaq100%20%E7%BA%B3%E6%8C%87100___NDX.csv")
NDX_OFFICIAL = "https://indexes.nasdaq.com/Index/History/NDX"


def read_source(path, url, timeout=45):
    if path:
        return path.read_bytes()
    req = Request(url, headers={"User-Agent": "JsInvest-Nasdaq100-Weekly/1.0"})
    with urlopen(req, timeout=timeout) as response:
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


def daily_csv(raw):
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    for row in rows:
        if row["date"] and row["ticker"] == "^NDX":
            yield row["date"], [row[k] for k in NDX_FIELDS]


def ndx_prices(source, start, end):
    if source:
        return list(daily_csv(source.read_bytes()))
    epoch = date(1970, 1, 1)
    params = urlencode({"period1": (start - epoch).days * 86400,
                        "period2": ((end - epoch).days + 1) * 86400, "interval": "1d"})
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/%5ENDX?{params}"
        try:
            response = json.loads(read_source(None, url, timeout=12))["chart"]
            if not response.get("result"):
                continue
            chart = response["result"][0]
            if chart["meta"]["symbol"] != "^NDX" or chart["meta"]["dataGranularity"] != "1d":
                raise ValueError("Unexpected instrument or frequency for NDX")
            quotes = chart["indicators"]["quote"][0]
            return [(datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
                     [quotes[k][i] for k in NDX_FIELDS]) for i, ts in enumerate(chart["timestamp"])]
        except (URLError, TimeoutError, json.JSONDecodeError):
            continue
    return list(daily_csv(read_source(None, NDX_MIRROR)))


def reference_csv(raw, start, end):
    ref = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        day = date.fromisoformat(row["observation_date"])
        if start <= day <= end:
            if day in ref:
                raise ValueError(f"Duplicate NDX reference date {day}")
            ref[day] = None if row["NASDAQ100"] in ("", ".") else float(row["NASDAQ100"])
    if not ref:
        raise ValueError("Empty NDX reference archive")
    return ref


def reference_closes(start, end, source):
    if source:
        return reference_csv(source.read_bytes(), start, end)
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100"
    try:
        return reference_csv(read_source(None, url, timeout=12), start, end)
    except (OSError, KeyError):
        pass
    try:
        url = "https://fred.stlouisfed.org/data/NASDAQ100.txt"
        body = unescape(re.sub(r"<[^>]+>", " ", read_source(None, url, timeout=12).decode("utf-8")))
        pairs = re.findall(r"(\d{4}-\d{2}-\d{2})[\s|]+(\d+\.\d+|\.)(?![\d.])", body)
        if pairs and ("NASDAQ100" in body or "NASDAQ-100" in body):
            text = "observation_date,NASDAQ100\n" + "\n".join(",".join(pair) for pair in pairs)
            return reference_csv(text.encode(), start, end)
    except OSError:
        pass
    # The dated offline reference preserves original FRED sessions and the Nasdaq final close.
    ref = reference_csv((ROOT / "ndx-reference.csv").read_bytes(), start, end)
    last = max(ref)
    if last < end:
        query = urlencode({"assetclass": "index", "fromdate": (last + timedelta(days=1)).isoformat(),
                           "todate": end.isoformat(), "limit": 10000})
        url = "https://api.nasdaq.com/api/quote/NDX/historical?" + query
        data = json.loads(read_source(None, url))["data"]
        if data.get("symbol", "NDX").upper() != "NDX":
            raise ValueError("Unexpected Nasdaq historical symbol")
        for row in data["tradesTable"]["rows"]:
            day = datetime.strptime(row["date"], "%m/%d/%Y").date()
            if not last < day <= end or day in ref:
                raise ValueError(f"Invalid Nasdaq historical date {day}")
            ref[day] = float(row["close"].replace(",", "").replace("$", ""))
    return ref


def index_weeks(positions, today, prices_file=None, reference_file=None, latest_file=None):
    mondays = [d - timedelta(days=d.weekday()) for d in
               (date.fromisoformat(row["date"]) for row in positions)]
    completed = [day for day in mondays if day + timedelta(days=4) < today]
    if not completed:
        return {}
    start, end = completed[0], completed[-1] + timedelta(days=4)
    ref = reference_closes(start, end, reference_file)
    if not reference_file and max(ref) == end - timedelta(days=1):
        archive = reference_csv((ROOT / "ndx-reference.csv").read_bytes(), start, end)
        if end in archive:
            ref[end] = archive[end]
    if max(ref, default=None) != end:
        # FRED can lag Friday's close. Accept Nasdaq's dated final Friday value only.
        if max(ref, default=None) != end - timedelta(days=1):
            raise ValueError("NDX reference archive does not reach the final week")
        page = unescape(re.sub(r"<[^>]+>", " ", read_source(latest_file, NDX_OFFICIAL).decode("utf-8")))
        mark = re.search(r"DATA\s+AS\s+OF\s+(\d+/\d+/\d{4})\s+([\d,]+\.\d+)", page, re.I)
        if not mark or datetime.strptime(mark[1], "%m/%d/%Y").date() != end:
            raise ValueError(f"Nasdaq's final close for {end} is unavailable")
        ref[end] = float(mark[2].replace(",", ""))
    sessions = {}
    for stamp, values in ndx_prices(prices_file, start, end):
        day = date.fromisoformat(stamp)
        if not start <= day <= end:
            continue
        if day in sessions or day.weekday() > 4:
            raise ValueError(f"Invalid NDX session date {day}")
        op, hi, lo, cl = map(float, values)
        if not all(math.isfinite(v) and v > 0 for v in (op, hi, lo, cl)) or not (
                lo <= min(op, cl) <= max(op, cl) <= hi):
            raise ValueError(f"Invalid NDX OHLC on {day}")
        sessions[day] = (op, hi, lo, cl)
    if set(sessions) != {day for day, close in ref.items() if close is not None}:
        raise ValueError("NDX trading dates disagree with the reference series")
    bars = {}
    for monday in completed:
        days = [monday + timedelta(days=i) for i in range(5) if monday + timedelta(days=i) in sessions]
        if not days or abs(sessions[days[-1]][3] - ref[days[-1]]) > 0.02:
            raise ValueError(f"Missing or inconsistent NDX weekly close for {monday}")
        bars[monday] = (days[-1], sessions[days[0]][0], max(sessions[d][1] for d in days),
                        min(sessions[d][2] for d in days), sessions[days[-1]][3])
    return bars


def render(rows, estimates, digest, bars):
    latest = rows[-1]
    table = []
    prev = None
    for row in rows:
        net = row["long"] - row["short"]
        delta = "—" if prev is None else f"{net - prev:+,}"
        day = date.fromisoformat(row["date"])
        bar = bars.get(day - timedelta(days=day.weekday()))
        price_cells = (f"<td>{bar[0]}</td>" + "".join(f"<td>{v:,.2f}</td>" for v in bar[1:])
                       if bar else '<td colspan="5">주봉 마감 대기</td>')
        table.append(f'<tr><td>{row["date"]}</td><td>{row["long"]:,}</td>'
                     f'<td>{row["short"]:,}</td><td>{net:+,}</td><td>{delta}</td>'
                     f'<td>{row["oi"]:,}</td><td>{100 * net / row["oi"]:+.2f}%</td>{price_cells}</tr>')
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
    parser.add_argument("--ndx-daily", type=Path, help="Offline ^NDX daily OHLC CSV")
    parser.add_argument("--ndx-reference", type=Path, help="Offline FRED NASDAQ100 close CSV")
    parser.add_argument("--ndx-latest", type=Path, help="Offline Nasdaq index page for a lagging FRED Friday")
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
    bars = index_weeks(rows, datetime.now(timezone.utc).date(), args.ndx_daily,
                       args.ndx_reference, args.ndx_latest)
    panel = render(rows, estimates, digest, bars)
    output.mkdir(parents=True, exist_ok=True)
    publish_if_changed(history, (json.dumps(snapshot, separators=(",", ":")) + "\n").encode())
    publish_if_changed(output / "index.html", panel.encode())
    print(f'{rows[0]["date"]} .. {rows[-1]["date"]}: {len(rows)} weeks, sha256={digest}')


if __name__ == "__main__":
    main()
