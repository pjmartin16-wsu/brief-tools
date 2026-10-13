#!/usr/bin/env python3
"""
layoutaudit.py — programmatic layout defect detector for Setnova HTML deliverables.

Catches the class of defect that render-and-read keeps missing, because a
full-page screenshot read by eye shows that a page LOOKS fine while local
density problems hide in plain sight. Every check below encodes a defect that
actually shipped:

  CLIP     SVG <text> drawn outside its own viewBox        (CD schedule: $155M label off-canvas)
  OVERLAP  two text boxes occupying the same pixels        (gap chart: "-217" on top of "3-12 mo")
  GUTTER   a plotted series not using its own plot width   (curve: 146px left / 28px right)
  IMBAL    a table row whose columns differ wildly in      (pricing sheet: 1-line money cells
           line count, so short cells float in whitespace   against a 4-line note column)
  OFLOW    a container scrolling horizontally

Usage:  python3 layoutaudit.py <file.html> [view1 view2 ...]
        Views are passed to a global go(view) if the page defines one.
Exit code 1 if any finding.
"""
import sys, json
from playwright.sync_api import sync_playwright

JS = r"""
(WIDEST) => {
  const out = [];
  const vis = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
           && parseFloat(s.opacity || '1') > 0.05;
  };
  const txt = el => (el.textContent || '').trim().replace(/\s+/g, ' ');

  /* Children of a CLOSED <details> still report client rects in Chromium, so
     hidden panel content "overlaps" whatever is laid out where it would go. */
  const inClosedDetails = el => !!el.closest('details:not([open])');
  const leavesOf = () => [...document.querySelectorAll('body *')].filter(el => {
    if (!txt(el) || !vis(el) || inClosedDetails(el)) return false;
    if (['SCRIPT','STYLE','SVG','DEFS','TITLE'].includes(el.tagName)) return false;
    return ![...el.children].some(c => txt(c));
  });

  /* ---- CLIP: svg text outside the viewBox it is drawn into ---- */
  document.querySelectorAll('svg').forEach(svg => {
    const vb = svg.viewBox && svg.viewBox.baseVal;
    if (!vb || !vb.width) return;
    svg.querySelectorAll('text').forEach(t => {
      if (!txt(t)) return;
      let b; try { b = t.getBBox(); } catch (e) { return; }
      const pad = 0.5;
      if (b.x < -pad || b.y < -pad || b.x + b.width > vb.width + pad || b.y + b.height > vb.height + pad) {
        out.push({ kind: 'CLIP', text: txt(t).slice(0, 48),
          detail: `bbox x${b.x.toFixed(0)} y${b.y.toFixed(0)} w${b.width.toFixed(0)} h${b.height.toFixed(0)} vs viewBox ${vb.width}x${vb.height}` });
      }
    });
  });

  /* ---- OVERLAP: two text boxes sharing pixels ----
     Compare PER-LINE-BOX rects, never the union bounding rect. An inline
     element that wraps has a bounding rect spanning every line it touches and
     the full column width, so two <b> spans on adjacent lines of ordinary
     flowing prose "overlap" by hundreds of pixels. That false positive fired
     eleven times on a clean document the first time this ran. */
  /* A box scrolled out of view inside an overflow container still reports its
     geometric rect, so a table column hidden behind its own card's scroll edge
     "overlaps" whatever card sits beside it. Clip every box to its nearest
     clipping ancestor before comparing, and drop what survives at zero size. */
  const clipTo = el => {
    let r = null;
    for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const nr = n.getBoundingClientRect();
        r = r ? { left: Math.max(r.left, nr.left), right: Math.min(r.right, nr.right),
                  top: Math.max(r.top, nr.top), bottom: Math.min(r.bottom, nr.bottom) } : nr;
      }
    }
    return r;
  };
  const boxes = [];
  leavesOf().forEach(el => {
    const rng = document.createRange();
    rng.selectNodeContents(el);
    const clip = clipTo(el);
    [...rng.getClientRects()].forEach(r0 => {
      let r = { left: r0.left, right: r0.right, top: r0.top, bottom: r0.bottom };
      if (clip) {
        r = { left: Math.max(r.left, clip.left), right: Math.min(r.right, clip.right),
              top: Math.max(r.top, clip.top), bottom: Math.min(r.bottom, clip.bottom) };
      }
      r.width = r.right - r.left; r.height = r.bottom - r.top;
      if (r.width > 1 && r.height > 1) boxes.push({ el, r, t: txt(el) });
    });
  });
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const A = boxes[i], B = boxes[j];
      if (A.el === B.el || A.el.contains(B.el) || B.el.contains(A.el)) continue;
      const ox = Math.min(A.r.right, B.r.right) - Math.max(A.r.left, B.r.left);
      const oy = Math.min(A.r.bottom, B.r.bottom) - Math.max(A.r.top, B.r.top);
      if (ox > 2 && oy > 2) {
        const area = ox * oy;
        const small = Math.min(A.r.width * A.r.height, B.r.width * B.r.height);
        if (small > 0 && area / small > 0.35)
          out.push({ kind: 'OVERLAP', text: (A.t.slice(0,28) + '  ><  ' + B.t.slice(0,28)),
            detail: `${ox.toFixed(0)}x${oy.toFixed(0)}px shared` });
      }
    }
  }

  /* ---- GUTTER: a plotted series not using its own plot width ----
     Circle-marked series only. A diverging bar chart is centred on its own
     axis by design, so measuring its margins flags a chart that is correct —
     which is how this check reported a clean NII panel on first run. Measure
     mark EDGES, not centres. */
  document.querySelectorAll('svg').forEach(svg => {
    const sr = svg.getBoundingClientRect();
    const marks = [...svg.querySelectorAll('circle')];
    if (marks.length < 5) return;
    const rs = marks.map(m => m.getBoundingClientRect());
    const left = Math.min(...rs.map(r => r.left)) - sr.left;
    const right = sr.right - Math.max(...rs.map(r => r.right));
    const bigger = Math.max(left, right), smaller = Math.max(Math.min(left, right), 1);
    if (bigger > sr.width * 0.12 && bigger / smaller > 2.2)
      out.push({ kind: 'GUTTER', text: (svg.textContent || '').trim().slice(0, 44),
        detail: `left ${left.toFixed(0)}px vs right ${right.toFixed(0)}px of ${sr.width.toFixed(0)}px` });
  });

  /* ---- IMBAL: table row whose columns differ wildly in line count ----
     NOTE: a cell's own height is useless here — every cell in a row stretches
     to the row height, so measuring the box tells you nothing about how many
     lines its text actually occupies. Count the text's own line boxes with a
     Range instead. (This check silently passed a known-bad table until that
     was fixed, which is the same failure mode the audit exists to catch.) */
  const lineCount = el => {
    const rng = document.createRange();
    rng.selectNodeContents(el);
    const rects = [...rng.getClientRects()].filter(r => r.height > 1 && r.width > 1);
    if (!rects.length) return 1;
    const tops = [...new Set(rects.map(r => Math.round(r.top)))].sort((a,b)=>a-b);
    const merged = tops.filter((v,i)=> i===0 || v - tops[i-1] > 3);
    return Math.max(1, merged.length);
  };
  const scrolls = el => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const s = getComputedStyle(n);
      if ((s.overflowX === 'auto' || s.overflowX === 'scroll') && n.scrollWidth - n.clientWidth > 4)
        return true;
    }
    return false;
  };
  document.querySelectorAll('tbody tr').forEach(tr => {
    /* Only judge column allocation at the widest viewport. Narrower than that,
       a wide table is SUPPOSED to compress or scroll inside its container, so
       every explanation column falls under any share threshold and the check
       reports dozens of rows that are behaving exactly as designed. */
    if (!WIDEST) return;
    if (scrolls(tr)) return;
    const cells = [...tr.children].filter(td => txt(td) && vis(td));
    if (cells.length < 3) return;
    const lines = cells.map(lineCount);
    const mx = Math.max(...lines), mn = Math.min(...lines);
    if (mx - mn < 3) return;
    /* A long explanation column beside a short label is not a defect — that is
       what a reference table IS. The defect is a text column STARVED by
       over-wide fixed neighbours, which is what forced four-line wraps on the
       pricing sheet while six-character money columns held 40% of the table.
       So require the wrapping column to be under-allocated. Without this the
       check flags correct reference tables, which is how it gets ignored. */
    const rowW = tr.getBoundingClientRect().width || 1;
    const wide = cells[lines.indexOf(mx)].getBoundingClientRect().width;
    const share = wide / rowW;
    if (share >= 0.33) return;
    out.push({ kind: 'IMBAL', text: txt(cells[0]).slice(0, 44),
      detail: `cell line counts [${lines.join(', ')}] — the ${mx}-line column has only ` +
              `${(share*100).toFixed(0)}% of the row width, so ${mx - mn} lines of dead space sit beside the short cells` });
  });

  /* ---- OFLOW: horizontal scroll ---- */
  [document.documentElement, document.body, ...document.querySelectorAll('div,section,table')]
    .forEach(el => {
      if (el.scrollWidth - el.clientWidth > 4 && getComputedStyle(el).overflowX === 'visible')
        out.push({ kind: 'OFLOW', text: (el.className || el.tagName).toString().slice(0, 44),
          detail: `scrollWidth ${el.scrollWidth} > clientWidth ${el.clientWidth}` });
    });

  return out;
}
"""

def main():
    import os
    path = os.path.abspath(sys.argv[1])
    views = sys.argv[2:]
    widths = [1400, 1120, 900]
    findings = []
    with sync_playwright() as p:
        exe = os.environ.get('LAYOUTAUDIT_CHROMIUM', '/opt/pw-browsers/chromium')
        b = p.chromium.launch(**({'executable_path': exe} if os.path.exists(exe) else {}))  # 13 Oct 2026: CI has no /opt/pw-browsers
        for w in widths:
            pg = b.new_page(viewport={'width': w, 'height': 1100})
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.goto('file://' + path, wait_until='networkidle')
            targets = views or [None]
            for v in targets:
                if v:
                    pg.evaluate(f"go('{v}')")
                    pg.wait_for_timeout(300)
                for f in pg.evaluate(JS, w == max(widths)):
                    f['width'] = w
                    f['view'] = v or '-'
                    findings.append(f)
            for e in errs:
                findings.append({'kind': 'JSERR', 'text': e[:80], 'detail': '', 'width': w, 'view': '-'})
            pg.close()
        b.close()

    seen, uniq = set(), []
    for f in findings:
        k = (f['kind'], f['text'], f['view'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)

    if not uniq:
        print("PASS — no layout findings at 1400 / 1120 / 900.")
        return 0
    print(f"{len(uniq)} finding(s):\n")
    for f in sorted(uniq, key=lambda x: x['kind']):
        print(f"  [{f['kind']}] {f['view']} @{f['width']}px  {f['text']}")
        if f['detail']:
            print(f"          {f['detail']}")
    return 1

sys.exit(main())
