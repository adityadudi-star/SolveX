import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { getSession, setSession, type ReviewerSession } from "@/services/api";

interface Ctx { session: ReviewerSession | null; login: (s: ReviewerSession) => void; logout: () => void }
const ReviewerContext = createContext<Ctx>({ session: null, login: () => {}, logout: () => {} });

/** DEMO authentication only: a shared token held in sessionStorage. Not production-grade. */
export function ReviewerProvider({ children }: { children: ReactNode }) {
  const [session, setS] = useState<ReviewerSession | null>(() => getSession());
  const login = useCallback((s: ReviewerSession) => { setSession(s); setS(s); }, []);
  const logout = useCallback(() => { setSession(null); setS(null); }, []);
  const value = useMemo(() => ({ session, login, logout }), [session, login, logout]);
  return <ReviewerContext.Provider value={value}>{children}</ReviewerContext.Provider>;
}
export const useReviewer = () => useContext(ReviewerContext);
