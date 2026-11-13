import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ExternalLink, Loader2, Search } from "lucide-react";
import { api, errMsg } from "@/services/api";
import { useAuditProgress } from "@/hooks/useAuditProgress";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@/components/ui/primitives";
import { ProgressTimeline } from "@/components/audit/ProgressTimeline";
import { Callout, ErrorBox, PageHeader } from "@/components/audit/Common";
import type { Company, FilingRefDto } from "@/types";
import { cn } from "@/utils/cn";

const QUICK = [
  { label: "Apple", q: "AAPL" }, { label: "Microsoft", q: "MSFT" }, { label: "NVIDIA", q: "NVDA" },
  { label: "Amazon", q: "AMZN" }, { label: "Alphabet", q: "GOOGL" },
];

export default function NewAudit() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [company, setCompany] = useState<Company | null>(null);
  const [filing, setFiling] = useState<FilingRefDto | null>(null);
  const [wid, setWid] = useState<string | null>(null);

  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 350); return () => clearTimeout(t); }, [q]);

  const search = useQuery({ queryKey: ["search", dq], queryFn: () => api.searchCompanies(dq), enabled: dq.length >= 1 && !company });
  const filings = useQuery({ queryKey: ["filings", company?.cik], queryFn: () => api.filings(company!.cik), enabled: !!company });
  const start = useMutation({
    mutationFn: () => api.startAudit(company!.cik, filing!.accession),
    onSuccess: (r) => setWid(r.workflow_id),
  });
  const { snap, transport } = useAuditProgress(wid);

  const filingList = useMemo(() => filings.data?.filings ?? [], [filings.data]);
  useEffect(() => { if (filingList.length && !filing) setFiling(filingList[0]); }, [filingList, filing]);

  const running = !!wid;
  const reset = () => { setCompany(null); setFiling(null); setWid(null); setQ(""); start.reset(); };

  return (
    <>
      <PageHeader title="New audit" subtitle="Search a company, select a Form 10-K, and SolveX will retrieve the original filing from SEC EDGAR." />
      <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>1 · Company</CardTitle><CardDescription>Search by name or ticker. The SEC CIK is resolved from EDGAR.</CardDescription></CardHeader>
            <CardContent>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input className="pl-9" placeholder="e.g. Apple, MSFT, NVIDIA…" value={company ? `${company.name} (${company.ticker ?? "—"}) · CIK ${company.cik}` : q}
                  onChange={(e) => { setQ(e.target.value); setCompany(null); setFiling(null); }} disabled={running} aria-label="Search company" />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {QUICK.map((c) => (
                  <button key={c.q} disabled={running} onClick={() => { setCompany(null); setFiling(null); setQ(c.q); }}
                    className="rounded-full border bg-surface px-3 py-1 text-xs font-semibold text-navy-800 hover:bg-navy-50 disabled:opacity-50">{c.label}</button>
                ))}
              </div>
              {search.isError && <div className="mt-3"><ErrorBox message={errMsg(search.error)} /></div>}
              {!company && dq && search.data && (
                <ul className="mt-3 divide-y rounded-md border">
                  {search.data.length === 0 && <li className="p-3 text-sm text-muted-foreground">No SEC registrants matched “{dq}”.</li>}
                  {search.data.map((c) => (
                    <li key={c.cik}><button className="flex w-full items-center justify-between gap-2 p-3 text-left hover:bg-secondary/50" onClick={() => setCompany(c)}>
                      <span className="text-sm font-medium">{c.name}</span><span className="text-xs text-muted-foreground">{c.ticker} · CIK {c.cik}</span></button></li>
                  ))}
                </ul>
              )}
              {search.isFetching && <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />Searching SEC registrants…</div>}
            </CardContent>
          </Card>

          <Card className={cn(!company && "opacity-60")}>
            <CardHeader><CardTitle>2 · Form 10-K & financial year</CardTitle><CardDescription>Only annual reports (Form 10-K) are offered.</CardDescription></CardHeader>
            <CardContent>
              {!company && <div className="text-sm text-muted-foreground">Select a company first.</div>}
              {filings.isFetching && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Retrieving filings from SEC EDGAR…</div>}
              {filings.isError && <ErrorBox message={errMsg(filings.error)} />}
              {filingList.length > 0 && (
                <div className="grid gap-2 sm:grid-cols-2">
                  {filingList.slice(0, 12).map((f) => (
                    <button key={f.accession} disabled={running} onClick={() => setFiling(f)}
                      className={cn("rounded-md border p-3 text-left text-sm transition-colors hover:bg-secondary/50 disabled:opacity-60", filing?.accession === f.accession && "border-navy-600 bg-navy-50 ring-1 ring-navy-600")}>
                      <div className="flex items-center justify-between"><span className="font-semibold text-navy-900">FY {f.fiscal_year}</span><Badge tone="navy">{f.form}</Badge></div>
                      <div className="mt-1 text-xs text-muted-foreground">Period end {f.period_end} · filed {f.filing_date}</div>
                      <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{f.accession}</div>
                    </button>
                  ))}
                </div>
              )}
              {filing && <a href={filing.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-navy-600 hover:underline">View original filing on SEC.gov <ExternalLink className="h-3 w-3" /></a>}
            </CardContent>
          </Card>

          {start.isError && <ErrorBox message={errMsg(start.error)} />}
          <div className="flex items-center gap-3">
            <Button size="lg" variant="gold" disabled={!filing || start.isPending || running} onClick={() => start.mutate()}>
              {start.isPending ? <><Loader2 className="h-4 w-4 animate-spin" />Starting…</> : "Start audit"}
            </Button>
            {running && <Button variant="ghost" onClick={reset}>New search</Button>}
          </div>
        </div>

        <Card className="h-fit lg:sticky lg:top-6">
          <CardHeader>
            <CardTitle>Live audit progress</CardTitle>
            <CardDescription>{wid ? "Real events streamed from the backend workflow." : "Progress appears here once the audit starts."}</CardDescription>
          </CardHeader>
          <CardContent>
            {!wid ? (
              <ol className="space-y-2 text-sm text-muted-foreground">
                {["SEC filing retrieval", "Document parsing", "Financial extraction", "Confidence calculation", "Accounting validation", "Anomaly investigation", "XBRL verification", "Audit decision", "Human review preparation"].map((s, i) => (
                  <li key={s} className="flex items-center gap-2"><span className="flex h-5 w-5 items-center justify-center rounded-full border text-[10px]">{i + 1}</span>{s}</li>
                ))}
              </ol>
            ) : snap ? (
              <>
                <ProgressTimeline stages={snap.stages} transport={transport} />
                {snap.status === "failed" && <div className="mt-4"><ErrorBox message={snap.error ?? "The audit failed."} /><p className="mt-2 text-xs text-muted-foreground">No results were fabricated. <Link className="underline" to={`/audits/${wid}`}>View failed run</Link></p></div>}
                {snap.status === "awaiting_review" && (
                  <Callout tone="danger" className="mt-4" title="Paused for human review">
                    All 9 stages are done and the workflow is checkpointed. Read the stage details above, then continue when you are ready.
                    <Button className="mt-3 w-full" variant="gold" onClick={() => nav(`/audits/${wid}`)}>Continue to human review</Button>
                  </Callout>
                )}
                {snap.status === "completed" && (
                  <Callout tone="pass" className="mt-4" title="Audit complete">
                    All 9 stages are done. Read the stage details above, then open the results.
                    <Button className="mt-3 w-full" variant="gold" onClick={() => nav(`/audits/${wid}`)}>View results</Button>
                  </Callout>
                )}
              </>
            ) : <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Connecting…</div>}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
