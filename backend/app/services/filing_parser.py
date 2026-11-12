"""Deterministic parser for original SEC filing HTML (including inline XBRL).

Produces tables (rows, cells, header years, scale) and inline-XBRL contexts/facts. No LLM involved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import lxml.html
from bs4 import BeautifulSoup

YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
NUM_RE = re.compile(r"^\(?\s*\$?\s*\(?\s*([\d]{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*\)?\s*$")
SCALE_RE = re.compile(r"in\s+(thousands|millions|billions)", re.I)
SCALE_EXP = {"thousands": 3, "millions": 6, "billions": 9}
DASHES = {"—", "–", "-", "— ", "$—", "$ —"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", " ")).strip()


def parse_display_number(text: str) -> tuple[float, bool] | None:
    """Parse a displayed number. Parentheses => negative. Returns (value, negative_flag) or None."""
    t = norm(text).replace("$", "").strip()
    if not t or t in DASHES:
        return None
    neg = t.startswith("(") or t.endswith(")")
    m = NUM_RE.match(t if t.startswith("(") or t.endswith(")") else t)
    if not m:
        t2 = t.strip("() ").replace(" ", "")
        m = NUM_RE.match(t2)
        if not m:
            return None
    ip = m.group(1).replace(",", "")
    v = float(ip + (m.group(2) or ""))
    return (-v if neg else v), neg


@dataclass
class IxFact:
    name: str
    context: str
    unit: str | None
    scale: int
    sign: str | None
    raw: str
    value: float            # fully scaled & signed (as tagged)
    decimals: str | None = None


@dataclass
class Context:
    id: str
    start: date | None
    end: date | None        # end for duration, instant date for instant
    instant: bool
    dimensional: bool


@dataclass
class ValueCell:
    col: int
    raw: str
    number: float           # displayed number, parentheses applied
    ix: IxFact | None


@dataclass
class Row:
    index: int
    label: str
    text: str
    values: list[ValueCell] = field(default_factory=list)


@dataclass
class Table:
    index: int
    title: str
    scale: int | None
    scale_text: str | None
    rows: list[Row]
    header_years: list[int]
    kind: str | None = None   # income | balance | cashflow | None
    score: int = 0


@dataclass
class ParsedFiling:
    tables: list[Table]
    contexts: dict[str, Context]
    ix_fact_count: int
    is_inline_xbrl: bool
    bytes_len: int


def _d(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_contexts(root) -> dict[str, Context]:
    ctxs: dict[str, Context] = {}
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if not tag.endswith("context") or ":" not in tag and tag != "context":
            continue
        cid = el.get("id")
        if not cid:
            continue
        start = end = inst = None
        dimensional = False
        for ch in el.iter():
            t = ch.tag if isinstance(ch.tag, str) else ""
            if t.endswith("startdate"):
                start = _d(ch.text)
            elif t.endswith("enddate"):
                end = _d(ch.text)
            elif t.endswith("instant"):
                inst = _d(ch.text)
            elif t.endswith("explicitmember") or t.endswith("typedmember"):
                dimensional = True
        if inst:
            ctxs[cid] = Context(cid, None, inst, True, dimensional)
        elif end:
            ctxs[cid] = Context(cid, start, end, False, dimensional)
    return ctxs


def _ix_from_el(el) -> IxFact | None:
    name = el.get("name")
    if not name:
        return None
    raw = norm(el.text_content())
    scale = int(el.get("scale") or 0)
    parsed = parse_display_number(raw)
    if parsed is None:
        return None
    mag = abs(parsed[0]) * (10 ** scale)
    val = -mag if el.get("sign") == "-" else mag
    return IxFact(name=name, context=el.get("contextref", ""), unit=el.get("unitref"), scale=scale,
                  sign=el.get("sign"), raw=raw, value=val, decimals=el.get("decimals"))


def _preceding_text(table, max_elems: int = 6) -> str:
    """Text immediately before a table (caption / 'In millions' / statement title)."""
    out: list[str] = []
    node = table
    hops = 0
    while node is not None and len(out) < max_elems and hops < 3:
        prev = node.getprevious()
        while prev is not None and len(out) < max_elems:
            if isinstance(prev.tag, str) and prev.tag not in ("table",):
                t = norm(prev.text_content())
                if t:
                    out.append(t[:300])
            elif isinstance(prev.tag, str) and prev.tag == "table":
                break
            prev = prev.getprevious()
        node = node.getparent()
        hops += 1
    return " | ".join(reversed(out))


STATEMENT_HINTS = {
    "income": re.compile(r"statements? of (consolidated )?(operations|income|earnings|comprehensive (income|loss))", re.I),
    "balance": re.compile(r"balance sheets?|statements? of financial (position|condition)", re.I),
    "cashflow": re.compile(r"statements? of (consolidated )?cash flows?|cash flows? statements?", re.I),
}


def _classify(labels: list[str]) -> tuple[str | None, int]:
    blob = "\n".join(labels)
    scores: dict[str, int] = {}
    scores["balance"] = sum(bool(re.search(p, blob)) for p in
                            (r"total assets", r"total liabilities", r"total (share|stock)holders", r"retained earnings|accumulated deficit",
                             r"total current assets", r"total current liabilities"))
    scores["cashflow"] = sum(bool(re.search(p, blob)) for p in
                             (r"operating activities", r"investing activities", r"financing activities",
                              r"depreciation", r"cash.*end of"))
    scores["income"] = sum(bool(re.search(p, blob)) for p in
                           (r"net (sales|revenues?)|^revenues?|total revenues?", r"net (income|loss|earnings)",
                            r"operating (income|expenses)|income from operations", r"per share|earnings per", r"income tax|provision for"))
    kind, best = max(scores.items(), key=lambda kv: kv[1])
    need = {"balance": 3, "cashflow": 3, "income": 3}[kind]
    return (kind, best) if best >= need else (None, best)


def parse_filing(html: bytes | str) -> ParsedFiling:
    raw = html if isinstance(html, bytes) else html.encode("utf-8")
    try:                                   # SEC filings are UTF-8 (or cp1252); never let lxml guess latin-1
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)   # lxml rejects str input carrying an encoding declaration
    root = lxml.html.document_fromstring(text)
    contexts = _parse_contexts(root)
    ix_count = 0
    tables: list[Table] = []
    for t_index, tbl in enumerate(root.iter("table")):
        if tbl.xpath(".//table"):      # layout wrapper table; its inner tables are handled themselves
            continue
        rows: list[Row] = []
        header_years: list[int] = []
        for r_index, tr in enumerate(tbl.iter("tr")):
            cells = tr.xpath("./td|./th")
            texts = [norm(c.text_content()) for c in cells]
            if not any(texts):
                continue
            label = ""
            values: list[ValueCell] = []
            for ci, (c, txt) in enumerate(zip(cells, texts)):
                if not txt or txt in ("$", ")", "%", "(", ")%"):
                    continue
                ix_el = next((e for e in c.iter() if isinstance(e.tag, str) and e.tag.endswith("nonfraction")), None)
                fact = _ix_from_el(ix_el) if ix_el is not None else None
                if fact:
                    ix_count += 1
                num = parse_display_number(txt)
                if num is not None and label:
                    values.append(ValueCell(ci, txt, num[0], fact))
                elif num is not None and not label and not YEAR_RE.fullmatch(txt):
                    values.append(ValueCell(ci, txt, num[0], fact))
                elif not label and num is None:
                    label = txt
                elif label and num is None and not values:
                    label = f"{label} {txt}" if len(label) < 3 else label
            text = " | ".join(t for t in texts if t and t not in ("$", ")", "%"))
            rows.append(Row(r_index, label, text, values))
            if not header_years and r_index < 12:
                ys = [m.group(1) for t in texts for m in YEAR_RE.finditer(t)]
                if len(set(ys)) >= 2 and not values:
                    header_years = [int(y) for y in ys]
            elif not header_years and r_index < 12 and len(rows) <= 12:
                pass
        if not rows:
            continue
        # header years may sit in rows that look numeric (e.g. bare "2025 2024 2023"): detect separately
        if not header_years:
            for row in rows[:10]:
                ys = [int(v.raw) for v in row.values if YEAR_RE.fullmatch(v.raw)]
                if len(set(ys)) >= 2:
                    header_years = ys
                    break
        prev = _preceding_text(tbl)
        head_text = " ".join(r.text for r in rows[:4])
        m = SCALE_RE.search(head_text) or SCALE_RE.search(prev)
        scale = SCALE_EXP[m.group(1).lower()] if m else None
        title = ""
        kind_hint = None
        for k, rx in STATEMENT_HINTS.items():
            mm = rx.search(head_text) or rx.search(prev)
            if mm:
                kind_hint, title = k, mm.group(0)
                break
        labels = [r.label.lower() for r in rows if r.label]
        kind, score = _classify(labels)
        if kind_hint and kind and kind_hint != kind:
            kind_hint = None
        title = re.sub(r"\b(Of|And)\b", lambda m_: m_.group(1).lower(), title.title()) if title else ""
        tables.append(Table(index=t_index, title=title, scale=scale,
                            scale_text=m.group(0).lower() if m else None, rows=rows, header_years=header_years,
                            kind=kind, score=score + (2 if kind_hint and kind_hint == kind else 0) + min(len(rows) // 15, 3)))
    return ParsedFiling(tables=tables, contexts=contexts, ix_fact_count=ix_count,
                        is_inline_xbrl=bool(contexts) and ix_count > 0, bytes_len=len(raw))


def snippet_for_row(table: Table, row: Row, max_len: int = 360) -> str:
    """Targeted evidence snippet: the table title plus the matched row text only."""
    head = f"[{table.title or 'Table ' + str(table.index)}{' — ' + table.scale_text if table.scale_text else ''}] "
    body = BeautifulSoup(row.text, "lxml").get_text(" ", strip=True)
    return (head + body)[:max_len]
