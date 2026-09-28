"""Self-contained, escaped HTML report generation."""
from __future__ import annotations
import html, json, statistics
from collections import Counter
from decimal import Decimal
from .models import json_value

PERIODS=(7,30,90,180)
def _e(v): return html.escape(str(v),quote=True)
def _fmt(v,places=2): return "—" if v is None else f"{v.quantize(Decimal(1).scaleb(-places))}%"
def summary(analyses):
    stats={}
    for n in PERIODS:
        vals=[a.returns[n] for a in analyses if a.returns.get(n) is not None]
        stats[n]={"count":len(vals),"mean":sum(vals)/len(vals) if vals else None,"median":Decimal(str(statistics.median(vals))) if vals else None,"min":min(vals) if vals else None,"max":max(vals) if vals else None,"up_ratio":Decimal(sum(v>0 for v in vals))*100/Decimal(len(vals)) if vals else None}
    statuses=Counter(o.status for a in analyses for o in a.observations.values() if o.status!="AVAILABLE")
    return stats,statuses

def render_report(analyses, as_of, notices_examined=0, warnings=(), return_places=2):
    stats,statuses=summary(analyses); mapped=sum(a.binance_contract is not None for a in analyses)
    warning_html="".join(f"<li>{_e(w)}</li>" for w in warnings)
    rows=[]
    for a in analyses:
        u,c=a.upbit_listing,a.binance_contract
        cells=[]
        for n in (0,)+PERIODS:
            o=a.observations[n]; cells.append(f"{_e(o.target_date)}<br>{_e(o.close_price if o.close_price is not None else '—')}<br><small>{_e(o.status)}</small>")
        returns=" / ".join(f"D+{n} {_fmt(a.returns[n],return_places)}" for n in PERIODS)
        rows.append(f'<tr data-status="{_e(a.mapping_status)}"><td>{_e(u.ticker)}</td><td><a href="{_e(u.notice_url)}">{_e(u.notice_id)}</a></td><td>{_e(u.notice_published_at.isoformat())}</td><td>{_e(u.trading_started_at.isoformat())}</td><td>{_e(c.symbol if c else "—")}<br>×{_e(c.contract_multiplier if c else "—")}</td><td>{_e(c.onboard_at.isoformat() if c else "—")}</td>'+''.join(f'<td>{x}</td>' for x in cells)+f'<td>{returns}</td><td>{_e(a.mapping_status)} {_e(a.warning or "")}</td></tr>')
    palette=["#2563eb","#16a34a","#d97706","#dc2626"]
    bars=[]
    for i,a in enumerate(analyses):
        for j,n in enumerate(PERIODS):
            v=a.returns[n]
            if v is not None:
                width=min(abs(float(v)),100); bars.append(f'<rect x="{120 if v>=0 else 120-width}" y="{i*22+j*4}" width="{max(width,1)}" height="3" fill="{palette[j]}"><title>{_e(a.upbit_listing.ticker)} D+{n}: {_fmt(v,return_places)}</title></rect>')
    statrows="".join(f"<tr><th>D+{n}</th><td>{s['count']}</td><td>{_fmt(s['mean'],return_places)}</td><td>{_fmt(s['median'],return_places)}</td><td>{_fmt(s['min'],return_places)}</td><td>{_fmt(s['max'],return_places)}</td><td>{_fmt(s['up_ratio'],return_places)}</td></tr>" for n,s in stats.items())
    statusbars="".join(f'<div>{_e(k)} <span style="display:inline-block;background:#64748b;width:{v*18}px">&nbsp;</span> {v}</div>' for k,v in statuses.items()) or "없음"
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Upbit listing analysis</title><style>body{{font:14px system-ui;margin:2rem;color:#172033}}section{{margin:2rem 0}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#eef2ff}}.scroll{{overflow:auto}}.warn{{background:#fff4db;padding:1rem}}input,select{{padding:.5rem;margin:.3rem}}svg{{width:100%;min-height:180px;background:#fafafa}}</style></head><body><h1>업비트 KRW 신규 상장 분석</h1><section><h2>1. 요약</h2><p>분석 기준일: {_e(as_of)} · 조사 공지: {notices_examined} · KRW 신규 상장: {len(analyses)} · Binance 매핑: {mapped}</p><div class="warn"><strong>수집 경고</strong><ul>{warning_html or '<li>없음</li>'}</ul></div><p>결측 상태: {_e(dict(statuses))}</p><table><tr><th>기간</th><th>표본</th><th>평균</th><th>중앙값</th><th>최소</th><th>최대</th><th>상승 비율</th></tr>{statrows}</table></section><section><h2>2. 차트</h2><h3>종목별 기간 수익률 (±100%에서 시각 범위 제한, 정확한 값은 표 참조)</h3><svg viewBox="0 0 240 {max(180,len(analyses)*22)}"><line x1="120" x2="120" y1="0" y2="100%" stroke="#222"/>{''.join(bars)}</svg><h3>기간별 분포 (표 형태 box-plot 요약)</h3><table>{statrows}</table><h3>상태별 종목 수</h3>{statusbars}</section><section><h2>3. 상세표</h2><input id="q" placeholder="ticker 검색"><select id="status"><option value="">모든 상태</option>{''.join(f'<option>{_e(k)}</option>' for k in statuses)}</select><div class="scroll"><table id="detail"><thead><tr>{''.join(f'<th>{x}</th>' for x in ['Ticker','공지','게시 시각','KRW 시작','계약/배율','Onboard','D0','D+7','D+30','D+90','D+180','수익률','상태/사유'])}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section><script>const q=document.querySelector('#q'),s=document.querySelector('#status'),rows=[...document.querySelectorAll('#detail tbody tr')];function f(){{rows.forEach(r=>r.hidden=!r.cells[0].textContent.toLowerCase().includes(q.value.toLowerCase())||(s.value&&!r.textContent.includes(s.value)))}}q.oninput=f;s.onchange=f;document.querySelectorAll('th').forEach((h,i)=>h.onclick=()=>{{if(!h.closest('#detail'))return;rows.sort((a,b)=>a.cells[i].textContent.localeCompare(b.cells[i].textContent,undefined,{{numeric:true}})).forEach(r=>r.parentNode.append(r))}})</script></body></html>'''

