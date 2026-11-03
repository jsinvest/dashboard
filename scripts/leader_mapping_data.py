import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
from pathlib import Path

DATE = None
BASE = None
SCAN = None


def n(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def txt(value):
    if value is None or pd.isna(value):
        return ""
    return str(value)


def fmt(value, digits=1):
    return f"{float(value):,.{digits}f}"


def signed(value, suffix="%"):
    value = float(value)
    return f"{'+' if value >= 0 else '−'}{abs(value):,.2f}{suffix}"


def read_xlsx(date):
    path = os.path.join(BASE, f"sector_stock_leaders_{date}.xlsx")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    sector = pd.read_excel(path, sheet_name=0, dtype={12: str})
    stock = pd.read_excel(path, sheet_name=1, dtype={5: str})
    excluded = pd.read_excel(path, sheet_name=2, dtype={0: str})
    sector.columns = [f"c{i}" for i in range(len(sector.columns))]
    stock.columns = [f"c{i}" for i in range(len(stock.columns))]
    excluded.columns = [f"c{i}" for i in range(len(excluded.columns))]
    return path, sector, stock, excluded


def available_dates():
    dates = []
    for name in os.listdir(BASE):
        m = re.fullmatch(r"sector_stock_leaders_(\d{8})\.xlsx", name)
        if m and m.group(1) <= DATE:
            dates.append(m.group(1))
    return sorted(set(dates))


def scan_map():
    if not os.path.exists(SCAN):
        return {}, {"rows": 0, "sameDate": 0, "pass": []}
    scan = pd.read_csv(SCAN, encoding="utf-8-sig")
    by_code = {}
    pass_rows = []
    same_date = 0
    for _, row in scan.iterrows():
        code = str(row.get("code", "")).split(".")[0].zfill(6)
        signal_date = str(row.get("signal_date", "")).split(".")[0]
        if signal_date != DATE:
            continue
        same_date += 1
        is_pass = row.get("common_filter_pass") is True or str(row.get("common_filter_pass")).lower() == "true"
        item = {
            "signalType": txt(row.get("signal_type")),
            "grade": txt(row.get("effective_grade") or row.get("base_grade")),
            "pass": bool(is_pass),
            "market": txt(row.get("market")),
            "name": txt(row.get("name")),
        }
        existing = by_code.get(code)
        if existing is None or (item["pass"] and not existing["pass"]):
            by_code[code] = item
        if item["pass"]:
            pass_rows.append([code, item["name"], item["market"], item["signalType"], item["grade"]])
    return by_code, {"rows": len(scan), "sameDate": same_date, "pass": pass_rows}


def sector_stats(stock):
    result = {"KOSPI": [], "KOSDAQ": []}
    for market in result:
        rows = stock[stock.c6.astype(str).str.upper().eq(market) & ~stock.c4.astype(str).str.contains("스팩|SPAC", case=False, regex=True)]
        for sector_name, g in rows.groupby("c1"):
            rets = [n(x) for x in g.c8]
            rss = [n(x) for x in g.c9]
            tvs = [n(x) for x in g.c10]
            volx = [n(x) for x in g.c12]
            sample = len(g)
            up_pct = sum(v > 0 for v in rets) / sample * 100 if sample else 0
            med_rs = float(pd.Series(rss).median()) if rss else 0
            total_tv = sum(tvs)
            vol_pct = sum(v >= 1 for v in volx) / sample * 100 if sample else 0
            lead = g.sort_values(["c7", "c10"], ascending=False).iloc[0]
            score = (max(med_rs, -5) + 5) * 7 + min(total_tv / 2000, 1) * 20 + up_pct * 0.25 + vol_pct * 0.1 + min(sample / 10, 1) * 10
            result[market].append({
                "sector": txt(sector_name),
                "rank": 0,
                "score": round(score, 3),
                "sample": sample,
                "upPct": round(up_pct, 1),
                "medianRs": round(med_rs, 2),
                "tradingValue": round(total_tv, 1),
                "volPct": round(vol_pct, 1),
                "leader": txt(lead.c4),
                "leaderScore": round(n(lead.c7), 1),
            })
        result[market].sort(key=lambda x: x["score"], reverse=True)
        for i, item in enumerate(result[market], 1):
            item["rank"] = i
    return result


def find_sector(stats, market, sector):
    for item in stats[market]:
        if item["sector"] == sector:
            return item
    raise KeyError((market, sector))


def stock_rows(stock, market, sector_name, count, scan_by_code):
    g = stock[(stock.c6.astype(str).str.upper() == market) & (stock.c1 == sector_name)].copy()
    g = g.sort_values(["c7", "c10"], ascending=False).head(count)
    out = []
    for i, row in enumerate(g.itertuples(index=False), 1):
        code = str(getattr(row, "c5")).split(".")[0].zfill(6)
        sc = scan_by_code.get(code)
        ret = n(getattr(row, "c8"))
        rs = n(getattr(row, "c9"))
        vol = n(getattr(row, "c12"))
        state = "가격·RS·거래 동반" if ret > 0 and rs > 0 and vol >= 1 else ("지수 대비 강세" if ret > 0 and rs > 0 else ("지수보다 약함" if rs < 0 else "관찰"))
        if sc and sc["pass"]:
            state = f"{state}·V2 통과"
        v2 = f"9/8 {sc['signalType']} {sc['grade']}등급 · 품질필터 {'통과' if sc['pass'] else '미통과'}" if sc else "9/8 교차신호 없음"
        out.append({
            "priority": i,
            "leaderScore": f"{n(getattr(row, 'c7')):.1f}",
            "name": txt(getattr(row, "c4")),
            "market": market,
            "state": state,
            "kind": "leader" if i <= 2 and ret > 0 else "",
            "metric": f"{ret:+.2f}% · {n(getattr(row, 'c10')):,.1f}억 · RS {rs:+.2f}%p · {vol:.2f}배 · 수급점수 {n(getattr(row, 'c15')):+.2f}".replace("-", "−"),
            "v2": v2,
        })
    return out


def cumulative(all_stats, dates):
    result = {}
    for market in ["KOSPI", "KOSDAQ"]:
        days = []
        freq = Counter()
        top5 = Counter()
        rank1 = Counter()
        leaders = defaultdict(Counter)
        detail = defaultdict(list)
        tree = {}
        for date in dates:
            picks = all_stats[date][market][:15]
            days.append([f"{int(date[4:6])}/{int(date[6:8])}", [[p["rank"], p["sector"], p["leader"]] for p in picks[:3]]])
            for p in picks:
                freq[p["sector"]] += 1
                if p["rank"] <= 5:
                    top5[p["sector"]] += 1
                if p["rank"] == 1:
                    rank1[p["sector"]] += 1
                leaders[p["sector"]][p["leader"]] += 1
                detail[p["sector"]].append([date, p["rank"], p["leader"], p["leaderScore"], "섹터 대표주"])
                tree.setdefault(p["sector"], []).append((date, p["rank"]))
        order = sorted(freq, key=lambda s: (-freq[s], -top5[s], -rank1[s], sum(r for _, r in tree[s]) / len(tree[s]), s))
        result[market] = {
            "days": days,
            "frequency": [[s, freq[s], top5[s], rank1[s]] for s in order[:6]],
            "tree": [[s, freq[s], top5[s], rank1[s], tree[s][-1][0], tree[s][-1][1], round(sum(r for _, r in tree[s]) / len(tree[s]), 1)] for s in order[:15]],
            "history": {s: {"l": leaders[s].most_common(5), "d": detail[s]} for s in order},
        }
    return result


def j(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def top_names(daily, key, count=2):
    return "·".join([s["name"] for s in daily[key]["stocks"][:count]])


def stat_text(s):
    return f"{s['sample']}종목 중 {round(s['sample'] * s['upPct'] / 100)}상승 · RS {signed(s['medianRs'], '%p')}"


