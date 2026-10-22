import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import EntityDetailPage from "./pages/EntityDetailPage";
import EntityListPage from "./pages/EntityListPage";
import EvidencePage from "./pages/EvidencePage";
import InvestigatePage from "./pages/InvestigatePage";
import ReportPage from "./pages/ReportPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<InvestigatePage />} />
          <Route path="/investigate/:id" element={<InvestigatePage />} />
          <Route path="/investigate/:id/evidence" element={<EvidencePage />} />
          <Route path="/investigate/:id/report" element={<ReportPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/erp/:resource" element={<EntityListPage />} />
          <Route path="/erp/:resource/:id" element={<EntityDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
