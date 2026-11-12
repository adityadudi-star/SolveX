import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { Logo } from "@/components/Brand";
import { Button, Card, CardContent, Input, Label } from "@/components/ui/primitives";
import { Callout } from "@/components/audit/Common";
import { api, errMsg } from "@/services/api";
import { useReviewer } from "@/hooks/useReviewer";

export default function Login() {
  const { login } = useReviewer();
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const m = useMutation({
    mutationFn: () => api.login(name.trim(), token),
    onSuccess: () => login({ name: name.trim(), token }),
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-white to-navy-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="w-64" />
          <p className="mt-4 text-sm font-medium text-navy-800">Extract the Facts. Investigate the Trust.</p>
          <p className="mt-1 text-xs text-muted-foreground">An intelligent human-in-the-loop financial filing auditing platform.</p>
        </div>
        <Card>
          <CardContent className="p-6">
            <h1 className="flex items-center gap-2 text-lg font-semibold text-navy-900"><Lock className="h-4 w-4 text-gold-600" />Reviewer sign-in</h1>
            <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
              <div className="space-y-1.5"><Label htmlFor="n">Your name (recorded in the review history)</Label>
                <Input id="n" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ada Reviewer" autoFocus minLength={2} required /></div>
              <div className="space-y-1.5"><Label htmlFor="t">Demo reviewer token</Label>
                <Input id="t" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="REVIEWER_TOKEN from backend/.env" required /></div>
              {m.isError && <Callout tone="danger">{errMsg(m.error)}</Callout>}
              <Button className="w-full" size="lg" disabled={m.isPending}>{m.isPending ? "Checking…" : "Sign in"}</Button>
            </form>
            <Callout tone="warn" className="mt-5" title="Demo authentication">
              A shared token protects reviewer actions in this prototype. It is not production-grade authentication (no per-user credentials, MFA, or session management).
            </Callout>
          </CardContent>
        </Card>
        <p className="mt-6 text-center text-xs text-muted-foreground">© SolveX · SolveX Financial Auditor</p>
      </div>
    </div>
  );
}
