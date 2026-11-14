// 공통 도구: 형식, 검색(초성·오타), 저장(localStorage), 데이터 불러오기, 표, 차트
export const PY = 3.3058;
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = new Intl.NumberFormat('ko-KR');

export const F = {
  n: v => v == null ? '-' : nf.format(v),
  eok: v => {
    if (v == null) return '-';
    const s = v < 0 ? '-' : '', a = Math.abs(v), e = Math.floor(a / 10000), m = Math.round(a % 10000);
    return s + (e ? `${e}억${m ? ' ' + nf.format(m) : ''}` : `${nf.format(m)}만`);
  },
  eokS: v => v == null ? '-' : Math.abs(v) >= 10000 ? `${+(v / 10000).toFixed(2)}억` : `${nf.format(v)}만`,
  pct: v => v == null ? '-' : `${v > 0 ? '+' : ''}${(+v).toFixed(1)}%`,
  pct0: v => v == null ? '-' : `${(+v).toFixed(1)}%`,
  man: v => v == null ? '-' : `${nf.format(v)}만`,
  m: v => v == null ? '-' : `${nf.format(v)}m`,
  yr: v => v == null ? '-' : `${v}년`,
};
export const cls = v => (v == null || v === 0) ? '' : v > 0 ? 'up' : 'down';
export const debounce = (fn, ms = 200) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const median = xs => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
export function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 2200); }

// ── 검색: 초성 + 오타 허용 ─────────────────────────────
const CHO = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];
export const normName = s => String(s || '').toLowerCase().replace(/[\s()·\-.,]/g, '');
export const chosung = s => [...normName(s)].map(ch => { const c = ch.charCodeAt(0) - 0xAC00; return c >= 0 && c <= 11171 ? CHO[Math.floor(c / 588)] : ch; }).join('');
function editDist(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]; let best = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (cur[j] < best) best = cur[j];
    }
    if (best > max) return max + 1;
    prev = cur;
  }
  return prev[b.length];
}
/** items: [{name, _n(정규화), _c(초성)}] → 점수순 */
export function searchItems(items, query, limit = 12) {
  const q = normName(query);
  if (!q) return [];
  const onlyCho = /^[ㄱ-ㅎ]+$/.test(q);
  const out = [];
  for (const it of items) {
    let s = -1;
    if (onlyCho) { const i = it._c.indexOf(q); if (i === 0) s = 1; else if (i > 0) s = 2; }
    else {
      const i = it._n.indexOf(q);
      if (i === 0) s = 0; else if (i > 0) s = 1;
      else if (q.length >= 3) {  // 오타: 이름 앞부분과 1~2글자 차이까지
        const max = q.length >= 5 ? 2 : 1;
        const d = Math.min(editDist(q, it._n.slice(0, q.length), max), editDist(q, it._n, max));
        if (d <= max) s = 3 + d;
      }
    }
    if (s >= 0) out.push([s, it]);
  }
  out.sort((a, b) => a[0] - b[0] || (b[1].n12 || 0) - (a[1].n12 || 0) || a[1].name.localeCompare(b[1].name, 'ko'));
  return out.slice(0, limit).map(x => x[1]);
}

// ── 내 브라우저 저장(서버 없음) ─────────────────────────
const KEY = 'gnbg-apt-v1';
function readStore() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
export const S = Object.assign({ watch: {}, presets: { screener: [], score: [] }, weights: null, visit: null, prevVisit: null }, readStore());
export function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); return true; } catch (e) { return false; } }
export function exportSettings() {
  const blob = new Blob([JSON.stringify({ app: KEY, exported: new Date().toISOString(), data: S }, null, 1)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: '강남박공_실거래_내설정.json' });
  a.click(); URL.revokeObjectURL(a.href);
}
export function importSettings(text) {
  const j = JSON.parse(text);
  if (j.app !== KEY || typeof j.data !== 'object') throw new Error('이 사이트의 설정 파일이 아닙니다');
  for (const k of ['watch', 'presets', 'weights', 'theme']) if (j.data[k] != null) S[k] = j.data[k];
  save();
}

// ── 주소(URL)에 조건 담기 ──────────────────────────────
export const encState = o => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
export const decState = s => { try { return JSON.parse(decodeURIComponent(escape(atob(s.replace(/-/g, '+').replace(/_/g, '/'))))); } catch (e) { return null; } };
export function setQuery(path, q) {
  const qs = Object.entries(q).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  history.replaceState(null, '', `#${path}${qs ? '?' + qs : ''}`);
}
export async function share(title) {
  const url = location.href;
  try { if (navigator.share) { await navigator.share({ title, url }); return; } } catch (e) { /* 취소 */ }
  try { await navigator.clipboard.writeText(url); toast('주소를 복사했어요'); } catch (e) { prompt('이 주소를 복사하세요', url); }
}

// ── 데이터 ────────────────────────────────────────────
const cache = new Map();
let dataVer = '';   // meta.json 의 갱신 시각. 다른 데이터 주소에 붙여서 갱신 뒤에 예전 숫자가 남지 않게 한다.
export function get(path) {
  if (!cache.has(path)) {
    const isMeta = path === 'meta.json';
    const url = `data/${path}${!isMeta && dataVer ? `?v=${dataVer}` : ''}`;
    cache.set(path, fetch(url, isMeta ? { cache: 'no-cache' } : undefined)
      .then(r => { if (!r.ok) throw new Error(`${path} (${r.status})`); return r.json(); })
      .catch(e => { cache.delete(path); throw e; }));
  }
  return cache.get(path);
}
export const D = { meta: null, index: null, byId: null, guName: {} };
export async function loadMeta() {
  D.meta = await get('meta.json');
  dataVer = encodeURIComponent(D.meta.updated || D.meta.asof || '');
  for (const s of D.meta.sidos) for (const g of s.gus) D.guName[g.sgg] = g.name;
  return D.meta;
}
export async function loadIndex() {
  if (D.index) return D.index;
  const j = await get('index.json');
  D.index = j.rows.map(r => {
    const o = {}; j.cols.forEach((c, i) => { o[c] = r[i]; });
    o.gu = D.guName[o.sgg] || o.sgg; o._n = normName(o.name); o._c = chosung(o.name);
    o.age = o.by ? new Date(D.meta.asof).getFullYear() - o.by : null;
    o.href = `#/apt/${o.sgg}/${o.id}`;
    return o;
  });
  D.byId = new Map(D.index.map(o => [o.id, o]));
  return D.index;
}
export const bandLabel = k => (D.meta.bands.find(b => b.key === k) || {}).label || k;

// ── 표(정렬·더 보기·CSV) ───────────────────────────────
export function downloadCSV(name, head, rows) {
  const q = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const text = '﻿' + [head, ...rows].map(r => r.map(q).join(',')).join('\r\n');
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' })), download: name });
  a.click(); URL.revokeObjectURL(a.href);
}
/** cols: [{k, label, num, color, fmt(v,row)→HTML, raw(v,row)→CSV값, tip}] */
export function table(host, { cols, rows, sort = null, dir = -1, limit = 30, csv = null, empty = '해당하는 데이터가 없어요' }) {
  let key = sort, d = dir, shown = limit;
  const sorted = () => !key ? rows : [...rows].sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null) return y == null ? 0 : 1;
    if (y == null) return -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'ko') : x - y) * d;
  });
  const draw = () => {
    const list = sorted();
    host.innerHTML = `<div class="tblwrap"><table class="tbl"><thead><tr>${cols.map(c =>
      `<th scope="col" tabindex="0" data-k="${c.k}" class="${c.num ? 'num' : ''}${c.k === key ? ' sorted' : ''}"${c.k === key ? ` aria-sort="${d > 0 ? 'ascending' : 'descending'}"` : ''}${c.tip ? ` title="${esc(c.tip)}"` : ''}>${esc(c.label)}${c.k === key ? (d > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead><tbody>${
      list.slice(0, shown).map(r => `<tr${r.href ? ` class="click" data-href="${esc(r.href)}"` : ''}>${cols.map(c => {
        const v = r[c.k];
        return `<td class="${c.num ? 'num' : ''} ${c.color ? cls(v) : ''}">${c.fmt ? c.fmt(v, r) : esc(v ?? '-')}</td>`;
      }).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}" class="empty">${esc(empty)}</td></tr>`
    }</tbody></table></div><div class="tblfoot"><span>${nf.format(rows.length)}건</span>${
      list.length > shown ? '<button class="btn sm more">더 보기</button>' : ''}${
      csv && rows.length ? '<button class="btn sm csv">CSV 내려받기</button>' : ''}</div>`;
  };
  host.onclick = e => {
    const th = e.target.closest('th');
    if (th) { const k = th.dataset.k; if (k === key) d = -d; else { key = k; d = cols.find(c => c.k === k).num ? -1 : 1; } draw(); return; }
    if (e.target.closest('.more')) { shown += limit * 2; draw(); return; }
    if (e.target.closest('.csv')) {
      downloadCSV(csv, cols.map(c => c.label), sorted().map(r => cols.map(c => c.raw ? c.raw(r[c.k], r) : r[c.k])));
      return;
    }
    if (e.target.closest('a,button,input')) return;
    const tr = e.target.closest('tr[data-href]');
    if (tr) location.hash = tr.dataset.href;
  };
  host.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.tagName === 'TH') { e.preventDefault(); e.target.click(); } };
  draw();
  return { update(r) { rows = r; shown = limit; draw(); } };
}

// ── 차트 ──────────────────────────────────────────────
const charts = new Set();
export const isDark = () => { const t = document.documentElement.dataset.theme; return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; };
export const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export function chart(el, opt) {
  if (!window.echarts) { el.innerHTML = '<p class="muted small">차트 도구를 불러오지 못했어요. 인터넷 연결을 확인해 주세요.</p>'; return null; }
  const c = window.echarts.init(el, isDark() ? 'dark' : null);
  c.setOption({
    backgroundColor: 'transparent', animationDuration: 250, textStyle: { fontFamily: 'inherit' },
    grid: { left: 6, right: 10, top: 40, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis', confine: true }, legend: { top: 0, type: 'scroll' }, ...opt,
  });
  charts.add(c);
  return c;
}
export function disposeCharts() { charts.forEach(c => { if (!c.isDisposed()) c.dispose(); }); charts.clear(); }
window.addEventListener('resize', debounce(() => charts.forEach(c => { if (c.isDisposed()) charts.delete(c); else c.resize(); }), 150));

/** 월별 거래량(막대) + 평단가(선). s: 시계열 JSON, band: 'all'|구간키, months: 최근 개월 수(0=전체) */
export function seriesChart(el, s, { band = 'all', months = 60, macro = null, jeonse = true } = {}) {
  const src = band === 'all' ? s : s.bands[band];
  const from = months ? Math.max(0, s.m.length - months) : 0;
  const x = s.m.slice(from);
  const partial = (D.meta.partial || []).filter(p => x.includes(p));
  const series = [
    { name: '거래량(건)', type: 'bar', yAxisIndex: 1, data: src.n.slice(from), itemStyle: { color: isDark() ? '#3b4a5f' : '#cfd8e3' }, barMaxWidth: 14,
      markArea: partial.length ? { silent: true, itemStyle: { color: 'rgba(240,140,0,.10)' }, label: { show: true, position: 'insideTop', color: css('--muted'), fontSize: 10, formatter: '신고 집계 중' }, data: [[{ xAxis: partial[0] }, { xAxis: partial[partial.length - 1] }]] } : undefined },
    { name: '매매 평단가', type: 'line', data: src.ppy.slice(from), smooth: .2, symbol: 'none', lineStyle: { width: 2.5 }, itemStyle: { color: css('--up') }, connectNulls: true },
  ];
  if (jeonse && band === 'all' && s.jppy) series.push({ name: '전세 평단가', type: 'line', data: s.jppy.slice(from), smooth: .2, symbol: 'none', lineStyle: { width: 2, type: 'dashed' }, itemStyle: { color: css('--down') }, connectNulls: true });
  const yAxis = [
    { type: 'value', name: '3.3㎡당(만원)', scale: true, axisLabel: { formatter: v => nf.format(v) }, splitLine: { lineStyle: { color: css('--line') } } },
    { type: 'value', name: '건', splitLine: { show: false }, max: v => Math.ceil(v.max * 2.6) },
  ];
  if (macro) {
    yAxis.push({ type: 'value', show: false, min: 0 });
    const names = { base_rate: '기준금리(%)', mortgage_rate: '주담대 금리(%)' };
    for (const k of Object.keys(names)) if (macro[k]) {
      const map = new Map(macro[k].t.map((t, i) => [t, macro[k].v[i]]));
      series.push({ name: names[k], type: 'line', yAxisIndex: 2, step: 'end', symbol: 'none', data: x.map(m => map.get(m) ?? null), lineStyle: { width: 1.5, type: 'dotted' }, connectNulls: true });
    }
  }
  return chart(el, { xAxis: { type: 'category', data: x, axisLabel: { formatter: v => v.slice(2) } }, yAxis, series });
}
