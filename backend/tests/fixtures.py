"""Synthetic SEC fixtures (clearly fake company 'Testco Inc'). Served through an httpx MockTransport — no network access."""
from __future__ import annotations

import json
from copy import deepcopy

import httpx

CIK = "0001234567"
ACC = "0001234567-25-000010"
ACC_PREV = "0001234567-24-000008"
ACC_PREV2 = "0001234567-23-000006"
DOC = "testco-20241231.htm"
FY_END = "2024-12-31"

# metric -> (concept, statement, period_type)
CONCEPTS = {
    "revenue": ("Revenues", "income", "duration"),
    "net_income": ("NetIncomeLoss", "income", "duration"),
    "operating_expenses": ("OperatingExpenses", "income", "duration"),
    "total_assets": ("Assets", "balance", "instant"),
    "total_liabilities": ("Liabilities", "balance", "instant"),
    "shareholders_equity": ("StockholdersEquity", "balance", "instant"),
    "cash_and_equivalents": ("CashAndCashEquivalentsAtCarryingValue", "balance", "instant"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities", "cashflow", "duration"),
    "capital_expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment", "cashflow", "duration"),
}

# values in USD millions: (FY2024, FY2023, FY2022)
BASE = {
    "revenue": (1050, 1000, 950), "net_income": (105, 100, 95), "operating_expenses": (800, 780, 760),
    "total_assets": (5000, 4800, 4600), "total_liabilities": (3000, 2900, 2800), "shareholders_equity": (2000, 1900, 1800),
    "cash_and_equivalents": (400, 380, 360), "operating_cash_flow": (220, 210, 200), "capital_expenditure": (60, 55, 50),
}

LABELS = {
    "revenue": "Total net sales", "net_income": "Net income", "operating_expenses": "Total operating expenses",
    "total_assets": "Total assets", "total_liabilities": "Total liabilities", "shareholders_equity": "Total shareholders’ equity",
    "cash_and_equivalents": "Cash and cash equivalents", "operating_cash_flow": "Net cash provided by operating activities",
    "capital_expenditure": "Payments for acquisition of property, plant and equipment",
}


def fmt(v: float, neg: bool = False) -> str:
    s = f"{abs(v):,.0f}"
    return f"({s})" if neg else s


def build_html(values: dict, inline: bool = True, scale_text: str | None = "(In millions, except per-share amounts)",
               omit: set[str] | None = None) -> bytes:
    omit = omit or set()
    ctx = """<ix:header><ix:resources>
    <xbrli:context id="D24"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1234567</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="D23"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1234567</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="I24"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1234567</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period></xbrli:context>
    <xbrli:context id="I23"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1234567</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
    <xbrli:context id="DIM24"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1234567</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">tc:ProductsMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
    </ix:resources></ix:header>""" if inline else ""

    def cell(key: str, col: int) -> str:
        v = values[key][col]
        concept = CONCEPTS[key][0]
        ptype = CONCEPTS[key][2]
        c = ("D" if ptype == "duration" else "I") + ("24" if col == 0 else "23")
        txt = fmt(v, neg=key == "capital_expenditure")
        inner = fmt(v)
        if inline:
            tag = f'<ix:nonFraction name="us-gaap:{concept}" contextRef="{c}" unitRef="usd" scale="6" decimals="-6" format="ixt:num-dot-decimal">{inner}</ix:nonFraction>'
            return f"<td>$</td><td>{('(' if key == 'capital_expenditure' else '') + tag + (')' if key == 'capital_expenditure' else '')}</td>"
        return f"<td>$</td><td>{txt}</td>"

    def row(key: str, order_2023_first: bool = False) -> str:
        if key in omit:
            return ""
        cols = (1, 0) if order_2023_first else (0, 1)
        return f"<tr><td>{LABELS[key]}</td>{''.join(cell(key, c) for c in cols)}</tr>"

    hdr = "<tr><td></td><td>2024</td><td>2023</td></tr>"
    sc = f"<p>{scale_text}</p>" if scale_text else ""
    html = f"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>{ctx}
    <p>Item 7. Management's Discussion</p>
    <table><tr><td>Total net sales</td><td>$</td><td>999,999</td></tr></table>
    <p>Item 8. Financial Statements</p>
    <p>TESTCO INC. CONSOLIDATED STATEMENTS OF OPERATIONS</p>{sc}
    <table>{hdr}
      {row('revenue')}
      <tr><td>Cost of sales</td><td>$</td><td>200</td><td>$</td><td>190</td></tr>
      {row('operating_expenses')}
      <tr><td>Operating income</td><td>$</td><td>250</td><td>$</td><td>230</td></tr>
      <tr><td>Provision for income taxes</td><td>$</td><td>30</td><td>$</td><td>28</td></tr>
      {row('net_income')}
      <tr><td>Earnings per share — basic</td><td>$</td><td>1.05</td><td>$</td><td>1.00</td></tr>
    </table>
    <p>TESTCO INC. CONSOLIDATED BALANCE SHEETS</p>{sc}
    <table><tr><td></td><td>December 31, 2024</td><td>December 31, 2023</td></tr>
      {row('cash_and_equivalents')}
      <tr><td>Total current assets</td><td>$</td><td>1,500</td><td>$</td><td>1,400</td></tr>
      {row('total_assets')}
      <tr><td>Total current liabilities</td><td>$</td><td>900</td><td>$</td><td>850</td></tr>
      {row('total_liabilities')}
      <tr><td>Retained earnings</td><td>$</td><td>700</td><td>$</td><td>650</td></tr>
      {row('shareholders_equity')}
      <tr><td>Total liabilities and shareholders’ equity</td><td>$</td><td>5,000</td><td>$</td><td>4,800</td></tr>
    </table>
    <p>TESTCO INC. CONSOLIDATED STATEMENTS OF CASH FLOWS</p>{sc}
    <table>{hdr}
      <tr><td>Depreciation and amortization</td><td>$</td><td>40</td><td>$</td><td>38</td></tr>
      {row('operating_cash_flow')}
      <tr><td>Net cash used in investing activities</td><td>$</td><td>(120)</td><td>$</td><td>(110)</td></tr>
      {row('capital_expenditure')}
      <tr><td>Net cash used in financing activities</td><td>$</td><td>(60)</td><td>$</td><td>(55)</td></tr>
    </table></body></html>"""
    return html.encode("utf-8")


def build_companyfacts(values: dict, drop: set[str] | None = None, history: bool = True, restate_prior: dict | None = None,
                       wrong: dict | None = None) -> dict:
    drop, wrong, restate_prior = drop or set(), wrong or {}, restate_prior or {}
    facts: dict = {}
    for key, (concept, _, ptype) in CONCEPTS.items():
        if key in drop:
            continue
        entries = []
        yrs = [(2024, 0, ACC, "2025-02-20")]
        if history:
            yrs += [(2023, 1, ACC, "2025-02-20"), (2023, 1, ACC_PREV, "2024-02-20"), (2022, 2, ACC_PREV, "2024-02-20"),
                    (2022, 2, ACC_PREV2, "2023-02-20")]
        for year, col, accn, filed in yrs:
            v = values[key][col]
            if key in wrong and year == 2024 and accn == ACC:
                v = wrong[key]
            if accn == ACC_PREV and year == 2023 and key in restate_prior:
                v = restate_prior[key]          # originally reported value (differs from restated comparative)
            e = {"end": f"{year}-12-31", "val": v * 1_000_000, "accn": accn, "fy": 2024 if accn == ACC else 2023, "fp": "FY", "form": "10-K", "filed": filed}
            if ptype == "duration":
                e["start"] = f"{year}-01-01"
            entries.append(e)
        facts[concept] = {"label": concept, "units": {"USD": entries}}
    return {"cik": 1234567, "entityName": "Testco Inc", "facts": {"us-gaap": facts}}


def submissions() -> dict:
    return {"cik": "1234567", "name": "Testco Inc", "tickers": ["TSTC"], "filings": {"recent": {
        "accessionNumber": [ACC, ACC_PREV, "0001234567-25-000002"], "filingDate": ["2025-02-20", "2024-02-20", "2025-04-01"],
        "reportDate": ["2024-12-31", "2023-12-31", "2025-03-31"], "form": ["10-K", "10-K", "10-Q"],
        "primaryDocument": [DOC, "testco-20231231.htm", "q.htm"]}, "files": []}}


class FakeSec:
    """Builds an httpx MockTransport that serves fixtures and records every request."""

    def __init__(self, values=None, inline=True, scale_text="(In millions, except per-share amounts)", omit=None, drop=None, history=True,
                 restate_prior=None, wrong=None, facts_status=200, fail_html=None):
        self.values = deepcopy(values or BASE)
        self.requests: list[str] = []
        self.html = build_html(self.values, inline=inline, scale_text=scale_text, omit=omit)
        self.facts = build_companyfacts(self.values, drop=drop, history=history, restate_prior=restate_prior, wrong=wrong)
        self.facts_status = facts_status
        self.fail_html = fail_html   # status code to return for the filing document
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        self.requests.append(url)
        assert "SolveX" in req.headers["user-agent"] and "@" in req.headers["user-agent"]   # truthful UA with contact
        if "company_tickers" in url:
            return httpx.Response(200, json={"0": {"cik_str": 1234567, "ticker": "TSTC", "title": "Testco Inc"},
                                             "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}})
        if "/submissions/" in url:
            return httpx.Response(200, json=submissions())
        if "companyfacts" in url:
            return httpx.Response(self.facts_status, json=self.facts if self.facts_status == 200 else {})
        if url.endswith(DOC):
            if self.fail_html:
                return httpx.Response(self.fail_html, text="error")
            return httpx.Response(200, content=self.html)
        return httpx.Response(404)

    def count(self, needle: str) -> int:
        return sum(needle in u for u in self.requests)
