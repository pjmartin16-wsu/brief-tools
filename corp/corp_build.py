import json, sys, datetime as dt
tape=json.load(open(sys.argv[1])); S=json.load(open(sys.argv[2])); OUT=sys.argv[3]
RT={r['id']:r for r in tape['rates']}
TEN={0.25:'3M',0.5:'6M',1:'1Y',2:'2Y',5:'5Y',10:'10Y',30:'30Y'}
n={TEN[t]:v for t,v in tape['curve'] if t in TEN}; n['1M']=S['curve_1m'][S['close']]; w=S['curve_prior']
assert tape['meta']['asof']==S['close'], 'tape close and supplement close differ'
def md(iso): d=dt.date.fromisoformat(iso); return d.strftime('%b ')+str(d.day)
def note_date(r): return r['note'].replace(' print','').replace(' close','')
NAVY='#0A2A5E';CY='#35B2C2';CYF='#1D96A6';CYS='#E3F4F7';AMB='#C07A34';GR='#2E7D4F';RD='#B4432A';INK='#1c2531';INK2='#3d4a5c';MU='#5f6b7a';LN='#e2e7ee'
SANS="-apple-system,'Segoe UI',Roboto,Arial,sans-serif";SERIF="Georgia,'Times New Roman',serif"
def bp(a,b):
    v=round((a-b)*100); return ('+' if v>0 else ('−' if v<0 else ''))+f'{abs(v)} bp'
def col(a,b): v=round((a-b)*100); return MU if v==0 else INK2
def card(lbl,val,sub):
    return f'<td style="width:20%;padding:12px 10px;border:1px solid {LN};vertical-align:top"><div style="font:600 11px {SANS};letter-spacing:.06em;text-transform:uppercase;color:{MU}">{lbl}</div><div style="font:600 22px {SANS};color:{NAVY};margin-top:6px">{val}</div><div style="font:12px/1.4 {SANS};color:{MU};margin-top:4px">{sub}</div></td>'
ff=RT['ff']['disp']; sofr=RT['sofr']['v']; effr=RT['effr']['v']
rates1=[card('Fed funds target',ff,'Held 28 Oct'),card('SOFR',f"{sofr:.2f}%",note_date(RT['sofr'])),card('SOFR 30-day avg',f"{S['sofr30']['v']:.2f}%",md(S['sofr30']['date'])),card('Prime rate',f"{S['prime']['v']:.2f}%",md(S['prime']['date'])),card('Fed funds effective',f"{effr:.2f}%",note_date(RT['effr']))]
rates2=[card('1-month bill',f"{n['1M']:.2f}%",f"{md(S['close'])} · {bp(n['1M'],w['1M'])} on the week"),card('3-month bill',f"{n['3M']:.2f}%",f"{md(S['close'])} · {bp(n['3M'],w['3M'])}"),card('6-month bill',f"{n['6M']:.2f}%",f"{md(S['close'])} · {bp(n['6M'],w['6M'])}"),card('1-year bill',f"{n['1Y']:.2f}%",f"{md(S['close'])} · {bp(n['1Y'],w['1Y'])}"),card('CP, 1-month',f"{S['cp_nf_1m']['v']:.2f}%",f"Nonfinancial AA · {md(S['cp_nf_1m']['date'])}")]
# curve svg
T=['1M','3M','6M','1Y','2Y','5Y','10Y','30Y']; W,H=520,200; L,R,TP,B=40,12,14,30
lo=min(min(n.values()),min(w.values()))-0.1; hi=max(max(n.values()),max(w.values()))+0.1
x=lambda i:L+(W-L-R)*i/(len(T)-1); y=lambda v:TP+(H-TP-B)*(1-(v-lo)/(hi-lo))
svg=f'<svg width="100%" viewBox="0 0 {W} {H}" role="img" aria-label="Treasury par curve, {md(S['close'])} against {md(S['prior'])}: 2-year {n['2Y']:.2f}%, 10-year {n['10Y']:.2f}%, 30-year {n['30Y']:.2f}%" style="display:block">'
for v in [x/2 for x in range(int(lo*2)+1,int(hi*2)+1)]:
    svg+=f'<line x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{LN}"/><text x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end" font-size="11" fill="{MU}" font-family="Arial">{v:.1f}%</text>'
svg+='<polyline fill="none" stroke="#9aa4b2" stroke-width="1.5" stroke-dasharray="4 3" points="'+' '.join(f'{x(i):.1f},{y(w[t]):.1f}' for i,t in enumerate(T))+'"/>'
svg+=f'<polyline fill="none" stroke="{NAVY}" stroke-width="2.5" points="'+' '.join(f'{x(i):.1f},{y(n[t]):.1f}' for i,t in enumerate(T))+'"/>'
for i,t in enumerate(T):
    svg+=f'<circle cx="{x(i):.1f}" cy="{y(n[t]):.1f}" r="{4.5 if t=="10Y" else 3}" fill="{CY if t=="10Y" else NAVY}"/><text x="{x(i):.1f}" y="{H-10}" text-anchor="middle" font-size="11" fill="{MU}" font-family="Arial">{t}</text>'
svg+='</svg>'
ladder=''.join(f'<td style="padding:6px 4px;text-align:center;font:12px {SANS};color:{INK2};border-top:1px solid {LN}"><div style="color:{MU}">{t}</div><div style="font-weight:600;color:{NAVY};font-size:14px">{n[t]:.2f}</div><div style="color:{col(n[t],w[t])}">{bp(n[t],w[t]).replace(" bp","")}</div></td>' for t in T)
e=S['ecb'];e1=e[S['close']];e0=e[S['prior']]
def fx(pair,a,b,dec):
    ch=(a/b-1)*100
    return f'<tr><td style="padding:8px 10px;border-bottom:1px solid {LN};font:14px {SANS};color:{INK}">{pair}</td><td style="padding:8px 10px;border-bottom:1px solid {LN};font:600 14px {SANS};color:{NAVY};text-align:right">{a:.{dec}f}</td><td style="padding:8px 10px;border-bottom:1px solid {LN};font:13px {SANS};color:{INK2};text-align:right">{"+" if ch>0 else "−"}{abs(ch):.2f}%</td></tr>'
fxrows=fx('EUR/USD',e1['USD'],e0['USD'],4)+fx('GBP/USD',e1['USD']/e1['GBP'],e0['USD']/e0['GBP'],4)+fx('USD/CAD',e1['CAD']/e1['USD'],e0['CAD']/e0['USD'],4)+fx('USD/MXN',e1['MXN']/e1['USD'],e0['MXN']/e0['USD'],4)+fx('USD/JPY',e1['JPY']/e1['USD'],e0['JPY']/e0['USD'],2)+fx('USD/CNY',e1['CNY']/e1['USD'],e0['CNY']/e0['USD'],4)
cal=[]
for it in tape['week']:
    if any(k.lower() in it['it'].lower() for k in S['week_keep']):
        dd=it['d'].title(); cal.append((dd.replace(' ',' Nov '), it['t'], it['it'], bool(it.get('mq'))))
cal+= [tuple(x) for x in S['calendar_extra']]
calrows=''.join(f'<tr style="background:{CYS if hl else "#ffffff"}"><td style="padding:8px 10px;border-bottom:1px solid {LN};font:600 13px {SANS};color:{NAVY};white-space:nowrap;vertical-align:top">{a}</td><td style="padding:8px 10px;border-bottom:1px solid {LN};font:12px {SANS};color:{MU};white-space:nowrap;vertical-align:top">{b}</td><td style="padding:8px 10px;border-bottom:1px solid {LN};font:13px/1.45 {SANS};color:{INK}">{c_}</td></tr>' for a,b,c_,hl in cal)
def h2(t,side=''): return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:2px solid {NAVY};margin:30px 0 14px"><tr><td style="font:400 20px {SERIF};color:{NAVY};padding-bottom:6px">{t}</td><td style="font:12px {SANS};color:{MU};text-align:right;padding-bottom:6px">{side}</td></tr></table>'
P=lambda s:f'<p style="margin:0 0 14px;font:16px/1.65 {SERIF};color:{INK}">{s}</p>'
edl=S['edition_long']
P2=lambda s:P(s)
reads=''.join(P(x) for x in S['read'])
cash=''.join(f'<div style="margin-bottom:10px"><span style="color:{CY}">&#9632;</span>&nbsp; <b>{a}</b> {b}</div>' for a,b in S['cash'])
s210=round((n['10Y']-n['2Y'])*100); s210w=round((w['10Y']-w['2Y'])*100)
html=f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Setnova Advisory Corporate Treasury Daily Brief · {edl} (corporate edition)</title></head>
<body style="margin:0;background:#eef1f5">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f5"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="820" cellpadding="0" cellspacing="0" style="max-width:820px;width:100%;background:#ffffff;box-shadow:0 2px 10px rgba(10,42,94,.08)">
<tr><td style="background:{AMB};color:#ffffff;text-align:center;font:600 11px {SANS};letter-spacing:.14em;text-transform:uppercase;padding:9px 16px">{S['banner']}</td></tr>
<tr><td style="background:{NAVY};padding:30px 36px 26px">
<div style="font:600 12px {SANS};letter-spacing:.16em;text-transform:uppercase;color:{CY}">Setnova Advisory · Corporate Treasury Daily Brief</div>
<h1 style="margin:10px 0 8px;font:400 34px/1.2 {SERIF};color:#ffffff">Cash, borrowing and the week ahead</h1>
<div style="font:italic 17px/1.5 {SERIF};color:#d6dde8">{S['deck']}</div>
<div style="font:13px {SANS};color:#aab6c8;margin-top:14px">{edl} · Markets as of the {S['close_long']} close · For CFOs and treasurers</div>
</td></tr>
<tr><td style="padding:8px 36px 32px">
{h2('The Read')}
{reads}
{h2('Cash and borrowing rates','Percent')}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>{''.join(rates1)}</tr><tr>{''.join(rates2)}</tr></table>
<div style="font:12px/1.5 {SANS};color:{MU};margin-top:8px">SOFR and the effective funds rate are for {note_date(RT['sofr'])}, published the next business morning; the SOFR 30-day average, prime and commercial paper carry their own dates. Bill yields are Treasury par yields (bond-equivalent basis) at Friday&rsquo;s close.</div>
{h2('Treasury curve',md(S['close'])+' close · dashed: '+md(S['prior']))}
{svg}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:6px"><tr>{ladder}</tr></table>
<div style="font:12px {SANS};color:{MU};margin-top:6px">Yield and change on the week in basis points. 2s10s spread {s210:+d} bp ({md(S['prior'])}: {s210w:+d} bp).</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px"><tr>
<td width="48%" style="vertical-align:top;padding-right:2%">{h2('Currencies','ECB reference · '+md(S['close']))}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr><td style="font:600 11px {SANS};color:{MU};padding:0 10px 6px;text-transform:uppercase;letter-spacing:.06em">Pair</td><td style="font:600 11px {SANS};color:{MU};padding:0 10px 6px;text-align:right;text-transform:uppercase;letter-spacing:.06em">Rate</td><td style="font:600 11px {SANS};color:{MU};padding:0 10px 6px;text-align:right;text-transform:uppercase;letter-spacing:.06em">Week</td></tr>{fxrows}</table>
<div style="font:12px/1.5 {SANS};color:{MU};margin-top:6px">Week = change since {md(S['prior'])}. Crosses other than EUR/USD are computed from the ECB&rsquo;s euro rates.</div></td>
<td width="50%" style="vertical-align:top">{h2('This week')}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{calrows}</table></td></tr></table>
{h2('What it means for your cash')}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fa;border:1px solid {LN}"><tr><td style="padding:18px 20px;font:15px/1.6 {SERIF};color:{INK}">
{cash}
</td></tr></table>
</td></tr>
<tr><td style="background:{NAVY};padding:22px 36px;text-align:center"><div style="font:italic 18px/1.5 {SERIF};color:#ffffff">{S['cta'][0]}<span style="color:{CY}">{S['cta'][1]}</span></div>
<a href="https://setnovaadvisory.com/" style="display:inline-block;margin-top:12px;background:{CYF};color:#ffffff;text-decoration:none;font:600 14px {SANS};padding:11px 22px;border-radius:4px">Talk to Setnova Advisory</a></td></tr>
<tr><td style="padding:20px 36px 26px;font:11px/1.6 {SANS};color:{MU}">
<p style="margin:0 0 8px">Corporate edition prepared by Setnova Advisory LLC for internal review; not sent to subscribers.</p>
<p style="margin:0">Sources: U.S. Treasury daily par yield curve; Federal Reserve Bank of New York (SOFR, SOFR averages, EFFR); Federal Reserve Board (FOMC statement of Oct 28, 2026; H.15; holiday schedule; release calendar); U.S. Department of the Treasury (auction schedule); Bureau of Labor Statistics (Consumer Price Index, release calendar); European Central Bank euro reference rates.</p></td></tr>
</table></td></tr></table></body></html>'''
open(OUT,'w').write(html)
print(len(html))
