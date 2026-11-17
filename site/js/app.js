// 앱 뼈대: 주소(#/…)에 따라 화면 바꾸기, 상단 검색, 테마, 브랜드 표시
import { $, $$, D, S, save, loadMeta, loadIndex, searchItems, esc, disposeCharts, debounce, F, isDark } from './core.js';

const pages = {
  home: () => import('./pages/home.js'), gu: () => import('./pages/gu.js'), apt: () => import('./pages/apt.js'),
  map: () => import('./pages/map.js'), screener: () => import('./pages/screener.js'), score: () => import('./pages/score.js'),
  compare: () => import('./pages/compare.js'), my: () => import('./pages/my.js'), report: () => import('./pages/report.js'),
  flow: () => import('./pages/flow.js'),
};

export function parseHash() {
  const [path, qs] = location.hash.replace(/^#\/?/, '').split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { name: pages[parts[0]] ? parts[0] : 'home', parts: parts.slice(1), q: Object.fromEntries(new URLSearchParams(qs || '')) };
}

let seq = 0;
async function route() {
  const r = parseHash(), my = ++seq, app = $('#app');
  disposeCharts();
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.r === (r.name === 'apt' ? 'gu' : r.name)));
  const box = document.createElement('div');
  box.innerHTML = '<p class="loading">불러오는 중…</p>';
  app.replaceChildren(box);
  try {
    const mod = await pages[r.name]();
    if (my !== seq) return;
    await mod.render(box, r);
  } catch (e) {
    console.error(e);
    if (my === seq) box.innerHTML = `<div class="card err"><p>화면을 불러오지 못했어요.</p><p class="small">${esc(e.message || e)}</p><p><a class="btn" href="#/">홈으로</a></p></div>`;
  }
  if (my === seq) window.scrollTo(0, 0);
}

function applyBrand(meta) {
  const s = meta.site || {};
  if (s.title) document.title = s.title;
  if (s.brand) $('#brand').textContent = s.brand;
  for (const id of ['#cta', '#cta2']) {
    const a = $(id);
    if (s.home_url) { a.href = s.home_url; if (id === '#cta' && s.home_label) a.textContent = s.home_label; } else a.hidden = true;
  }
  if (s.home_url && s.promo_title) {
    $('#promo-title').textContent = s.promo_title;
    $('#promo-text').textContent = s.promo_text || '';
    const a = $('#cta3'); a.href = s.home_url; a.textContent = s.home_label || '자세히 보기';
    // 미리보기 버튼: 주소(preview_url)가 있을 때만. 있으면 미리보기가 앞(채운 버튼), 강의 보기는 테두리 버튼으로.
    if (s.preview_url) {
      const p = $('#cta4'); p.href = s.preview_url; p.textContent = s.preview_label || '▶ 1강 첫 챕터 무료 미리보기'; p.hidden = false;
      a.classList.add('line');
    }
    $('#promo').hidden = false;
  }
  // 방문 집계(Cloudflare Web Analytics, 쿠키 없음): 토큰(cf_beacon_token)이 있을 때만 붙인다. 내 PC에서 볼 때(localhost)는 세지 않는다.
  if (s.cf_beacon_token && !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) && !document.querySelector('script[data-cf-beacon]')) {
    const b = document.createElement('script');
    b.defer = true; b.src = 'https://static.cloudflareinsights.com/beacon.min.js';
    b.setAttribute('data-cf-beacon', JSON.stringify({ token: String(s.cf_beacon_token) }));
    document.head.appendChild(b);
  }
  if (s.disclaimer) $('#disclaimer').textContent = s.disclaimer;
  if (s.source) $('#source').textContent = s.source;
  $('#updated').textContent = `거래 기준일 ${meta.asof} · 갱신 ${meta.updated.replace('T', ' ').slice(0, 16)}`;
  const cov = meta.coverage;
  if (meta.sample) $('#banner').innerHTML = '<div class="banner" role="status">⚠ 가상 샘플 데이터입니다 — 실제 거래가 아닙니다(개발·시연용). 단지 이름도 모두 지어낸 것입니다.</div>';
  else if (cov && cov.months < cov.target - 1) {
    // 과거 자료를 며칠에 걸쳐 채우는 동안에는 '전고점·1년 전 대비'가 짧은 기간 기준이라는 점을 알린다.
    $('#banner').innerHTML = `<div class="banner info" role="status">과거 자료를 채우는 중이에요 — 지금은 ${esc(cov.from.replace('-', '년 '))}월부터의 거래가 들어 있어요(목표 ${Math.round(cov.target / 12)}년치). 전고점·1년 전 대비 같은 숫자는 다 채워지면 정확해져요.</div>`;
  }
}

function initSearch() {
  const q = $('#q'), box = $('#qres');
  let items = [], on = -1;
  const close = () => { box.hidden = true; on = -1; };
  const draw = () => {
    box.innerHTML = items.map((o, i) => `<a href="${o.href}" class="${i === on ? 'on' : ''}"><span>${esc(o.name)}</span><span class="muted small">${esc(o.gu)} ${esc(o.umd)} · ${F.eokS(o.price)}</span></a>`).join('')
      || '<a><span class="muted">찾는 단지가 없어요</span></a>';
    box.hidden = false;
  };
  const run = debounce(async () => {
    if (!q.value.trim()) return close();
    items = searchItems(await loadIndex(), q.value); on = -1; draw();
  }, 120);
  q.addEventListener('focus', () => { loadIndex().catch(() => {}); if (q.value.trim()) run(); });
  q.addEventListener('input', run);
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (!items.length) return; on = (on + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; draw(); }
    else if (e.key === 'Enter') { const o = items[Math.max(on, 0)]; if (o) { location.hash = o.href; q.value = ''; q.blur(); close(); } }
    else if (e.key === 'Escape') close();
  });
  box.addEventListener('click', () => { q.value = ''; close(); });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) close(); });
}

function initTheme() {
  $('#theme').addEventListener('click', () => {
    S.theme = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = S.theme;
    save(); route();
  });
}

/** 지난 방문 때의 관심 단지 시세를 기억해 두었다가, 데이터가 갱신되면 '지난 방문 이후 변화'로 보여 준다 */
async function trackVisit(meta) {
  if (S.visit && S.visit.asof === meta.asof) return;
  const snap = {};
  if (Object.keys(S.watch).length) {
    try { await loadIndex(); for (const id of Object.keys(S.watch)) { const o = D.byId.get(id); if (o) snap[id] = { price: o.price, nh: o.nh }; } } catch (e) { /* 다음에 */ }
  }
  if (S.visit) S.prevVisit = S.visit;
  S.visit = { asof: meta.asof, at: new Date().toISOString().slice(0, 10), snap };
  save();
}

async function boot() {
  initSearch(); initTheme();
  try {
    const meta = await loadMeta();
    applyBrand(meta);
    await trackVisit(meta);
  } catch (e) {
    $('#app').innerHTML = '<div class="card err"><p>데이터를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.</p></div>';
    return;
  }
  window.addEventListener('hashchange', route);
  route();
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}
boot();
