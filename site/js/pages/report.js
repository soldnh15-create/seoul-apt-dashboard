// 주간 리포트: 계산된 숫자로 만든 요약(+ 검증을 통과한 AI 글이 있으면 함께)
import { D, F, esc, get } from '../core.js';

export async function render(el, r) {
  const meta = D.meta;
  const code = meta.sidos.some(s => s.code === r.q.sido) ? r.q.sido : meta.sidos[0].code;
  const rep = await get(`report/${code}.json`);
  const f = rep.facts;
  el.innerHTML = `
    <h1>${esc(rep.region)} 주간 리포트</h1><p class="muted small">거래 기준일 ${rep.asof} · 아래 숫자는 모두 이 사이트가 실거래 자료로 계산한 값이에요.</p>
    ${rep.ai ? `<div class="card report"><h2>AI 요약</h2>${rep.ai.text.split(/\n+/).map(p => `<p>${esc(p)}</p>`).join('')}
      <p class="note">${esc(rep.ai.model)}가 ${esc(rep.ai.generated)}에 작성. 글 속 숫자는 계산 값과 자동 대조를 통과한 것만 실어요.</p></div>` : ''}
    <div class="card report"><h2>핵심 요약</h2>${rep.lines.map(l => `<p>${esc(l)}</p>`).join('')}</div>
    <div class="grid two">
      <div class="card"><h2>평단가가 많이 오른 구</h2><dl class="dl">${f.up.map(g => `<dt>${esc(g.name)}</dt><dd class="${g.chg3m > 0 ? 'up' : 'down'}">${F.pct(g.chg3m)}</dd>`).join('')}</dl></div>
      <div class="card"><h2>거래가 많이 늘어난 구</h2><dl class="dl">${f.busy.map(g => `<dt>${esc(g.name)}</dt><dd class="${g.volchg > 0 ? 'up' : 'down'}">${F.pct(g.volchg)}</dd>`).join('')}</dl></div>
    </div>
    <p class="note">${esc(meta.site.disclaimer || '')} 전망이나 매수·매도 의견은 담지 않아요.</p>
    <p><a class="btn" href="#/">홈에서 자세히 보기</a></p>`;
}
