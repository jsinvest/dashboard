'use strict';
// Refresh the initial dashboard view after the dated JSON series have been validated.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const folder = process.argv[2] || path.resolve(__dirname, '../cta-trend/foreign-futures');
const load = name => JSON.parse(fs.readFileSync(path.join(folder, name), 'utf8'));
const base = load('data.json');
const comp = load('comparison.json');
assert(comp.daily.length > 0 && comp.daily.at(-1).d === comp.asOf, 'Latest daily observation must match asOf');
let previous = '';
for (const row of comp.daily) {
  assert(/^\d{4}-\d{2}-\d{2}$/.test(row.d) && row.d > previous, 'Daily dates must be unique and ascending');
  assert(['iv','iq','ic','fv','fq','fc'].every(k => Number.isSafeInteger(row[k])), 'Daily flows must be integer amounts or contracts');
  assert(Number.isFinite(comp.index[row.d]) && comp.index[row.d] > 0, 'Missing matching KOSPI 200 close for '+row.d);
  previous = row.d;
}
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(folder, 'view.js'), 'utf8'), ctx);
const state = {owner:'foreign', unit:'v', freq:'week', band:'percentile', overlay:true};
const initial = ctx.drawPage(base,comp,state,964).html;
for (const owner of ['foreign','institution']) {
  const cash = ctx.series(base,comp,owner,'c');
  for (const band of ['fixed','percentile']) {
    const bounds = ctx.bandFor(cash.history,'c',band);
    assert(bounds && bounds.every(Number.isFinite) && bounds[0] < bounds[1], 'Invalid '+owner+' cash band');
    const result = ctx.drawPage(base,comp,{...state,owner,unit:'c',band,freq:'day'},420);
    assert(result.charts[1].list.at(-1)?.date === comp.asOf, 'Expected latest daily cash observation');
    assert(!/NaN|undefined|Infinity/.test(result.html), 'Invalid chart data');
  }
}
const target = path.join(folder,'index.html');
const old = fs.readFileSync(target,'utf8');
const begin = '<div id="app">', end = '</div></main>';
const start = old.indexOf(begin), stop = old.indexOf(end,start+begin.length);
assert(start >= 0 && stop >= 0, 'Expected dashboard container');
const html = old.slice(0,start+begin.length)+initial+old.slice(stop);
if (old !== html) fs.writeFileSync(target,html,'utf8');
console.log(comp.asOf+' · '+comp.daily.length+' daily observations · '+(old===html?'already current':'snapshot refreshed'));

