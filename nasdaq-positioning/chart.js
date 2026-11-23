(() => {
  const canvas = document.querySelector("#plot");
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const field = document.querySelector("#field");
  const period = document.querySelector("#period");
  const point = document.querySelector("#point");
  const fmt = new Intl.NumberFormat("ko-KR");
  const signed = value => (value > 0 ? "+" : "") + fmt.format(value);
  const rows = Array.from(document.querySelectorAll("tbody tr"), tr => {
    const [date, long, short, net, , oi] = Array.from(tr.cells, cell => cell.textContent.replaceAll(",", ""));
    return {date, long: Number(long), short: Number(short), net: Number(net), share: 100 * Number(net) / Number(oi)};
  }).reverse();
  let shown = rows;
  let cursor = rows.length - 1;
  const left = 60, right = 12;

  function draw() {
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (width <= left + right || !shown.length) return;
    const scale = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    const gross = field.value === "gross";
    const keys = gross ? ["long", "short"] : [field.value];
    const values = shown.flatMap(row => keys.map(key => row[key]));
    const lo = Math.min(0, ...values), hi = Math.max(0, ...values);
    const x = i => left + (width - left - right) * i / Math.max(shown.length - 1, 1);
    const y = value => 12 + (hi - value) * (height - 38) / (hi - lo || 1);
    ctx.font = "11px system-ui";
    for (const v of new Set([lo, 0, hi])) {
      ctx.strokeStyle = v === 0 ? "#647787" : "#2e3a44";
      ctx.beginPath(); ctx.moveTo(left, y(v)); ctx.lineTo(width - right, y(v)); ctx.stroke();
      ctx.fillStyle = "#bdcad4"; ctx.textAlign = "right";
      ctx.fillText(field.value === "share" ? v.toFixed(1) + "%" : fmt.format(v), left - 6, y(v) + 4);
    }
    keys.forEach((key, j) => {
      ctx.strokeStyle = j ? "#ffab82" : "#76d6d1";
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      shown.forEach((row, i) => { if (i === 0) ctx.moveTo(x(i), y(row[key])); else ctx.lineTo(x(i), y(row[key])); });
      ctx.stroke();
    });
    ctx.lineWidth = 1; ctx.strokeStyle = "#889aaa"; ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(x(cursor), 10); ctx.lineTo(x(cursor), height - 22); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#bdcad4"; ctx.textAlign = "left"; ctx.fillText(shown[0].date, left, height - 4);
    ctx.textAlign = "right"; ctx.fillText(shown.at(-1).date, width - right, height - 4);
    const row = shown[cursor];
    point.value = row.date + " · " + (gross ? "롱 " + fmt.format(row.long) + " / 숏 " + fmt.format(row.short) + "계약"
      : field.value === "share" ? "순포지션/OI " + signed(Number(row.share.toFixed(2))) + "%" : "순포지션 " + signed(row.net) + "계약");
    canvas.dataset.rendered = "true";
  }
  function reset() {
    shown = Number(period.value) ? rows.slice(-Number(period.value)) : rows;
    cursor = shown.length - 1;
    document.querySelector("#chart-title").textContent = {net:"레버리지 펀드 순포지션", share:"전체 미결제약정 대비 순포지션", gross:"롱 (청록) · 숏 (주황)"}[field.value];
    draw();
  }
  for (const input of [field, period]) input.addEventListener("change", reset);
  canvas.addEventListener("pointermove", event => {
    const rect = canvas.getBoundingClientRect();
    const fraction = (event.clientX - rect.left - left) / (rect.width - left - right);
    cursor = Math.min(shown.length - 1, Math.max(0, Math.round(fraction * (shown.length - 1)))); draw();
  });
  canvas.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    cursor = Math.min(shown.length - 1, Math.max(0, cursor + (event.key === "ArrowLeft" ? -1 : 1))); draw();
  });
  new ResizeObserver(draw).observe(canvas);
  reset();
})();
