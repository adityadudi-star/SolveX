import { Logo } from "@/components/Brand";
import { Card, CardContent } from "@/components/ui/primitives";
import { Callout, PageHeader } from "@/components/audit/Common";

const PRINCIPLES = [
  ["Facts, calculations and AI are kept apart", "Observed facts come from the SEC filing, calculations are deterministic Python, and any AI text is clearly labelled and cannot change a value or a decision."],
  ["Confidence is not approval", "Extraction confidence measures evidence quality. Anomalies and accounting failures can require a human even at 100/100."],
  ["No fabricated data", "If SEC retrieval fails, the audit fails visibly. Missing metrics are recorded as missing — never as zero."],
  ["Human decisions are permanent", "Approve, correct and reject actions are append-only, keep the original extracted value, the reviewer and the timestamp."],
  ["Anomalies are signals", "A large year-over-year move is a reason to investigate, not proof of error or fraud."],
];

export default function About() {
  return (
    <>
      <PageHeader title="About SolveX" />
      <Card><CardContent className="p-8">
        <Logo className="w-72" />
        <p className="mt-5 text-lg font-semibold text-navy-900">Extract the Facts. Investigate the Trust.</p>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">SolveX Financial Auditor is an intelligent human-in-the-loop financial filing auditing platform. It retrieves real SEC EDGAR Form 10-K filings, extracts key financial metrics with evidence, verifies them against SEC XBRL data, runs deterministic accounting validations and anomaly investigations, and pauses for mandatory human approval when the evidence says it should.</p>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">{PRINCIPLES.map(([t, b]) => <div key={t} className="rounded-lg border p-4"><dt className="font-semibold text-navy-800">{t}</dt><dd className="mt-1 text-sm text-muted-foreground">{b}</dd></div>)}</dl>
        <Callout tone="warn" className="mt-6" title="Prototype notice">SolveX is a decision-support prototype, not an audit opinion. Thresholds are configurable demonstration defaults, not accounting standards. Reviewer sign-in uses a shared demo token and is not production-grade authentication.</Callout>
      </CardContent></Card>
    </>
  );
}
