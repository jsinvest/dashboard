"""Read the published US tab and its rendered NQ panel, matching the checked-in snapshot."""

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


def main():
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
    for attempt in range(25):
        query = f"?v={digest[:12]}-{time.time_ns()}"
        panel_url = SITE + "nasdaq-positioning/" + query
        try:
            root = read(SITE + query)
            panel = read(panel_url)
            if ('data-tab-panel="global"' in root and 'src="nasdaq-positioning/"' in root and
                    f'content="{digest}"' in panel and f"<time>{latest}</time>" in panel and
                    label in panel and table in panel and 'id="ndx-plot"' in panel):
                break
        except OSError as exc:
            print(type(exc).__name__, flush=True)
        if attempt == 24:
            raise SystemExit("Published panel does not match this snapshot")
        time.sleep(12)
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise SystemExit("A headless DOM renderer is required")
    result = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu",
                             "--virtual-time-budget=5000", "--dump-dom", panel_url],
                            capture_output=True, timeout=45, check=True)
    dom = result.stdout.decode("utf-8")
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
