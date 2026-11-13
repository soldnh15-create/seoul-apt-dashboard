// 지도: 단지(좌표가 있을 때) 또는 구 단위 마커. 색 기준을 고를 수 있다. Leaflet + OpenStreetMap
import { $, $$, D, F, esc, get, loadIndex } from '../core.js';

const LEAFLET = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet';
const PAL = ['#4dabf7', '#a5d8ff', '#ffe066', '#ffa94d', '#f03e3e'];
let loading;
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (!loading) loading = new Promise((ok, fail) => {
    document.head.appendChild(Object.assign(document.createElement('link'), { rel: 'stylesheet', href: `${LEAFLET}.css` }));
    document.head.appendChild(Object.assign(document.createElement('script'), { src: `${LEAFLET}.js`, onload: ok, onerror: () => { loading = null; fail(new Error('지도 도구를 불러오지 못했어요')); } }));
  });
  return loading;
}
const METRICS = {
  apt: [['ppy', '평단가', F.man], ['dd', '전고점 대비', F.pct], ['jr', '전세가율', F.pct0], ['n12', '1년 거래량', v => `${F.n(v)}건`]],
  gu: [['ppy', '평단가', F.man], ['chg3m', '3개월 변화', F.pct], ['jr', '전세가율', F.pct0], ['vol3m', '거래량', v => `${F.n(v)}건`]],
};

export async function render(el) {
  const meta = D.meta;
  const [index, sidos] = await Promise.all([loadIndex(), Promise.all(meta.sidos.map(s => get(`sido/${s.code}.json`))), loadLeaflet()]);
  const gus = sidos.flatMap(s => s.gus).filter(g => g.lat && g.lng);
  const hasGeo = meta.features.geo;
  let mode = hasGeo ? 'apt' : 'gu', metric = 'ppy', band = 'all';
  el.innerHTML = `
    <h1>지도</h1>
    <div class="card"><div class="row" style="margin-bottom:10px">
      <div class="chips" id="mode"><button class="chip" data-v="gu">구 단위</button>${hasGeo ? '<button class="chip" data-v="apt">단지 단위</button>' : ''}</div>
      <div class="chips" id="metric"></div>
      <select id="band" aria-label="면적">${[['all', '전체 면적'], ...meta.bands.map(b => [b.key, b.label])].map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join('')}</select></div>
      <div class="map" id="map"></div>
      <div class="legend"><span id="lg-lo"></span><i style="background:linear-gradient(90deg,${PAL.join(',')})"></i><span id="lg-hi"></span><span id="lg-n" style="margin-left:auto"></span></div>
      ${hasGeo ? '' : '<p class="note">단지 좌표 데이터가 아직 없어 구 단위로만 보여 드려요.</p>'}</div>`;
  const L = window.L;
  const map = L.map($('#map', el), { preferCanvas: true }).setView([37.5665, 126.978], 11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 기여자' }).addTo(map);
  const layer = L.layerGroup().addTo(map);
  const draw = () => {
    layer.clearLayers();
    const defs = METRICS[mode];
    if (!defs.some(d => d[0] === metric)) metric = 'ppy';
    const [, label, fmt] = defs.find(d => d[0] === metric);
    $('#metric', el).innerHTML = defs.map(([k, l]) => `<button class="chip ${k === metric ? 'on' : ''}" data-v="${k}">${l}</button>`).join('');
    $$('#mode .chip', el).forEach(b => b.classList.toggle('on', b.dataset.v === mode));
    $('#band', el).hidden = mode !== 'apt';
    const rows = (mode === 'apt' ? index.filter(o => o.lat && o.lng && !o.stale && (band === 'all' || o.band === band)) : gus).filter(o => o[metric] != null);
    const vals = rows.map(o => o[metric]).sort((a, b) => a - b);
    const qt = p => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
    const cuts = [0.2, 0.4, 0.6, 0.8].map(qt);
    const color = v => PAL[cuts.filter(c => v > c).length];
    for (const o of rows) {
      const m = L.circleMarker([o.lat, o.lng], { radius: mode === 'gu' ? 16 : 6, color: '#fff', weight: 1, fillColor: color(o[metric]), fillOpacity: .9 });
      m.bindPopup(mode === 'gu'
        ? `<b>${esc(o.name)}</b><br>평단가 ${F.man(o.ppy)} · ${F.pct(o.chg3m)}<br>전세가율 ${F.pct0(o.jr)} · 거래 ${F.n(o.vol3m)}건<br><a href="#/gu/${o.sgg}">자세히 →</a>`
        : `<b>${esc(o.name)}</b> ${o.a}㎡<br>${F.eok(o.price)} · 평단가 ${F.man(o.ppy)}<br>고점 대비 ${F.pct(o.dd)} · 전세가율 ${F.pct0(o.jr)}<br><a href="${o.href}">자세히 →</a>`);
      if (mode === 'gu') m.bindTooltip(`${esc(o.name)}<br>${fmt(o[metric])}`, { permanent: true, direction: 'center', className: 'gu-tip', opacity: .9 });
      m.addTo(layer);
    }
    $('#lg-lo', el).textContent = vals.length ? `${label} ${fmt(vals[0])}` : '';
    $('#lg-hi', el).textContent = vals.length ? fmt(vals[vals.length - 1]) : '';
    $('#lg-n', el).textContent = `${F.n(rows.length)}곳`;
  };
  el.onclick = e => {
    const b = e.target.closest('.chip'); if (!b) return;
    if (b.closest('#mode')) mode = b.dataset.v; else if (b.closest('#metric')) metric = b.dataset.v; else return;
    draw();
  };
  $('#band', el).onchange = e => { band = e.target.value; draw(); };
  draw();
  setTimeout(() => map.invalidateSize(), 60);
}
