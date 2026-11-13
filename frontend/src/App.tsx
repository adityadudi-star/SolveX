import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import { SplashScreen } from "@/components/Brand";
import { useReviewer } from "@/hooks/useReviewer";
import Login from "@/pages/Login";

const Overview = lazy(() => import("@/pages/Overview"));
const NewAudit = lazy(() => import("@/pages/NewAudit"));
const AuditResults = lazy(() => import("@/pages/AuditResults"));
const EvidencePage = lazy(() => import("@/pages/EvidencePage"));
const ReviewCenter = lazy(() => import("@/pages/ReviewCenter"));
const Trends = lazy(() => import("@/pages/Trends"));
const AuditHistory = lazy(() => import("@/pages/AuditHistory"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const AdaptiveThresholds = lazy(() => import("@/pages/AdaptiveThresholds"));
const About = lazy(() => import("@/pages/About"));

export default function App() {
  const { session } = useReviewer();
  if (!session) return <Login />;
  return (
    <Suspense fallback={<SplashScreen />}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Overview />} />
          <Route path="audits/new" element={<NewAudit />} />
          <Route path="audits" element={<AuditHistory />} />
          <Route path="audits/:id" element={<AuditResults />} />
          <Route path="audits/:id/metrics/:metricId" element={<EvidencePage />} />
          <Route path="reviews" element={<ReviewCenter />} />
          <Route path="trends" element={<Trends />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="adaptive" element={<AdaptiveThresholds />} />
          <Route path="about" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
