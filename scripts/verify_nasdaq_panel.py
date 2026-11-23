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
                    label in panel and panel.count("<tr><td>") == data["weeks"]):
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
    if (not re.search(r'<canvas\b[^>]*data-rendered="true"', dom) or
            f"<time>{latest}</time>" not in dom or label not in dom or
            dom.count("<tr><td>") != data["weeks"]):
        raise SystemExit("Rendered chart or history does not match")
    print(f'PUBLIC_DOM_OK {latest} | {label} | {data["weeks"]} weeks | sha256={digest}')


if __name__ == "__main__":
    main()
