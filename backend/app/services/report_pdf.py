"""SolveX audit report PDF export (reportlab)."""
from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#0B1F4B")
GOLD = colors.HexColor("#C9971C")
LOGO = Path(__file__).resolve().parent.parent / "assets" / "solvex-logo.png"
STATUS_COLORS = {"FULLY_PASSED": colors.HexColor("#15803D"), "PASSED_HUMAN_CONSIDERATION_RECOMMENDED": colors.HexColor("#B45309"),
                 "HUMAN_APPROVAL_REQUIRED": colors.HexColor("#B91C1C")}


def _money(v, cur="USD"):
    if v is None:
        return "—"
    a = abs(v)
    s = f"{a / 1e9:,.2f}B" if a >= 1e9 else f"{a / 1e6:,.1f}M" if a >= 1e6 else f"{a:,.0f}"
    return ("-" if v < 0 else "") + ("$" if cur in (None, "USD") else f"{cur} ") + s


def render_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"SolveX Audit Report — {report['company']['name']}", author="SolveX Financial Auditor")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=NAVY, fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=NAVY, fontSize=12, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#475569"))
    el = []
    if LOGO.exists():
        el.append(Image(str(LOGO), width=52 * mm, height=52 * mm * 0.348))
    el.append(Paragraph("SolveX Financial Auditor — Audit Report", h1))
    el.append(Paragraph(f"<i>{escape(report.get('tagline', ''))}</i>", small))
    el.append(Spacer(1, 4))
    c, f = report["company"], report["filing"]
    info = [["Company", f"{c['name']} ({c.get('ticker') or '—'})", "CIK", c["cik"]],
            ["Form", f["form"], "Period end", f["period_end"]],
            ["Accession", f["accession"], "Filed", f["filing_date"]],
            ["Workflow", report["workflow_id"], "Generated", report["generated_at"][:19]]]
    t = Table(info, colWidths=[24 * mm, 66 * mm, 24 * mm, 60 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (0, -1), NAVY), ("TEXTCOLOR", (2, 0), (2, -1), NAVY),
                           ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]))
    el += [t, Spacer(1, 6)]
    col = STATUS_COLORS.get(report.get("decision") or "", NAVY)
    dec = Table([[Paragraph(f"<b>Overall decision: {escape(str(report.get('decision_label')))}</b>", ParagraphStyle("d", parent=body, textColor=colors.white, fontSize=10))]],
                colWidths=[174 * mm])
    dec.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), col), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el += [dec, Spacer(1, 4)]
    el.append(Paragraph("A financial value can be extracted correctly and still be unsafe to approve. "
                        "Confidence measures extraction evidence quality; it is not audit approval.", small))
    el.append(Paragraph("Metrics", h2))
    rows = [["Metric", "Extracted", "Final (reviewed)", "Conf.", "XBRL", "Anomaly", "Decision"]]
    for m in report["metrics"]:
        rows.append([m["label"], _money(m["value"], m["currency"]) if m["found"] else "MISSING", _money(m["final_value"], m["currency"]) if m["final_value"] is not None else "—",
                     f"{m['confidence']:.1f}" if m["confidence"] is not None else "—", m["xbrl_status"], m["anomaly_status"],
                     (m["decision"] or "").replace("_", " ").title()[:30] + (f" [{m['review_status']}]" if m["review_status"] not in ("not_required",) else "")])
    mt = Table(rows, repeatRows=1, colWidths=[30 * mm, 24 * mm, 24 * mm, 12 * mm, 18 * mm, 22 * mm, 44 * mm])
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el.append(mt)
    el.append(Paragraph("Explanations", h2))
    for m in report["metrics"]:
        if m.get("narrative"):
            el.append(Paragraph(f"<b>{escape(m['label'])}</b>: {escape(m['narrative'])}", body))
            if m.get("evidence"):
                el.append(Paragraph(f"Evidence: {escape(m['evidence'][:300])}", small))
            el.append(Spacer(1, 3))
    el.append(Paragraph("Validation checks", h2))
    for k in report["validation_checks"]:
        if k["status"] != "passed":
            el.append(Paragraph(f"[{k['status'].upper()}] {escape(k['name'])} — {escape(k['explanation'])}", body))
    el.append(Paragraph("Anomalies (investigation signals)", h2))
    if not report["anomalies"]:
        el.append(Paragraph("None above the warning level.", body))
    for a in report["anomalies"]:
        el.append(Paragraph(f"[{a['status'].upper()}] {escape(a['explanation'])}", body))
    el.append(Paragraph("Human review history", h2))
    if not report["review_history"]:
        el.append(Paragraph("No reviewer actions recorded.", body))
    for r in report["review_history"]:
        el.append(Paragraph(f"{r['ts'][:19]} — {escape(r['reviewer'])}: {r['action'].upper()} (original {r['original_value']}, corrected {r['corrected_value']}) — {escape(r['notes'] or '')}", body))
    el.append(Paragraph("XBRL verification methodology", h2))
    el.append(Paragraph(escape((report.get("summary", {}).get("xbrl") or {}).get("methodology", "")), body))
    el.append(Spacer(1, 6))
    for d in report.get("disclaimers", []):
        el.append(Paragraph("• " + escape(d), small))
    doc.build(el)
    return buf.getvalue()
