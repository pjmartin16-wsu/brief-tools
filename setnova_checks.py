#!/usr/bin/env python3
"""setnova_checks.py - deterministic release gate for the Setnova Advisory Treasury Morning Brief.

WHY (10 Oct 2026): on 29 Sep both plain-text parts carried figures the HTML lacked and the run still
reported (9e) PASS. A model asked to scan its own output can report a pass that is false; this script
cannot. Every mechanical gate in the brief prompt lives here, so the prompt keeps only the judgement.

Standard library only (Python 3.8+). Runs anywhere the brief run runs.

Usage:
  python3 setnova_checks.py --mc marketclose.json \
      --full-file full.html --full-email full_email.html --full-text full.txt \
      --generic-file generic.html --generic-email generic_email.html --generic-text generic.txt \
      [--today 2026-10-09] [--json report.json] [--subject-full "..."] [--subject-generic "..."]
  python3 setnova_checks.py --self-test

Any input may be omitted; the checks that need it report SKIP (never PASS). G8 needs both editions.
Exit: 0 = no FAIL, 1 = at least one FAIL, 2 = usage or input error (unreadable file, no curve in the
MarketClose object). A brief may be sent only on exit 0.

Every check has a seeded fixture in --self-test that must make it FAIL; a rule without a test is
not a rule. Add the fixture first when adding a rule.
"""
import argparse, datetime as dt, hashlib, html, json, os, re, sys
from html.parser import HTMLParser

# ---------------------------------------------------------------- text extraction
VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "source", "wbr"}
DARK_BG = {"#0a2a5e", "#061a3d", "#c07a34", "#3d5a86"}
LIGHT_FG = {"#fff", "#ffffff", "#d8e2f0", "#aebfd6", "#bdcbe0", "#35b2c2"}
COLOR_RE = re.compile(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{3,6})")
BG_RE = re.compile(r"background-color\s*:\s*(#[0-9a-fA-F]{3,6})")


class _Parse(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip, self.light_hits = [], [], 0, []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in ("style", "script", "head", "title"):
            self.skip += 1
        if tag in ("p", "div", "tr", "li", "h1", "h2", "h3", "br", "table", "td", "th"):
            self.out.append("\n" if tag != "td" and tag != "th" else " ")
        bg = (a.get("bgcolor") or "").lower()
        m = BG_RE.search(a.get("style", ""))
        dark = bg in DARK_BG or (m and m.group(1).lower() in DARK_BG)
        fg = [c.lower() for c in COLOR_RE.findall(a.get("style", ""))] + ([a["color"].lower()] if "color" in a else [])
        if any(c in LIGHT_FG for c in fg) and not dark and not any(d for _, d in self.stack):
            self.light_hits.append(f"<{tag}> color {fg} outside a navy/amber bgcolor cell")
        if tag not in VOID:
            self.stack.append((tag, bool(dark)))

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head", "title"):
            self.skip = max(0, self.skip - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in ("p", "div", "tr", "li", "h1", "h2", "h3"):
            self.out.append("\n")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def visible(html_src):
    p = _Parse(); p.feed(html_src); p.close()
    t = "".join(p.out)
    t = re.sub(r"[ \t\r\f\v\u00a0]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return t.strip(), p.light_hits


def norm(s):
    """Normalise typography so plain text and HTML compare on content, not glyphs."""
    return (s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-").replace("\u00d7", "x")
             .replace("\u2009", " ").replace("\u202f", " ").replace("\u00a5", "Y").replace("&amp;", "&"))


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9$(])|\n+", t) if s.strip()]


def ctx(t, i, j, w=50):
    return "..." + t[max(0, i - w):j + w].replace("\n", " ") + "..."


def find_all(t, needles, ci=True):
    hits = []
    for n in needles:
        for m in re.finditer(re.escape(n), t, re.I if ci else 0):
            hits.append(f"'{n}': {ctx(t, m.start(), m.end())}")
    return hits


def find_re(t, pats, ci=True):
    hits = []
    for p in pats:
        for m in re.finditer(p, t, re.I if ci else 0):
            hits.append(f"/{p}/ -> '{m.group(0)}': {ctx(t, m.start(), m.end())}")
    return hits


# ---------------------------------------------------------------- MarketClose access
TENORS = ["1M", "2M", "3M", "4M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH_RX = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"


def _val(x):
    if isinstance(x, dict):
        x = x.get("value", x.get("v"))
    try:
        return float(str(x).replace("%", ""))
    except (TypeError, ValueError):
        return None


def _tkey(k):
    k = str(k).upper().replace("-", "").replace("_", "").replace(" ", "")
    k = {"3MO": "3M", "6MO": "6M", "1YR": "1Y", "2YR": "2Y", "3YR": "3Y", "5YR": "5Y", "7YR": "7Y", "10YR": "10Y",
         "20YR": "20Y", "30YR": "30Y", "T10": "10Y", "T2": "2Y", "T5": "5Y", "T30": "30Y", "T3M": "3M"}.get(k, k)
    return k if k in TENORS else None


def _walk(o, path=()):
    yield path, o
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, path + (str(i),))


class MC:
    """Tolerant reader. The prompt fixes {value, source, asOf} per field but not the nesting, so this finds
    the curve, history, changes, FedWatch and news/reg items by shape and fails loudly if the curve is missing."""

    def __init__(self, obj):
        self.raw = obj
        self.curve, self.hist = {}, {}
        for path, o in _walk(obj):
            if isinstance(o, dict) and "hist" not in "/".join(path).lower():
                c = {_tkey(k): _val(v) for k, v in o.items() if _tkey(k) and _val(v) is not None}
                if len(c) >= 5 and len(c) > len(self.curve):
                    self.curve = c
        for path, o in _walk(obj):
            if isinstance(o, dict) and re.search(r"hist", "/".join(path[-1:]), re.I):
                for d, row in o.items():
                    if re.match(r"20\d\d-\d\d-\d\d$", str(d)) and isinstance(row, dict):
                        self.hist[d] = {_tkey(k): _val(v) for k, v in row.items() if _tkey(k) and _val(v) is not None}
        self.changes = []
        for path, o in _walk(obj):
            if isinstance(o, dict) and {"instrument", "from_date", "to_date", "change_bp"} <= set(o):
                self.changes.append(o)
        self.fedwatch = any(isinstance(o, dict) and _val(o) is not None
                            for p, o in _walk(obj) if p and re.search(r"fedwatch", p[-1], re.I))
        self.items = []
        for p, o in _walk(obj):
            if isinstance(o, list) and p and re.search(r"news|reg", p[-1], re.I):
                kind = "reg" if re.search(r"reg", p[-1], re.I) else "news"
                self.items += [dict(i, _kind=kind) for i in o if isinstance(i, dict)]
        self.close = None
        for p, o in _walk(obj):
            if isinstance(o, dict) and _tkey(p[-1] if p else "") == "10Y" and isinstance(o.get("asOf"), str):
                self.close = o["asOf"][:10]
                break
        if self.hist:
            self.close = self.close or max(self.hist)
            self.hist.setdefault(self.close, self.curve)
        self.rates = {}
        for p, o in _walk(obj):
            if p and _val(o) is not None and isinstance(o, (dict, int, float, str)):
                k = p[-1].upper().replace("_", " ")
                for lab in ("EFFR", "SOFR", "IORB", "ON RRP", "RRP", "DISCOUNT"):
                    if k.startswith(lab) and lab not in self.rates and "AVG" not in k and "30" not in k:
                        self.rates[lab] = _val(o)

        # G2a (12 Oct 2026): the 30-day SOFR average and SOFR's own date, by shape ("sofr_30d_avg" in the prompt).
        self.sofr30, self.sofr_asof = None, None
        for p, o in _walk(obj):
            if p and isinstance(o, dict) and isinstance(o.get("asOf"), str) and _val(o) is not None:
                key = p[-1].lower().replace("-", "_").replace(" ", "_")
                if "sofr" in "/".join(p).lower() and re.search(r"30|avg|average", key) and self.sofr30 is None:
                    self.sofr30 = (_val(o), o["asOf"][:10])
                elif key == "sofr" and self.sofr_asof is None:
                    self.sofr_asof = o["asOf"][:10]

        # auct (14 Oct 2026, RELEASE-QUEUE Q7): Treasury auctions carrying the schedule's "reopening": true|false flag.
        self.auctions = []
        for p, o in _walk(obj):
            if isinstance(o, dict) and isinstance(o.get("reopening"), bool):
                sec = " ".join(str(o.get(k, "")) for k in ("security", "tenor", "name", "t", "it", "title") if o.get(k))
                self.auctions.append((sec, o["reopening"], str(o.get("date") or o.get("d") or o.get("asOf") or "")))

        # G2b (13 Oct 2026): FRED figures ("series" key, or a FRED/H.10 source) and the data-file headers the run read.
        self.fred_figs, self.fred_headers = [], {}
        for p, o in _walk(obj):
            if p and p[-1] == "fred_headers" and isinstance(o, dict):
                self.fred_headers.update({str(k): v for k, v in o.items() if isinstance(v, dict)})
        for p, o in _walk(obj):
            if not (p and isinstance(o, dict) and isinstance(o.get("asOf"), str)) or "fred_headers" in p:
                continue
            src = str(o.get("source", ""))
            if "series" in o or re.search(r"\bFRED\b|H\.10|DTWEX|DEXUS|DEXJP|SP500|NASDAQCOM|DJIA", src, re.I):
                self.fred_figs.append(("/".join(p), o))

    def dates(self):
        return sorted(self.hist)

    def value(self, inst, date):
        row = self.hist.get(date) or (self.curve if date == self.close else None)
        if row is None:
            return None
        if inst == "2s10s":
            return None if row.get("10Y") is None or row.get("2Y") is None else row["10Y"] - row["2Y"]
        if inst == "3M10Y":
            return None if row.get("10Y") is None or row.get("3M") is None else row["10Y"] - row["3M"]
        if inst == "5s30s":
            return None if row.get("30Y") is None or row.get("5Y") is None else row["30Y"] - row["5Y"]
        return row.get(inst)

    def back(self, n):
        d = self.dates()
        if self.close in d and d.index(self.close) >= n:
            return d[d.index(self.close) - n]
        return None


# ---------------------------------------------------------------- wording lists (from the brief prompt)
# The wording lists live in setnova_rules.json, the one rule file this checker, brief_tape_check.py, the Desk's
# tools/marketclose-check.ts and releasecheck.py all read (13 Oct 2026, checker-efficiency #5: the copies had drifted).
# Its SHA-256 is pinned here, so pinning this script's hash in the brief prompt pins the rules too.
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setnova_rules.json")
RULES_SHA256 = "b57c578cff621bfe45d466a97bb7bbff1ced94703ba0bd29decb13133afe6dbe"


def load_rules(path=RULES_FILE, want=RULES_SHA256):
    try:
        raw = open(path, "rb").read()
    except OSError as ex:
        sys.exit(f"INPUT ERROR: rules file unreadable: {ex}")
    got = hashlib.sha256(raw).hexdigest()
    if got != want:
        print(f"INPUT ERROR: {os.path.basename(path)} sha256 {got} != pinned {want}", file=sys.stderr)
        sys.exit(2)
    return json.loads(raw.decode("utf-8"))


RULES = load_rules()
_B, _R = RULES["brief"], RULES["release"]
RETIRED = _B["retired_literal"]
RETIRED_RE = _B["retired_re"] + [p for k in _B["also_apply"]["retired"] for p in _R[k.split(".", 1)[1]]]
ADVICE_RE = _B["advice_re"] + [p for k in _B["also_apply"]["advice"] for p in _R[k.split(".", 1)[1]]]
EXPECT = _B["expect_literal"]
PRODUCER = _B["producer_literal"]
OFFER = _B["offer_literal"]
KPI_FULL = _B["kpi_full_literal"]
STALE_CAPTIONS = _B["stale_captions_literal"]
EMAIL_BANNED = _B["email_banned_literal"]
SECONDARY = _B["secondary_sources_literal"]
SOURCES_REQUIRED = _B["sources_required"]
DATELINE_BANNED = _B["dateline_banned_re"]
FRED_SAME_CLOSE = set(_B["fred_same_close_series"])

TENOR_WORDS = [(r"(?<!\d)3-month|three-month|\b3M\b", "3M"), (r"(?<!\d)6-month|six-month|\b6M\b", "6M"), (r"(?<!\d)1-year|one-year|\b1Y\b", "1Y"),
               (r"(?<!\d)2-year|two-year|\b2Y\b", "2Y"), (r"(?<!\d)3-year|three-year|\b3Y\b", "3Y"), (r"(?<!\d)5-year|five-year|\b5Y\b", "5Y"),
               (r"(?<!\d)7-year|seven-year|\b7Y\b", "7Y"), (r"(?<!\d)10-year|ten-year|\b10Y\b", "10Y"), (r"(?<!\d)20-year|twenty-year|\b20Y\b", "20Y"),
               (r"(?<!\d)30-year|thirty-year|\b30Y\b", "30Y"), (r"2s10s", "2s10s"), (r"3M-?10Y|3s10s", "3M10Y"), (r"5s30s", "5s30s")]
WEEK = r"on the week|over the week|week-over-week|\bw/w\b|a week ago|step back a week|for the week"
DAY = r"on the day|day-over-day|from the prior close|than the day before|from the previous close"
CHG_AFTER = r"\s*(?:lower|higher|up|down|steeper|flatter|below|above|tighter|wider|richer|cheaper)"
CHG_BEFORE = r"(?:\bup|\bdown|\brose|\bfell|\bgained|\blost|\badded|\bby|\bmoved|\bclimbed|\bdropped)\s+(?:about\s+|roughly\s+|some\s+)?$"


def _date_of(word, year):
    m = re.match(r"(" + MONTH_RX + r")\.?\s+(\d{1,2})", word, re.I)
    if not m:
        return None
    try:
        return dt.date(year, MONTHS[m.group(1)[:3].lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------- checks
# Each check: fn(ctx) -> list of hit strings (empty = PASS) or None (= SKIP, with reason in ctx.skip)


class Ed:
    def __init__(self, name, file_html=None, email_html=None, text=None, subject=None):
        self.name, self.file_html, self.email_html, self.text, self.subject = name, file_html, email_html, text, subject
        self.vis = {}
        self.light = {}
        for k, h in (("file", file_html), ("email", email_html)):
            if h is not None:
                self.vis[k], self.light[k] = visible(h)
        if text is not None:
            self.vis["text"] = text

    def html_texts(self):
        return {k: v for k, v in self.vis.items() if k in ("file", "email")}


def chk_email_hygiene(ed, mc, today):
    if ed.email_html is None:
        return None
    h = ed.email_html
    hits = find_all(h, EMAIL_BANNED)
    hits += [f"background shorthand: {ctx(h, m.start(), m.end())}" for m in re.finditer(r"(?<!-)background\s*:", h, re.I)]
    hits += [f"unresolved placeholder '{m.group(0)}'" for m in re.finditer(r"\{\{?[A-Za-z_][\w .]*\}?\}|\$\{[^}]*\}|\bNone\b|\bundefined\b|\bNaN\b", ed.vis["email"])]
    hits += [f"dangling dateline fragment: {ctx(ed.vis['email'], m.start(), m.end())}" for m in re.finditer(r"(?:\u00b7|\|)\s*(?:\u00b7|\||$)|\bas of (?:the)?\s*(?:\u00b7|\||$)", ed.vis["email"], re.M)]
    hits += ed.light["email"]
    return hits


def chk_provenance(ed, mc, today):
    out = []
    for k, t in ed.html_texts().items():
        out += [f"[{k}] ISO date '{m.group(0)}': {ctx(t, m.start(), m.end())}" for m in re.finditer(r"20\d\d-\d\d-\d\d", t)]
        out += [f"[{k}] {h}" for h in find_all(t, ["H.15 released", "released 20"])]
        n = len(re.findall(r"\bas of\b", t, re.I))
        if n > 3:
            out.append(f"[{k}] 'as of' appears {n} times (max 3)")
        if not re.search(r"Sources:", t):
            out.append(f"[{k}] no 'Sources:' line")
    return out if ed.html_texts() else None


def chk_retired(ed, mc, today):
    out = []
    for k, t in ed.vis.items():
        out += [f"[{k}] {h}" for h in find_all(t, RETIRED) + find_re(t, RETIRED_RE)]
    return out


def chk_advice(ed, mc, today):
    out = []
    for k, t in ed.vis.items():
        out += [f"[{k}] {h}" for h in find_re(t, ADVICE_RE)]
    return out


def chk_captions(ed, mc, today):
    if ed.name != "full":
        return []
    out = []
    for k, t in ed.vis.items():
        out += [f"[{k}] stale caption {h}" for h in find_all(t, STALE_CAPTIONS)]
        for m in re.finditer(r"\bQoQ\b|\bq/q\b|prior quarter", t, re.I):
            win = t[max(0, m.start() - 90):m.start()]
            if re.search(r"AOCI|cost of deposits|\bCOD\b|deposit cost", win, re.I):
                out.append(f"[{k}] quarter caption on a MONTHLY series: {ctx(t, m.start(), m.end())}")
    return out


def chk_market_expect(ed, mc, today):
    if mc and mc.fedwatch:
        return []
    out = []
    for k, t in ed.vis.items():
        out += [f"[{k}] no FedWatch reading in marketclose.json: {h}" for h in find_all(t, EXPECT)]
    return out


def chk_periods(ed, mc, today):
    out = []
    per = re.compile(MONTH_RX + r"|\bQ[1-4]\b|(?:first|second|third|fourth) quarter|\b20\d\d\b", re.I)
    ser = re.compile(r"\b(CPI|PCE|payrolls?|unemployment|wages|average hourly earnings|GDP)\b[^;.\n]{0,40}?[+\-\u2212]?\d[\d,]*(?:\.\d+)?\s*(%|,000|k\b)", re.I)
    for k, t in ed.vis.items():
        for s in sentences(t):
            for clause in re.split(r";", s):
                if ser.search(clause) and not per.search(clause):
                    out.append(f"[{k}] macro print without its period: '{clause.strip()[:140]}'")
    return out


def chk_item_dates(ed, mc, today):
    out = []
    for k, t in ed.html_texts().items():
        for m in re.finditer(r"(?:^|\n)[ \t\u2022\-]*(" + MONTH_RX + r")\s+20\d\d\b(?!\s*(?:CPI|PCE|payrolls|data|release|report|figures\b(?! rose)))", t):
            out.append(f"[{k}] month-only date chip '{m.group(0).strip()}': {ctx(t, m.start(), m.end())}")
    if mc is None:
        return out
    for it in mc.items:
        src = json.dumps({x: it.get(x) for x in ("source", "url", "publisher", "via")}).lower()
        name = (it.get("title") or it.get("t") or it.get("text") or "")[:70]
        if any(s in src for s in SECONDARY):
            out.append(f"[mc] {it['_kind']} item cites a secondary source ({src[:90]}): '{name}'")
        if it["_kind"] == "reg" and not (it.get("agency") or it.get("ag")):
            out.append(f"[mc] regulatory item names no agency: '{name}'")
        d = it.get("date") or it.get("d") or it.get("asOf")
        if isinstance(d, str) and re.match(r"20\d\d-\d\d$", d) is None and not re.match(r"20\d\d-\d\d-\d\d", d):
            out.append(f"[mc] item date not ISO day '{d}': '{name}'")
    return out


def _num_tokens(t):
    toks = []
    for m in re.finditer(r"\$?\d[\d,]*(?:\.\d+)?\s?(?:%|bp|bps|M\b|B\b|k\b|x\b|\u00d7)?", t):
        tok = m.group(0).strip()
        core = tok.replace(" ", "")
        if re.search(r"[%$,.]|bp|M$|B$|k$|x$|\u00d7", core) and not re.fullmatch(r"\d{1,2}\.", core):
            toks.append(core.rstrip("."))
    return toks


def chk_text_vs_html(ed, mc, today):
    if "text" not in ed.vis or not ed.html_texts():
        return None
    html_sp = norm(" ".join(ed.html_texts().values()))
    html_all = html_sp.replace(" ", "")
    out, toks = [], _num_tokens(norm(ed.vis["text"]))
    for tok in toks:
        if tok.replace(" ", "") in html_all:
            continue
        if tok.endswith("%") and re.search(r"(?<![\d.])" + re.escape(tok[:-1]) + r"(?![\d.])", html_sp):
            continue  # ladder cell printed without "%" (8 Oct email layout)
        else:
            out.append(f"plain-text figure '{tok}' not in the HTML")
    for ten in ("3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"):
        if mc and mc.curve.get(ten) is not None:
            v = f"{mc.curve[ten]:.2f}"
            if not re.search(r"\b" + ten + r"\b[^\d\n|]{0,6}" + re.escape(v) + r"(?!\d)", norm(ed.vis["text"])):
                out.append(f"plain text lacks curve tenor {ten} {v}")
    ed.token_count = (len(toks), len(out))
    return out


def chk_book_wording(ed, mc, today):
    if ed.name != "full":
        return []
    out = []
    for k, t in ed.vis.items():
        for s in sentences(t):
            if "$4.3M" in s and "whole securities portfolio" not in s:
                out.append(f"[{k}] $4.3M AOCI sentence lacks 'whole securities portfolio': '{s[:120]}'")
        out += [f"[{k}] {h}" for h in find_all(t, ["a leverage ratio"])]
    for k, t in ed.html_texts().items():
        for cap in KPI_FULL:
            if cap not in t:
                out.append(f"[{k}] KPI caption missing or altered: '{cap}'")
    return out


def chk_producer(ed, mc, today):
    out = []
    for k, t in ed.vis.items():
        out += [f"[{k}] {h}" for h in find_all(t, PRODUCER)]
        out += [f"[{k}] 'this close': {ctx(t, m.start(), m.end())}" for m in re.finditer(r"\bthis close\b", t, re.I)]
    return out


def chk_offer(ed, mc, today):
    out = []
    tenor = re.compile(r"(?<![\d.])\b(?:\d{1,2}|two|three|five|seven|ten|thirty)-(?:year|yr)\b(?!\s+(?:mortgage|fixed|(?:effective\s+)?duration|CD|APY))|\b(?:2|3|5|7|10|20|30)Y\b", re.I)
    book = re.compile(r"book yield|roll-?off|rolling off|tranche|cash flow (?:due|next)|maturing cash", re.I)
    for k, t in ed.vis.items():
        out += [f"[{k}] {h}" for h in find_all(t, OFFER)]
        for s in sentences(t):
            if book.search(s) and tenor.search(s):
                out.append(f"[{k}] named Treasury tenor beside the book: '{s[:160]}'")
    return out


def chk_change_basis(ed, mc, today):
    """9a/G4d: every 'N bp' change carries a base and equals Treasury's own change for that instrument."""
    out, claims = [], []
    year = int((mc.close if mc and mc.close else today)[:4])
    for k, t in ed.vis.items():
        for s in sentences(norm(t)):
            base = None
            wk_at = re.search(WEEK, s, re.I)
            for m in re.finditer(r"([+\-]?\d+(?:\.\d+)?)\s?bps?\b", s):
                pre, post = s[max(0, m.start() - 22):m.start()], s[m.end():m.end() + 45]
                is_change = re.match(CHG_AFTER, post, re.I) or re.search(CHG_BEFORE, pre, re.I)
                ex = re.search(r"^\s*(?:lower|higher|up|down|steeper|flatter|below|above)?\s*(?:than|since|from|below|above|vs\.?)\s+(" + MONTH_RX + r"\.?\s+\d{1,2})", post, re.I)
                if wk_at and wk_at.start() < m.start() and (base is None or base[0] != "date"):
                    base = ("week", None)
                if ex:
                    base = ("date", _date_of(ex.group(1), year))
                elif re.search(DAY, s[:m.start()] + post, re.I) and base is None:
                    base = ("day", None)
                if not is_change or base is None:
                    continue
                inst = None
                lead = s[:m.start()]
                best = -1
                for rx, nm in TENOR_WORDS:
                    for mm in re.finditer(rx, lead, re.I):
                        if mm.start() > best:
                            best, inst = mm.start(), nm
                if inst is None:
                    for rx, nm in TENOR_WORDS:
                        if re.search(rx, post, re.I):
                            inst = nm
                            break
                if inst is None:
                    out.append(f"[{k}] change with no instrument: '{s[:140]}'")
                    continue
                claims.append((k, inst, base, float(m.group(1)), post, s, bool(wk_at and wk_at.start() < m.start()), pre))
    if not claims:
        return []
    if mc is None or not mc.hist:
        return [f"{len(claims)} change claim(s) but marketclose.json carries no curve history to compute them from"] + out
    to = mc.close
    for k, inst, base, n, post, s, after_week, pre in claims:
        if base[0] == "week":
            frm = mc.back(5)
        elif base[0] == "day":
            frm = mc.back(1)
        else:
            frm = base[1]
            wk = mc.back(5)
            if after_week and wk and frm != wk:
                out.append(f"[{k}] 'week' change measured from {frm}, but five closes before {to} is {wk}: '{s[:140]}'")
        a, b = mc.value(inst, frm) if frm else None, mc.value(inst, to)
        if a is None or b is None:
            out.append(f"[{k}] cannot compute {inst} {frm}->{to} from the history: '{s[:120]}'")
            continue
        exp = round((b - a) * 100)
        if re.match(r"\s*(lower|down|below|flatter|richer)", post, re.I) or re.search(r"\b(down|fell|lost|dropped|declined|eased|slipped)\s+(?:about\s+|roughly\s+|some\s+)?$", pre, re.I) or n < 0:
            sign = -1
        elif re.match(r"\s*(higher|up|above|steeper|cheaper)", post, re.I) or re.search(r"\b(up|rose|gained|added|climbed|rallied\s+up)\s+(?:about\s+|roughly\s+|some\s+)?$", pre, re.I) or n > 0:
            sign = 1
        else:
            sign = 0
        got = abs(n) * (sign or 1)
        okv = abs(abs(n) - abs(exp)) < 0.51 and (sign == 0 or exp == 0 or (exp > 0) == (sign > 0))
        line = f"{inst} {frm}->{to}: printed {'+' if got > 0 else ''}{got:g} bp, Treasury {exp:+d} bp"
        ed.change_list = getattr(ed, "change_list", []) + [line]
        if not okv:
            out.append(f"[{k}] {line}: '{s[:140]}'")
    return out


def chk_prose_grid(ed, mc, today):
    """G1: a level stated in prose matches the grid for the same instrument and close."""
    if mc is None or not mc.curve:
        return None
    out = []
    for k, t in ed.vis.items():
        tt = norm(t)
        for rx, nm in TENOR_WORDS[:10]:
            for m in re.finditer(r"(?:" + rx + r")(?![^.;\n]{0,12}(?:mortgage|fixed|FRM|ARM))[^%.;\n]{0,28}?\b(at|to|of|near|through|above|below|over|under)\s+(\d+(?:\.\d+)?)%", tt, re.I):
                v, op, x = mc.curve.get(nm), m.group(1).lower(), float(m.group(2))
                sent = tt[max(0, tt.rfind(".", 0, m.start())):tt.find(".", m.end()) if tt.find(".", m.end()) > 0 else len(tt)]
                if v is None or re.search(r"mortgage|PMMS|Freddie|fixed-rate loan", sent, re.I) or re.search(r"\b(CD|APY|HYSA|savings|money[- ]market|deposit rate)\b", tt[m.start():m.end() + 4], re.I):
                    continue
                bad = ((op in ("at", "to", "of") and abs(v - x) > 0.005 and "." in m.group(2)) or
                       (op in ("through", "above", "over") and not v > x) or (op in ("below", "under") and not v < x) or
                       (op == "near" and abs(v - x) > 0.10))
                if bad:
                    out.append(f"[{k}] prose says {nm} {op} {x}%, grid {v:.2f}%: {ctx(tt, m.start(), m.end())}")
        for m in re.finditer(r"2-year[^.;\n]{0,20}?(\d+)\s?bp above the (\d+\.\d+)% effective", tt, re.I):
            if mc.curve.get("2Y") is not None:
                e = round((mc.curve["2Y"] - float(m.group(2))) * 100)
                if e != int(m.group(1)):
                    out.append(f"[{k}] 2Y-EFFR spread printed {m.group(1)} bp, computed {e} bp")
        for m in re.finditer(r"(2s10s|3M-?10Y|5s30s)\s*\+?(-?\d+)\s?bp|\+?(-?\d+)\s?bp\s+(2s10s|3M-?10Y|5s30s)", tt):
            nm = (m.group(1) or m.group(4)).replace("-", "")
            n = int(m.group(2) or m.group(3))
            pre = tt[max(0, m.start() - 25):m.start()]
            if re.search(r"\b(up|down|steeper|flatter|by|since)\s*$", pre, re.I) or re.match(r"\s*(steeper|flatter|since|higher|lower)", tt[m.end():m.end() + 12], re.I) \
                    or re.search(r"(steepen|flatten|widen|narrow|invert)\w*\s+(?:by\s+)?\d+\s?bp\s*$", tt[max(0, m.start() - 40):m.start()], re.I) \
                    or re.match(r"\s*(steeper|flatter|wider|narrower)", tt[m.end():m.end() + 14], re.I):
                continue
            v = mc.value(nm if nm != "3M10Y" else "3M10Y", mc.close) if mc.close else None
            if v is None and nm == "2s10s" and mc.curve.get("10Y") is not None and mc.curve.get("2Y") is not None:
                v = mc.curve["10Y"] - mc.curve["2Y"]
            if v is not None and round(v * 100) != n and abs(n) > 3:
                out.append(f"[{k}] {nm} printed {n} bp, curve gives {round(v * 100)} bp")
    return out


def chk_qbp_basis(ed, mc, today):
    """G4c: every QBP change states its basis as the FDIC does."""
    out = []
    for k, t in ed.vis.items():
        for s in sentences(t):
            if re.search(r"Quarterly Banking Profile|\bQBP\b|FDIC'?s? Q[1-4]|FDIC[^.]{0,60}\b(industry|net interest margin|NIM|net income|domestic deposits|noncurrent|unrealized losses)", s, re.I) \
                    and re.search(r"\b(up|down|rose|fell|increased|decreased|declined|gain(?:ed)?)\b[^.]{0,30}?\d+(?:\.\d+)?\s?(?:%|bp|basis point|percent|billion|million)", s, re.I) \
                    and not re.search(r"\b(proposed|proposal|final rule|comment period|assessment rate|issued|approved)\b", s, re.I) and not re.search(r"from the prior quarter|from a year ago|from the previous quarter|quarter over quarter|from Q[1-4]|year over year|from the first quarter|from the second quarter", s, re.I):
                out.append(f"[{k}] QBP change without its comparison basis: '{s[:160]}'")
    return out


MON_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _human(d):
    y, m, dd = (int(x) for x in d.split("-"))
    return f"{MON_ABBR[m - 1]} {dd}"


def chk_sofr_avg(ed, mc, today):
    """G2a (12 Oct 2026): a printed 30-day SOFR average equals marketclose.json and, when its NY Fed date differs
    from SOFR's, carries its own date on the same line. 12 Oct: the Oct 9 record (3.82%) printed under "Oct 8"."""
    if mc is None or mc.sofr30 is None:
        return None
    v, d = mc.sofr30
    hd = _human(d)
    out = []
    for k, t in ed.vis.items():
        for m in re.finditer(r"30-day (?:average )?SOFR(?: average)?(?:\s*\([^)\n]{0,20}\))?[^0-9%\n]{0,25}?(\d+\.\d\d)%", t, re.I):
            if abs(float(m.group(1)) - round(v, 2)) > 0.005:
                out.append(f"[{k}] 30-day SOFR average printed {m.group(1)}%, object {v:.2f}% ({hd}): {ctx(t, m.start(), m.end(), 30)}")
            if mc.sofr_asof and mc.sofr_asof != d:
                line = t[t.rfind("\n", 0, m.start()) + 1: (t.find("\n", m.end()) if t.find("\n", m.end()) >= 0 else len(t))]
                if not re.search(r"\b" + re.escape(hd) + r"\b", line):
                    out.append(f"[{k}] 30-day SOFR average without its own date ({hd}; SOFR is {_human(mc.sofr_asof)}): {ctx(t, m.start(), m.end(), 40)}")
    return out


def chk_dashes(ed, mc, today):
    """STEP 3: true minus for negatives and en dash for ranges, in the HTML (plain text is ASCII by design)."""
    out = []
    for k, t in ed.html_texts().items():
        out += [f"[{k}] hyphen-minus negative: {ctx(t, m.start(), m.end(), 25)}" for m in re.finditer(r"(?<![\w.\-\u2013/])-\$?\d", t)]
        out += [f"[{k}] hyphen in a numeric range: {ctx(t, m.start(), m.end(), 25)}" for m in re.finditer(r"\d\.\d+-\d+(?:\.\d+)?%", t)]
    return out


def chk_brand(ed, mc, today):
    out = []
    for k, t in list(ed.vis.items()) + ([("subject", ed.subject)] if ed.subject else []):
        out += [f"[{k}] bare masterbrand: {ctx(t, m.start(), m.end(), 30)}" for m in re.finditer(r"\bSetnova\b(?!\s+Advisory)", t, re.I)]
    return out


def chk_sources(ed, mc, today):
    """src (13 Oct 2026): every figure family or agency in the body is named in the one Sources line."""
    out = []
    for k, t in ed.vis.items():
        ms = list(re.finditer(r"\bSources:", t))
        if not ms:
            continue  # 5b6 reports a missing Sources line
        body, foot = t[:ms[-1].start()], t[ms[-1].end():ms[-1].end() + 600]
        for r in SOURCES_REQUIRED:
            hit = re.search(r["body_re"], body)
            if hit and not re.search(r["sources_re"], foot):
                out.append(f"[{k}] {r['label']}: the body has '{hit.group(0)}' but the Sources line names no /{r['sources_re']}/")
    return out


def chk_dateline(ed, mc, today):
    """dateline (13 Oct 2026, RELEASE-QUEUE Q4): no single market as-of over figures that carry other dates."""
    out = []
    for k, t in ed.vis.items():
        out += [f"[{k}] {h}" for h in find_re(t, DATELINE_BANNED)]
    return out


def chk_fred(mc):
    """G2b (13 Oct 2026): FRED freshness from the data-file header (fred.stlouisfed.org/data/<ID>.txt) the run recorded.
    Series pages and CSVs can serve a stale cache (9 Oct); FX had no check at all (10 Oct close-out, 'item 8')."""
    if mc is None:
        return None
    out = []
    for path, o in mc.fred_figs:
        sid, a = o.get("series"), o["asOf"][:10]
        if not sid:
            out.append(f"{path}: FRED figure (asOf {a}) carries no \"series\" id")
            continue
        h = mc.fred_headers.get(str(sid))
        end = str((h or {}).get("range_end", ""))[:10]
        if not re.match(r"20\d\d-\d\d-\d\d$", end):
            out.append(f"{path}: no fred_headers.{sid}.range_end recorded (read fred.stlouisfed.org/data/{sid}.txt)")
            continue
        if a > end:
            out.append(f"{path}: {sid} asOf {a} is after FRED's last observation {end}")
        elif sid in FRED_SAME_CLOSE:
            if mc.close and a != mc.close:
                out.append(f"{path}: {sid} asOf {a} is not the curve's close {mc.close}")
        elif a != end:
            out.append(f"{path}: {sid} printed for {a} but FRED's data file runs to {end} (stale)")
    return out


REOPEN_SEC = re.compile(r"(\d+)-(week|month|year)(?:\s+(TIPS|FRN|bond|note|bill)s?)?", re.I)
REOPEN_TXT = re.compile(r"(\d+)-(week|month|year)(?:\s+(TIPS|FRN|bond|note|bill)s?)?\s+(?:auction\s+)?\(?reopen(?:ing|ed)\b", re.I)


def _sec_key(m):
    typ = (m.group(3) or "").upper().rstrip("S")
    return int(m.group(1)), m.group(2).lower(), {"BOND": "", "NOTE": "", "BILL": ""}.get(typ, typ)


def chk_auction_reopening(ed, mc, today):
    """auct (14 Oct 2026, RELEASE-QUEUE Q7): an auction is called a "reopening" only when marketclose.json records
    "reopening": true for that security from TreasuryDirect's schedule (marked "R"). 14 Oct: "5-year TIPS reopening
    auction Thu Oct 22" printed for an original issue (the schedule marks it "T"); Number Verifier HOLD."""
    if mc is None:
        return None
    recs = []
    for sec, flag, d in mc.auctions:
        m = REOPEN_SEC.search(sec)
        if m:
            recs.append((_sec_key(m), flag, sec))
    out = []
    for k, t in ed.vis.items():
        named = set()
        for m in REOPEN_TXT.finditer(t):
            named.add(m.start())
            key = _sec_key(m)
            same = [r for r in recs if r[0] == key or (not key[2] and r[0][:2] == key[:2] and r[0][2] not in ("TIPS", "FRN"))]
            if not mc.auctions:
                out.append(f"[{k}] 'reopening' printed but marketclose.json records no auction with a \"reopening\" flag: {ctx(t, m.start(), m.end(), 30)}")
            elif not same:
                out.append(f"[{k}] '{m.group(0)}': no auction record for that security in marketclose.json: {ctx(t, m.start(), m.end(), 30)}")
            elif not any(r[1] for r in same):
                out.append(f"[{k}] '{m.group(0)}': the schedule record ({same[0][2]}) is an original issue, not a reopening: {ctx(t, m.start(), m.end(), 30)}")
        for m in re.finditer(r"\breopen(?:ing|ed)\b", t, re.I):
            if not any(s <= m.start() <= s + 60 for s in named):
                out.append(f"[{k}] 'reopening' printed without a named security (\"5-year TIPS\"): {ctx(t, m.start(), m.end(), 40)}")
    return out


APOS = "['\u2019]"
BKR_SUPER = [
    r"\btop\s+APY\b",
    r"(?<!stated )\btop of Bankrate" + APOS + r"s\b",
    r"(?<!stated )\btop\b[^.%\n]{0,60}?\bon Bankrate" + APOS + r"s\b",
    r"Bankrate" + APOS + r"s\s+(?:best[- ]rate\s+)?lists?\b[^.%\n]{0,30}?\b(?:top|highest|best)\b",
    r"(?<!stated )\b(?:top|highest|best|leading)\s+(?:(?:\d+|one|six|twelve)[- ](?:month|year)\s+CD|CD|high-yield savings|savings|money[- ]market)\b",
]
BKR_UNNAMED = [
    r"first in Bankrate" + APOS + r"s ranked list(?!\s*\([^)]+\))",
    r"Bankrate" + APOS + r"s stated top rate(?!\s*\([^)]+\))",
]


def chk_headline_vs_list(ed, mc, today):
    """bkr (22 Oct 2026, HEADLINE VS LIST): a deposit rate from Bankrate is printed with exactly one of two labels,
    each naming the institution: "first in Bankrate's ranked list (Peak Bank)" or "Bankrate's stated top rate
    (Openbank)". Any other superlative ("Top APY", "top of Bankrate's list", "the top high-yield savings APY") FAILs.
    21 and 22 Oct: Bankrate's page said "Today's top savings rate is 4.35% APY offered by Openbank" while its ranked
    list began at 4.27% (Peak Bank); "Top of Bankrate's list" failed the Number Verifier with either figure, and both
    runs were HELD."""
    out = []
    for k, t in ed.vis.items():
        for pat in BKR_SUPER:
            for m in re.finditer(pat, t, re.I):
                out.append(f"[{k}] superlative on a Bankrate figure (use \"first in Bankrate's ranked list (Institution)\" or \"Bankrate's stated top rate (Institution)\"): {ctx(t, m.start(), m.end(), 40)}")
        for pat in BKR_UNNAMED:
            for m in re.finditer(pat, t, re.I):
                out.append(f"[{k}] Bankrate label without the institution in brackets: {ctx(t, m.start(), m.end(), 40)}")
    return out


CHECKS = [
    ("5b5", "email hygiene and contrast", chk_email_hygiene),
    ("5b6", "provenance leak", chk_provenance),
    ("5b7", "stale sample-book captions / QoQ on monthly", chk_captions),
    ("5b7b", "retired wording", chk_retired),
    ("5b8", "advice language", chk_advice),
    ("9a", "change basis computed per instrument", chk_change_basis),
    ("9b", "market-expectations claims", chk_market_expect),
    ("9c", "macro prints name their period", chk_periods),
    ("9d", "item dates and primary sources", chk_item_dates),
    ("9e", "plain text = HTML", chk_text_vs_html),
    ("9f", "Full Desk Read book wording", chk_book_wording),
    ("9g", "producer-facing wording", chk_producer),
    ("9h", "unconfirmed offers / tenor against the book", chk_offer),
    ("G1", "prose matches the grid", chk_prose_grid),
    ("G4c", "QBP comparison basis", chk_qbp_basis),
    ("G2a", "30-day SOFR average value and its own date", chk_sofr_avg),
    ("dash", "minus signs and en dashes", chk_dashes),
    ("brand", "Setnova Advisory branding only", chk_brand),
    ("src", "Sources line names every source used", chk_sources),
    ("dateline", "no single market as-of over mixed dates", chk_dateline),
    ("auct", "an auction is a reopening only if the schedule says so", chk_auction_reopening),
    ("bkr", "headline vs list: Bankrate rates name which figure they are", chk_headline_vs_list),
]


G8_GAP = r"(?:(?!EFFR|SOFR|IORB|ON RRP|\bRRP\b|discount|effective|fed(?:eral)? funds|target|prime)[^%\n]){0,25}?"


def chk_g8(eds, mc):
    """G8: shared figures identical across editions and equal to marketclose.json."""
    if len(eds) < 2 or mc is None:
        return None
    out = []
    for ed in eds:
        for k, t in ed.html_texts().items():
            for ten in ("3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"):
                v = mc.curve.get(ten)
                if v is None:
                    out.append(f"marketclose.json has no {ten}")
                elif f"{v:.2f}%" not in t and not re.search(r"(?<![\d.])" + re.escape(f"{v:.2f}") + r"(?![\d.%])(?!\s*bp)", t):
                    out.append(f"[{ed.name}/{k}] curve {ten} {v:.2f}% not printed")
            for lab, rx in (("EFFR", r"EFFR|effective (?:federal )?funds rate"), ("SOFR", r"(?<!average )(?<!avg )(?<!day )\bSOFR\b(?! 30)(?!\s+(?:average|avg))"), ("IORB", r"\bIORB\b")):
                if lab in mc.rates:
                    # 14 Oct 2026 (RELEASE-QUEUE Q8): the figure must belong to this label, so the gap may not cross another
                    # rate label. The first pass read "SOFR ... for Oct 9 · IORB 3.90%" as SOFR 3.90% (4 false alarms).
                    for m in re.finditer(r"(?:" + rx + r")" + G8_GAP + r"(\d+\.\d\d)%", t, re.I):
                        if abs(float(m.group(1)) - mc.rates[lab]) > 0.005:
                            out.append(f"[{ed.name}/{k}] {lab} printed {m.group(1)}%, object {mc.rates[lab]:.2f}%")
    return out


def run(eds, mc, today):
    rows = []
    for cid, title, fn in CHECKS:
        for ed in eds:
            try:
                r = fn(ed, mc, today)
            except Exception as e:  # a crashed check is a FAIL, never a pass
                r = [f"checker error: {type(e).__name__}: {e}"]
            rows.append({"check": cid, "title": title, "edition": ed.name,
                         "status": "SKIP" if r is None else ("PASS" if not r else "FAIL"), "hits": r or []})
    g8 = chk_g8(eds, mc)
    rows.append({"check": "G8", "title": "cross-edition consistency", "edition": "both",
                 "status": "SKIP" if g8 is None else ("PASS" if not g8 else "FAIL"), "hits": g8 or []})
    try:
        g2b = chk_fred(mc)
    except Exception as e:
        g2b = [f"checker error: {type(e).__name__}: {e}"]
    rows.append({"check": "G2b", "title": "FRED figures as fresh as FRED's data file", "edition": "object",
                 "status": "SKIP" if g2b is None else ("PASS" if not g2b else "FAIL"), "hits": g2b or []})
    return rows


def report(rows, eds):
    lines = []
    for r in rows:
        lines.append(f"{r['status']:4}  {r['check']:5} {r['edition']:8} {r['title']}" + (f"  ({len(r['hits'])} hits)" if r["hits"] else ""))
        for h in r["hits"][:25]:
            lines.append(f"        - {h}")
        if len(r["hits"]) > 25:
            lines.append(f"        - ... {len(r['hits']) - 25} more")
    for ed in eds:
        if hasattr(ed, "token_count"):
            lines.append(f"9e {ed.name}: {ed.token_count[0]} plain-text numeric tokens checked, {ed.token_count[1]} missing from the HTML")
        for c in getattr(ed, "change_list", []):
            lines.append(f"9a {ed.name}: {c}")
    fails = sum(r["status"] == "FAIL" for r in rows)
    lines.append(f"RESULT: {'FAIL' if fails else 'PASS'} ({fails} failing check(s); SKIP never counts as PASS for a check whose input was supplied)")
    return "\n".join(lines), fails


# ---------------------------------------------------------------- self-test
MC_FIX = {
    "schema": "setnova-marketclose-1.0",
    "curve": {t: {"value": v, "source": "home.treasury.gov", "asOf": "2026-10-08"} for t, v in
              {"3M": 4.23, "6M": 4.30, "1Y": 4.44, "2Y": 4.75, "3Y": 4.82, "5Y": 4.99, "7Y": 5.10, "10Y": 5.22, "20Y": 5.55, "30Y": 5.60}.items()},
    "curve_history": {
        "2026-10-01": {"3M": 4.22, "2Y": 4.73, "5Y": 4.98, "10Y": 5.24, "30Y": 5.61},
        "2026-10-02": {"3M": 4.22, "2Y": 4.74, "5Y": 5.00, "10Y": 5.26, "30Y": 5.63},
        "2026-10-05": {"3M": 4.23, "2Y": 4.76, "5Y": 5.02, "10Y": 5.27, "30Y": 5.66},
        "2026-10-06": {"3M": 4.23, "2Y": 4.77, "5Y": 5.03, "10Y": 5.29, "30Y": 5.68},
        "2026-10-07": {"3M": 4.23, "2Y": 4.77, "5Y": 5.03, "10Y": 5.28, "30Y": 5.67}},
    "policy": {"EFFR": {"value": 3.88, "source": "newyorkfed.org", "asOf": "2026-10-07"},
               "SOFR": {"value": 3.88, "source": "newyorkfed.org", "asOf": "2026-10-07"},
               "IORB": {"value": 3.90, "source": "federalreserve.gov", "asOf": "2026-10-08"},
               "sofr_30d_avg": {"value": 3.79, "source": "markets.newyorkfed.org sofrai", "asOf": "2026-10-08"}},
    "fx": {"eur_usd": {"value": 1.1259, "source": "FRED DEXUSEU (Fed H.10)", "asOf": "2026-10-02", "series": "DEXUSEU"}},
    "equities": {"sp500": {"value": 7765.36, "source": "FRED SP500", "asOf": "2026-10-08", "series": "SP500"}},
    "fred_headers": {"DEXUSEU": {"last_updated": "2026-10-05 3:16 PM CDT", "range_end": "2026-10-02"},
                     "SP500": {"last_updated": "2026-10-08 7:01 PM CDT", "range_end": "2026-10-08"}},
    "auctions": [{"security": "20-year bond", "date": "2026-10-21", "reopening": True, "source": "treasurydirect.gov tentative auction schedule"},
                 {"security": "5-year TIPS", "date": "2026-10-22", "reopening": False, "source": "treasurydirect.gov tentative auction schedule"}],
    "news": [{"date": "2026-08-25", "title": "FDIC Quarterly Banking Profile Q2 2026", "source": "fdic.gov"}],
    "reg": [{"date": "2026-08-12", "agency": "OCC/FDIC", "title": "CRA proposal", "source": "federalregister.gov"}],
}
CMN = ("<p>Friday, October 9, 2026 \u00b7 Treasury curve as of Oct 8 close \u00b7 Fed funds 3.75\u20134.00% (raised Sep 16)</p>"
       "<p>August headline CPI ran 3.4% and August headline PCE 3.4% (core CPI 2.4%, core PCE 3.0%); September payrolls slowed to +29,000 and the unemployment rate rose to 4.2%.</p>"
       "<p>The curve stayed positively sloped at the October 8 close, the 2-year at 4.75% and the 10-year at 5.22%, a +47 bp 2s10s slope; the 10-year closed 6 bp below October 7 and the 30-year 7 bp lower at 5.60%. "
       "On the week the 10-year was 2 bp lower than October 1. The 2-year sits 87 bp above the 3.88% effective funds rate. "
       "The FDIC reported the Q2 2026 net interest margin up 1 basis point from the prior quarter to 3.32%.</p>"
       "<p>3M 4.23% \u00b7 6M 4.30% \u00b7 1Y 4.44% \u00b7 2Y 4.75% \u00b7 5Y 4.99% \u00b7 10Y 5.22% \u00b7 30Y 5.60% \u00b7 2s10s +47 bp \u00b7 3M\u201310Y +99 bp \u00b7 5s30s +61 bp</p>"
       "<p>EFFR 3.88% \u00b7 SOFR 3.88% \u00b7 IORB 3.90%</p>"
       "<p>The 30-day average SOFR (Oct 8) was 3.79%.</p>"
       "<p>The long end rallied on the day (the 10-year 6 bp below October 7, the 30-year 7 bp lower at 5.60%) and the curve was little changed on the week. "
       "Freddie Mac's survey put the 30-year fixed at 7.40% and the 15-year at 6.73%, both up from the prior week (7.28% / 6.60%).</p>"
       "<p>The 30-year fell 7 bp from October 7. The 2s10s slope steepened 15 bp to +41 bp since September 30. The 1-year CD APY first in Bankrate's ranked list (Example Bank) was 4.45%. "
       "The FDIC increased its staffing for bank examinations. WED 14: Personal Income &amp; Outlays, August 2026 \u00b7 8:30 ET.</p>"
       "<p>Ahead: 20-year bond reopening auction Wed Oct 21; 5-year TIPS auction Thu Oct 22.</p>")
FULL_BODY = ("<p>NIM 3.32% (7 consecutive quarterly increases) \u00b7 Cost of deposits 1.92% (beta 34% vs 45% modeled) \u00b7 AOCI \u2212$41.4M (up $4.6M over three months, less negative) \u00b7 "
             "Loans / deposits 85.1% ($1,910M / $2,245M) \u00b7 Avail. liquidity $1,017M (37.0% of assets) \u00b7 Uninsured 27% (1.7\u00d7 covered) \u00b7 Tier 1 leverage ratio 9.6% (vs 8.5% internal floor) \u00b7 EVE +300 \u221214.6% (watch \u221213.75% / limit \u221225%)</p>"
             "<p>Each 25 bp between that book yield and whatever it earns next is on the order of $313k a year, gross, full-year, full deployment ($125M \u00d7 0.25%). "
             "AOCI sensitivity \u2248 $4.3M per 25 bp, taken at the whole securities portfolio\u2019s 4.2-year effective duration (the book states no AFS-only duration). The roughly $125M of cash flow is measured at the book's 4.2-year effective duration.</p>")
FOOT = "<p>Sources: Federal Reserve H.15 &amp; FOMC; NY Fed/FRED; U.S. Treasury; BLS; BEA; Freddie Mac PMMS; FDIC QBP; Bankrate (retrieved Oct 9, 2026).</p>"


def _email(body, banner):
    return ('<table width="700" bgcolor="#eef1f5" style="background-color:#eef1f5"><tr><td>'
            f'<table width="700" bgcolor="#FFFFFF" style="background-color:#FFFFFF"><tr><td bgcolor="#C07A34" style="background-color:#C07A34;color:#ffffff">{banner}</td></tr>'
            '<tr><td bgcolor="#0A2A5E" style="background-color:#0A2A5E"><span style="color:#35B2C2">SETNOVA ADVISORY \u00b7 TREASURY &amp; ALM</span><h1 style="color:#ffffff">Treasury Brief</h1></td></tr>'
            f'<tr><td style="color:#1c2531">{body}{FOOT}</td></tr></table></td></tr></table>')


def _file(body):
    return f"<html><head><style>.x{{color:#0A2A5E}}</style></head><body><div class=\"x\">{body}{FOOT}</div></body></html>"


def _text(body):
    return visible(body + FOOT)[0]


def _fixture():
    return {"full": dict(file_html=_file(CMN + FULL_BODY), email_html=_email(CMN + FULL_BODY, "FULL DESK READ"), text=_text(CMN + FULL_BODY)),
            "generic": dict(file_html=_file(CMN), email_html=_email(CMN, "DESK READ"), text=_text(CMN))}


# (check id, edition, which part to mutate, old, new, why) - one per shipped error
SEEDS = [
    ("5b5", "full", "email_html", '<tr><td bgcolor="#0A2A5E" style="background-color:#0A2A5E">', '<tr><td style="background:#0A2A5E">', "26 Aug: navy masthead lost, white text on white"),
    ("5b5", "generic", "email_html", "</td></tr></table></td></tr></table>", '<img src="cid:logo"></td></tr></table></td></tr></table>', "26 Aug: cid images stripped by Gmail"),
    ("5b5", "full", "email_html", "Treasury curve as of Oct 8 close", "Treasury curve as of the", "26 Aug: dangling dateline fragment"),
    ("5b6", "generic", "file_html", "Treasury curve as of Oct 8 close", "Treasury curve as of 2026-10-08 close (H.15 released 2026-10-09)", "28 Aug: ISO dates and release mechanics"),
    ("5b7", "full", "email_html", "up $4.6M over three months", "improved $6.3M QoQ", "3 Sep: stale AOCI caption"),
    ("5b7", "full", "text", "up $4.6M over three months", "up $4.6M QoQ", "29 Sep/30 Sep: QoQ on a monthly series"),
    ("5b7b", "generic", "email_html", "EFFR 3.88%", "DXY 99.2 \u00b7 EFFR 3.88%", "25 Sep: broad dollar labelled DXY"),
    ("5b7b", "full", "file_html", "Tier 1 leverage ratio 9.6%", "Tier-1 capital ratio 9.6%", "leverage ratio misnamed"),
    ("5b8", "generic", "text", "The 2-year sits", "Banks should consider extending duration. The 2-year sits", "24 Sep: advice language"),
    ("9a", "generic", "email_html", "On the week the 10-year was 2 bp lower than October 1.", "On the week the 10-year was up 21 bp and the 5-year 21 bp higher.", "28 Sep: one week number shared across two tenors"),
    ("9a", "full", "text", "the 10-year closed 6 bp below October 7", "the 10-year closed 6 bp above October 7", "25 Sep: direction word against the numbers"),
    ("9b", "generic", "file_html", "The 2-year sits", "Market pricing leans toward a hold. The 2-year sits", "28 Sep: expectations claim with no FedWatch"),
    ("9c", "full", "email_html", "August headline CPI ran 3.4% and August headline PCE 3.4%", "Headline CPI ran 3.4% and headline PCE 3.4%", "28 Sep: CPI and PCE with no months"),
    ("9d", "generic", "file_html", "</p><p>EFFR", "</p><p>Sep 2026 FDIC insured-deposit figures rose.</p><p>EFFR", "28 Sep: month-only item chip"),
    ("9e", "full", "text", "Sources:", "Labor/growth: August payrolls +162,000, Q2 GDP +1.5%. Sources:", "29 Sep: plain-text line the HTML lacked"),
    ("9f", "full", "email_html", "taken at the whole securities portfolio\u2019s 4.2-year", "taken at a 4.2-year", "AOCI sentence missing the portfolio basis"),
    ("9f", "full", "file_html", "vs 8.5% internal floor", "a leverage ratio", "tautological KPI caption"),
    ("9g", "generic", "email_html", "</p><p>EFFR", " Curve chart is shown in the file and PDF editions.</p><p>EFFR", "29 Sep: producer-facing note"),
    ("9g", "full", "text", "Sources:", "FHLB omitted, not retrieved this close. Sources:", "28 Sep: note to the producer"),
    ("9g", "generic", "email_html", "</p><p>EFFR", " Full sources in the footer line.</p><p>EFFR", "1/5 Oct: producer note in the body"),
    ("9a", "generic", "text", "The 30-year fell 7 bp from October 7.", "The 30-year rose 7 bp from October 7.", "direction word before the number"),
    ("9h", "generic", "file_html", "Sources:", "Full PDF edition available on request. Sources:", "28/29 Sep: unconfirmed offer"),
    ("9h", "full", "email_html", "Each 25 bp between that book yield", "Against the 2.95% book yield and the 5.06% 5-year par level, each 25 bp between that book yield", "29 Sep: named tenor against the book"),
    ("G1", "generic", "text", "the 10-year at 5.22%", "the 10-year at 5.31%", "24 Sep: prose level not the grid's"),
    ("G1", "full", "email_html", "a +47 bp 2s10s slope", "a +26 bp 2s10s slope", "25 Sep: slope stated against the grid"),
    ("G4c", "full", "file_html", "up 1 basis point from the prior quarter to 3.32%", "up 1 basis point to 3.32%", "25 Sep: QBP change with no basis"),
    ("G2a", "generic", "email_html", "The 30-day average SOFR (Oct 8) was 3.79%.", "The 30-day average SOFR was 3.79%.", "12 Oct: average printed without its own NY Fed date"),
    ("G2a", "full", "text", "(Oct 8) was 3.79%", "(Oct 8) was 3.82%", "12 Oct: average value not the object's"),
    ("dash", "full", "email_html", "\u221214.6%", "-14.6%", "hyphen-minus negative"),
    ("brand", "generic", "email_html", "Treasury Brief", "Setnova Treasury Morning Brief", "bare masterbrand (F4)"),
    ("G8", "generic", "file_html", "6M 4.30%", "6M 4.31%", "21 Aug: editions disagree"),
    # 13 Oct 2026: shared rules file (#5), the release gate's lists now also apply to the brief, and three new checks.
    ("5b7b", "full", "text", "The 2-year sits", "The CD tower rolls next quarter. The 2-year sits", "release-gate vocabulary (CD tower), now shared"),
    ("5b8", "generic", "email_html", "The 2-year sits", "Banks can lock in term funding here. The 2-year sits", "13 Oct: 'lock in term funding' passed the old pattern"),
    ("5b8", "full", "file_html", "The 2-year sits", "Duration positioning matters now. The 2-year sits", "release gate Shelf B, now shared"),
    ("src", "generic", "email_html", "</p><p>EFFR", " WTI spot $96.24 (Oct 6).</p><p>EFFR", "13 Oct shadow: oil printed, EIA not in the Sources line"),
    ("src", "full", "text", "The FDIC increased", "NCUA reported assets of $2.50 trillion. The FDIC increased", "13 Oct shadow: NCUA figures, NCUA not in the Sources line"),
    ("dateline", "generic", "email_html", "Treasury curve as of Oct 8 close", "Market data as of Oct 8 close", "13 Oct Number Verifier HOLD: one as-of over mixed dates (Q4)"),
    # 14 Oct 2026: RELEASE-QUEUE Q7 and Q8.
    ("auct", "generic", "text", "5-year TIPS auction", "5-year TIPS reopening auction", "14 Oct Number Verifier HOLD: original-issue TIPS called a reopening (Q7)"),
    ("auct", "full", "email_html", "5-year TIPS auction Thu Oct 22.", "5-year TIPS auction Thu Oct 22; the 10-year reopening follows.", "reopening with no schedule record for that security"),
    ("G8", "generic", "email_html", "SOFR 3.88% \u00b7 IORB", "SOFR 3.91% \u00b7 IORB", "SOFR printed off the object (still caught after the Q8 tightening)"),
    # 22 Oct 2026: HEADLINE VS LIST (Number Verifier HOLD on 21 and 22 Oct, high-yield savings row).
    ("bkr", "generic", "email_html", "The 1-year CD APY first in Bankrate's ranked list (Example Bank) was 4.45%.", "High-yield savings: 4.27% (Top of Bankrate's list for high-yield savings).", "22 Oct NV HOLD: 'Top of Bankrate's list' on a figure the page's own headline contradicts"),
    ("bkr", "full", "text", "The 1-year CD APY first in Bankrate's ranked list (Example Bank) was 4.45%.", "On Bankrate's best-rate lists the top 12-month CD APY is 4.60%.", "22 Oct NV HOLD: Funding & Deposit Market sentence calls a list figure 'the top'"),
    ("bkr", "generic", "file_html", "The 1-year CD APY first in Bankrate's ranked list (Example Bank) was 4.45%.", "The top high-yield savings APY on Bankrate was 4.35%.", "21 Oct NV HOLD: 'top' with no statement of which Bankrate figure"),
    ("bkr", "full", "email_html", "The 1-year CD APY first in Bankrate's ranked list (Example Bank) was 4.45%.", "Product \u00b7 Top APY \u00b7 Institution. 1-year CD 4.45%.", "the 'Top APY' column header (prompt wording until 22 Oct)"),
    ("bkr", "generic", "text", "(Example Bank) was", "was", "label used without naming the institution"),
    ("bkr", "full", "file_html", "first in Bankrate's ranked list (Example Bank)", "Bankrate's stated top rate", "stated-top label without the institution"),
]

# (why, mutation of a deep copy of MC_FIX) for the object-level G2b check
MC_SEEDS = [
    ("13 Oct: FX printed for Oct 2 while FRED's data file already runs to Oct 9 (stale)",
     lambda m: m["fred_headers"]["DEXUSEU"].update(range_end="2026-10-09")),
    ("FRED figure with no data-file header recorded", lambda m: m["fred_headers"].pop("SP500")),
    ("FRED figure with no series id", lambda m: m["fx"]["eur_usd"].pop("series")),
    ("equity close not the curve's close", lambda m: m["equities"]["sp500"].update(asOf="2026-10-07")),
    ("9 Oct: a date FRED does not have yet", lambda m: m["fx"]["eur_usd"].update(asOf="2026-10-05")),
]

# (check id, why, mutation of a deep copy of MC_FIX): an edition check that must FAIL once the object changes
MC_ED_SEEDS = [
    ("auct", "14 Oct: 'reopening' printed with no schedule flag recorded in marketclose.json", lambda m: m.pop("auctions")),
    ("auct", "the schedule record says original issue", lambda m: m["auctions"][0].update(reopening=False)),
]


def self_test():
    mc = MC(MC_FIX)
    fx = _fixture()
    eds = [Ed(n, **p) for n, p in fx.items()]
    rows = run(eds, mc, "2026-10-09")
    bad = [r for r in rows if r["status"] == "FAIL"]
    ok = True
    if bad:
        ok = False
        print("CLEAN FIXTURE FAILED (false positives):")
        print(report(bad, [])[0])
    else:
        print(f"clean fixture: {sum(r['status'] == 'PASS' for r in rows)} checks PASS, 0 FAIL")
    for cid, ed_name, part, old, new, why in SEEDS:
        f2 = _fixture()
        src = f2[ed_name][part]
        if old not in src:
            print(f"  SEED BROKEN  {cid:5} {why}: anchor '{old[:40]}' not in {ed_name}.{part}")
            ok = False
            continue
        f2[ed_name][part] = src.replace(old, new, 1)
        rs = run([Ed(n, **p) for n, p in f2.items()], mc, "2026-10-09")
        hit = [r for r in rs if r["check"] == cid and r["status"] == "FAIL"]
        print(f"  {'caught' if hit else 'MISSED'}  {cid:5} {why}")
        ok &= bool(hit)
    import copy
    for why, mut in MC_SEEDS:
        m2 = copy.deepcopy(MC_FIX)
        mut(m2)
        rs = run([Ed(n, **pp) for n, pp in _fixture().items()], MC(m2), "2026-10-09")
        hit = [r for r in rs if r["check"] == "G2b" and r["status"] == "FAIL"]
        print(f"  {'caught' if hit else 'MISSED'}  G2b   {why}")
        ok &= bool(hit)
    for cid, why, mut in MC_ED_SEEDS:
        m2 = copy.deepcopy(MC_FIX)
        mut(m2)
        rs = run([Ed(n, **pp) for n, pp in _fixture().items()], MC(m2), "2026-10-09")
        hit = [r for r in rs if r["check"] == cid and r["status"] == "FAIL"]
        print(f"  {'caught' if hit else 'MISSED'}  {cid:5} {why}")
        ok &= bool(hit)
    # Regression (14 Oct 2026, Q8): a grid note naming SOFR and EFFR's date, then IORB, is not a SOFR or EFFR figure.
    note = CMN.replace("<p>EFFR 3.88% \u00b7 SOFR 3.88% \u00b7 IORB 3.90%</p>",
                       "<p>EFFR 3.88% \u00b7 SOFR 3.88% \u00b7 IORB 3.90%</p><p>SOFR and EFFR for Oct 7 \u00b7 IORB 3.90% per the FOMC note.</p>")
    q8 = [Ed("full", email_html=_email(note + FULL_BODY, "FULL DESK READ")), Ed("generic", email_html=_email(note, "DESK READ"))]
    g8 = [r for r in run(q8, mc, "2026-10-09") if r["check"] == "G8" and r["status"] == "FAIL"]
    if g8:
        ok = False
        print("REGRESSION 14 Oct G8 window FAILED:")
        print(report(g8, [])[0])
    else:
        print("  regression 14 Oct 'SOFR ... for Oct 9 · IORB 3.90%' grid note: no G8 false positive")
    # Regression (8 Oct 2026): email-only editions whose HTML ladder prints bare numbers, plus a 30-day SOFR average.
    lad = "<table><tr>" + "".join(f"<td>{t}</td>" for t in ("3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y")) + "</tr><tr>" + \
          "".join(f"<td>{v}</td>" for v in ("4.23", "4.30", "4.44", "4.75", "4.99", "5.22", "5.60")) + "</tr></table>"
    old_lad = CMN[CMN.index("<p>3M 4.23%"):CMN.index("</p>", CMN.index("<p>3M 4.23%")) + 4]
    body = CMN.replace(old_lad, lad + "<p>2s10s +47 bp \u00b7 3M\u201310Y +99 bp \u00b7 5s30s +61 bp</p>").replace(
        "IORB 3.90%</p>", "IORB 3.90%; 30-day average SOFR (Oct 8) 3.79%.</p>")
    reg = [Ed("full", email_html=_email(body + FULL_BODY, "FULL DESK READ"), text=_text(CMN + FULL_BODY)),
           Ed("generic", email_html=_email(body, "DESK READ"), text=_text(CMN))]
    bad = [r for r in run(reg, mc, "2026-10-09") if r["status"] == "FAIL"]
    if bad:
        ok = False
        print("REGRESSION 8 Oct ladder/SOFR-average FAILED:")
        print(report(bad, [])[0])
    else:
        print("  regression 8 Oct ladder without % and 30-day SOFR average: no false positives")
    # Regression (22 Oct 2026, bkr): both permitted Bankrate labels, in a table row and a sentence, pass.
    okb = CMN.replace("The 1-year CD APY first in Bankrate's ranked list (Example Bank) was 4.45%. ",
                      "High-yield savings: 4.35%, Bankrate\u2019s stated top rate (Openbank). On Bankrate's pages the money market APY "
                      "first in Bankrate's ranked list (Example MM Bank) is 4.05% and the 1-year CD APY first in Bankrate's ranked list (Example Bank) 4.45%. ")
    bk = [r for r in run([Ed("generic", email_html=_email(okb, "DESK READ"), text=_text(okb))], mc, "2026-10-09")
          if r["check"] == "bkr" and r["status"] == "FAIL"]
    if bk:
        ok = False
        print("REGRESSION 22 Oct permitted Bankrate labels FAILED:")
        print(report(bk, [])[0])
    else:
        print("  regression 22 Oct permitted Bankrate labels (stated top rate / first in ranked list): no false positive")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mc"); ap.add_argument("--today", default=dt.date.today().isoformat()); ap.add_argument("--json")
    for e in ("full", "generic"):
        for v in ("file", "email", "text"):
            ap.add_argument(f"--{e}-{v}")
        ap.add_argument(f"--subject-{e}")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    try:
        mc = None
        if a.mc:
            mc = MC(json.load(open(a.mc, encoding="utf-8")))
            if len(mc.curve) < 5:
                print("INPUT ERROR: no Treasury curve (5+ tenors) found in marketclose.json", file=sys.stderr)
                return 2
        eds = []
        for e in ("full", "generic"):
            parts = {}
            for v, key in (("file", "file_html"), ("email", "email_html"), ("text", "text")):
                p = getattr(a, f"{e}_{v}")
                if p:
                    parts[key] = open(p, encoding="utf-8").read()
            if parts:
                eds.append(Ed(e, subject=getattr(a, f"subject_{e}"), **parts))
    except OSError as ex:
        print(f"INPUT ERROR: {ex}", file=sys.stderr)
        return 2
    if not eds:
        ap.print_help()
        return 2
    rows = run(eds, mc, a.today)
    txt, fails = report(rows, eds)
    print(txt)
    if a.json:
        json.dump({"rows": rows, "fails": fails}, open(a.json, "w"), indent=1)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
