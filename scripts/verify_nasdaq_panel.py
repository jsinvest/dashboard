"""Verify the published CTA market menus, weekly charts, and related CFTC panel."""

import argparse
import os
import tempfile
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://jsinvest.github.io/dashboard/"


def read(url):
    with urlopen(Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as response:
        return response.read().decode("utf-8")


def render_dom(chrome, url, budget=5000, timeout=45):
    # Isolate headless QA from interactive profiles; keep normal browser security.
    with tempfile.TemporaryDirectory(prefix="nasdaq-cta-qa-") as profile:
        run = subprocess.run([chrome, "--headless", "--disable-gpu", "--no-first-run",
                              "--user-data-dir=" + profile,
                              "--virtual-time-budget=" + str(budget), "--dump-dom", url],
                             capture_output=True, check=True, timeout=timeout)
    return run.stdout.decode("utf-8").replace("\r\n", "\n")


def verify_cta_navigation(chrome, query):
    expected = (ROOT / "cta-trend/index.html").read_text(encoding="utf-8")
    payload = json.loads(expected.split('id="data">', 1)[1].split("</script>", 1)[0])

    def dom(url):
        return render_dom(chrome, url, 3500, 60)

    def tag(html, selector):
        return next((m for m in re.findall(r"<(?:button|iframe|div)\b[^>]*>", html) if selector in m), "")

    for market, name in (("kospi", "코스피"), ("nasdaq", "나스닥100")):
        route = SITE + query + "#cta-trend/" + market
        dashboard = dom(route)
        main = tag(dashboard, 'data-tab="cta-trend"')
        selected = tag(dashboard, f'data-cta-market="{market}"')
        frame = tag(dashboard, 'id="cta-trend-panel"')
        if ("active" not in main or 'aria-pressed="true"' not in selected or
                f'src="cta-trend/index.html?embedded=1#{market}"' not in frame or
                'id="nasdaq-weekly-positions"' in dashboard):
            raise SystemExit(f"CTA dashboard route failed: {market}")
        rendered = dom(SITE + "cta-trend/index.html" + query + "#" + market)
        first, last = payload[market]["weeks"][0], payload[market]["weeks"][-1]
        if (f'<h2 id="market-title">{name}</h2>' not in rendered or
                f'{first[0]} ~ {last[0]} 마감' not in rendered or
                f'id="score">{last[5]:+.1f}<' not in rendered or
                '<line id="cursor"' not in rendered):
            raise SystemExit(f"CTA weekly chart failed: {market}")
        print(f"PUBLIC_CTA_OK {market} | {first[0]} to {last[0]} | {len(payload[market]['weeks'])} weeks | {last[5]:+.1f}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--attempts", type=int, default=25, choices=range(1, 26))
    args = parser.parse_args(argv)
    data = json.loads((ROOT / "nasdaq-positioning/history.json").read_bytes())
    expected_panel = (ROOT / "nasdaq-positioning/index.html").read_text(encoding="utf-8")
    table = re.search(r"<tbody>(.*?)</tbody>", expected_panel, re.S)[1]
    model_rows = re.findall(r"<td>(\d{4}-\d{2}-\d{2})</td>(?:<td>[\d,.]+</td>){3}"
                            r"<td>([\d,.]+)</td><td>([+-]\d+\.\d)</td></tr>", table)
    if not model_rows or any(abs(float(score)) > 100 for _, _, score in model_rows):
        raise SystemExit("Missing or invalid CTA score for completed NDX bars")
    model_date, model_close, score = model_rows[0]
    digest, latest = data["sha256"], data["as_of"]
    final = data["history"][-1]
    net = final["long"] - final["short"]
    label = ("순숏" if net < 0 else "순롱" if net > 0 else "중립") + f" {abs(net):,}계약"
    for attempt in range(args.attempts):
        query = f"?v={digest[:12]}-{time.time_ns()}"
        panel_url = SITE + "nasdaq-positioning/" + query
        try:
            root = read(SITE + query)
            panel = read(panel_url)
            if ('data-tab-panel="cta-trend"' in root and 'href="nasdaq-positioning/"' in root and
                    'src="cta-trend/index.html?embedded=1#kospi"' in root and
                    'id="nasdaq-weekly-positions"' not in root and
                    f'content="{digest}"' in panel and f"<time>{latest}</time>" in panel and
                    label in panel and table in panel and 'id="ndx-plot"' in panel):
                break
        except OSError as exc:
            print(type(exc).__name__, flush=True)
        if attempt == args.attempts - 1:
            raise SystemExit("Published panel does not match this snapshot")
        time.sleep(12)
    chrome = str(args.browser) if args.browser else shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("msedge")
    if not chrome and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"
        chrome = str(candidate) if candidate.is_file() else None
    if not chrome:
        raise SystemExit("A headless DOM renderer is required")
    if not Path(chrome).is_file():
        raise SystemExit("The selected DOM renderer does not exist")
    verify_cta_navigation(chrome, query)
    dom = render_dom(chrome, panel_url)
    canvases = re.findall(r'<canvas\b[^>]*>', dom)
    paired = [tag for tag in canvases if 'data-rendered="true"' in tag and
              f'data-week="{model_date}"' in tag and f'data-weeks="{len(model_rows)}"' in tag]
    if (len(paired) != 2 or not all(any(f'id="{key}"' in tag for tag in paired) for key in ("plot", "ndx-plot")) or
            f"<time>{latest}</time>" not in dom or label not in dom or
            not any('id="plot"' in tag and 'data-series="cta"' in tag for tag in paired) or
            table not in dom or dom.count("<tr><td>") != table.count("<tr><td>")):
        raise SystemExit("Rendered chart or history does not match")
    detail = re.search(r'<output id="ndx-point">([^<]+)</output>', dom)
    model_point = re.search(r'<output id="point">([^<]+)</output>', dom)
    display_score = "0.0" if float(score) == 0 else score
    if (not detail or not all(v in detail[1] for v in (model_date, model_close)) or
            not model_point or not all(v in model_point[1] for v in (model_date, "CTA", display_score))):
        raise SystemExit("Rendered red line and NDX readouts must match the same completed week")
    print(f'PUBLIC_DOM_OK {latest} | {label} | {data["weeks"]} CFTC weeks | '
          f'CTA {model_date} {score} / {len(model_rows)} weeks | NDX {model_close} | sha256={digest}')


if __name__ == "__main__":
    main()
