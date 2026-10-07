import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { StoreProvider } from "@/contexts/StoreContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import Transactions from "@/pages/Transactions";
import Payouts from "@/pages/Payouts";
import Report from "@/pages/Report";
import Stores from "@/pages/Stores";
import { CompanyLayout } from "@/components/company/CompanyLayout";
import CompanyOverview from "@/pages/company/Overview";
import Capital from "@/pages/company/Capital";
import Debts from "@/pages/company/CurrentAccounts";
import Closings from "@/pages/company/Closings";
import SectionLedger from "@/pages/SectionLedger";
import CategorySettings from "@/pages/CategorySettings";

function App() {
  return (
    <AuthProvider>
      <StoreProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/fba" element={<SectionLedger section="fba" title="FBA Takibi" subtitle="FBA gelir ve giderleri" />} />
              <Route path="/ppc" element={<SectionLedger section="ppc" title="PPC Reklam Takibi" subtitle="Kampanya başına tıklama / gösterim / sipariş" />} />
              <Route path="/payouts" element={<Payouts />} />
              <Route path="/report" element={<Report />} />
              <Route path="/stores" element={<Stores />} />
              <Route path="/settings/categories" element={<CategorySettings />} />
              <Route path="/company" element={<CompanyLayout />}>
                <Route index element={<CompanyOverview />} />
                <Route path="capital" element={<Capital />} />
                <Route path="debts" element={<Debts />} />
                <Route path="closings" element={<Closings />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <Toaster position="bottom-right" richColors />
        </BrowserRouter>
      </StoreProvider>
    </AuthProvider>
  );
}

export default App;
