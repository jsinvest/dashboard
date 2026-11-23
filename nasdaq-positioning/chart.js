(() => {
  const positions = document.querySelector("#plot");
  const prices = document.querySelector("#ndx-plot");
  const field = document.querySelector("#field");
  const period = document.querySelector("#period");
  const fmt = new Intl.NumberFormat("ko-KR");
  const priceFmt = new Intl.NumberFormat("ko-KR", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const signed = value => (value > 0 ? "+" : "") + fmt.format(value);
  const rows = Array.from(document.querySelectorAll("tbody tr"), tr => {
    const [stamp, long, short, net, , oi, , end, open, high, low, close, score] =
      Array.from(tr.cells, cell => cell.textContent.replaceAll(",", ""));
    const bar = close === undefined ? null : {end, open: +open, high: +high, low: +low, close: +close};
    return {date: stamp === "미발표" ? null : stamp, long: +long, short: +short, net: +net,
      share: 100 * Number(net) / Number(oi), bar, cta: score === undefined ? null : Number(score)};
  }).reverse();
  let shown = rows;
  let cursor = rows.length - 1;
  const left = 62, right = 10;
  const clamp = i => Math.max(0, Math.min(shown.length - 1, i));
  const chartDate = row => field.value === "cta" ? row.bar.end : row.date;

  function frame(canvas, low, high, ticks, label, timeLabels) {
    const ctx = canvas.getContext("2d");
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!ctx || width <= left + right || !shown.length) return null;
    const scale = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
    }
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const bottom = height - (timeLabels ? 25 : 10);
    const step = (width - left - right) / shown.length;
    const x = i => left + step * (i + 0.5);
    const y = v => bottom - (v - low) * (bottom - 12) / (high - low || 1);
    function line(x1, y1, x2, y2, color) {
      ctx.strokeStyle = color;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    ctx.lineWidth = 1;
    ctx.font = "11px system-ui";
    ctx.fillStyle = "#bdcad4";
    ctx.textAlign = "right";
    for (const v of new Set(ticks)) {
      line(left, y(v), width - right, y(v), v === 0 ? "#647787" : "#2e3a44");
      ctx.fillText(label(v), left - 6, y(v) + 4);
    }
    const count = Math.min(shown.length, Math.max(2, Math.floor((width-left-right)/100)));
    for (let j = 0; j < count; j++) {
      const i = Math.round(j * (shown.length - 1) / Math.max(1, count - 1));
      line(x(i), 10, x(i), bottom, "#23313c");
      if (timeLabels) {
        ctx.textAlign = j === 0 ? "left" : j === count - 1 ? "right" : "center";
        const stamp = chartDate(shown[i]);
        ctx.fillText(shown.length <= 52 ? stamp.slice(2) : stamp.slice(0, 7), x(i), height - 5);
      }
    }
    return {ctx, x, y, step, line, bottom};
  }

  function mark(canvas, plot) {
    const {ctx, x, bottom, line} = plot;
    ctx.lineWidth = 1; ctx.setLineDash([3, 4]);
    line(x(cursor), 9, x(cursor), bottom, "#d5e2ed");
    ctx.setLineDash([]);
    canvas.dataset.rendered = "true";
    canvas.dataset.week = chartDate(shown[cursor]);
    canvas.dataset.weeks = String(shown.length);
  }

  function draw() {
    if (!shown.length) return;
    const model = field.value === "cta";
    const gross = field.value === "gross";
    const keys = gross ? ["long", "short"] : [field.value];
    const values = shown.flatMap(row => keys.map(key => row[key]));
    const lo = model ? -100 : Math.min(0, ...values), hi = model ? 100 : Math.max(0, ...values);
    const upper = frame(positions, lo, hi, [lo, 0, hi],
      v => model ? ({"100":"+100 롱", "0":"0 중립", "-100":"−100 숏"})[v] :
        field.value === "share" ? v.toFixed(1) + "%" : fmt.format(v), false);
    if (!upper) return;
    keys.forEach((key, j) => {
      const {ctx, x, y} = upper;
      ctx.strokeStyle = model ? "#ff737a" : j ? "#ffab82" : "#76d6d1";
      ctx.lineWidth = model ? 2.3 : 1.8; ctx.beginPath();
      shown.forEach((row, i) => { if (i === 0) ctx.moveTo(x(i), y(row[key])); else ctx.lineTo(x(i), y(row[key])); });
      ctx.stroke();
    });
    mark(positions, upper);
    positions.dataset.series = field.value;
    const bars = shown.map(row => row.bar).filter(Boolean);
    if (bars.length) {
      const low = Math.min(...bars.map(b => b.low)), high = Math.max(...bars.map(b => b.high));
      const lower = frame(prices, low, high, [low, (low + high) / 2, high], v => fmt.format(Math.round(v)), true);
      if (lower) {
        const {ctx, x, y, step, line} = lower;
        const bodyWidth = Math.max(0.8, Math.min(14, step * 0.72));
        shown.forEach(({bar}, i) => {
          if (!bar) return;
          const color = bar.close >= bar.open ? "#75d8b6" : "#efa489";
          line(x(i), y(bar.high), x(i), y(bar.low), color);
          ctx.fillStyle = color;
          ctx.fillRect(x(i) - bodyWidth / 2, Math.min(y(bar.open), y(bar.close)),
            bodyWidth, Math.max(1, Math.abs(y(bar.open) - y(bar.close))));
        });
        mark(prices, lower);
      }
    }
    const row = shown[cursor];
    document.querySelector("#point").value = model ?
      row.bar.end + " 마감 · CTA 추세 " + (row.cta > 0 ? "+" : "") + row.cta.toFixed(1) + "점" :
      row.date + " 집계 · " + (gross ?
      "롱 " + fmt.format(row.long) + " / 숏 " + fmt.format(row.short) + "계약" :
      field.value === "share" ? "순포지션/OI " + signed(Number(row.share.toFixed(2))) + "%" :
      "순포지션 " + signed(row.net) + "계약");
    const b = row.bar;
    document.querySelector("#ndx-point").value = b ?
      b.end + " 마감 · 시 " + priceFmt.format(b.open) + "　고 " + priceFmt.format(b.high) +
      "　저 " + priceFmt.format(b.low) + "　종 " + priceFmt.format(b.close) : "주봉 마감 대기";
  }

  function reset(keep) {
    const eligible = rows.filter(row => field.value === "cta" ? row.bar && row.cta !== null : row.date);
    shown = Number(period.value) ? eligible.slice(-Number(period.value)) : eligible;
    const index = shown.indexOf(keep);
    cursor = index < 0 ? shown.length - 1 : index;
    draw();
  }
  period.addEventListener("change", () => reset());
  field.addEventListener("change", () => {
    const model = field.value === "cta";
    document.querySelector("#model-summary").hidden = !model;
    document.querySelector("#cftc-summary").hidden = model;
    document.querySelector("#cta-key").hidden = !model;
    document.querySelector("#chart-title").textContent =
      {cta:"CTA 추세추종 점수 · 자체 모델", net:"레버리지 펀드 순포지션", share:"전체 미결제약정 대비 순포지션", gross:"롱 (청록) · 숏 (주황)"}[field.value];
    reset(shown[cursor]);
  });
  for (const canvas of [positions, prices]) {
    function select(event) {
      const rect = canvas.getBoundingClientRect();
      cursor = clamp(Math.floor((event.clientX - rect.left - left) / (rect.width - left - right) * shown.length));
      draw();
    }
    canvas.addEventListener("pointermove", select);
    canvas.addEventListener("pointerdown", select);
    canvas.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault(); cursor = clamp(cursor + (event.key === "ArrowLeft" ? -1 : 1)); draw();
    });
  }
  new ResizeObserver(draw).observe(positions);
  const iframe = window.frameElement;
  if (iframe && iframe.id === "nasdaq-weekly-positions") {
    new ResizeObserver(() => {
      iframe.style.height = Math.ceil(document.body.getBoundingClientRect().height + 3) + "px";
    }).observe(document.body);
  }
  reset();
})();
