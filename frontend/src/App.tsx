import { HashRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Agents from "./pages/Agents";
import Vendors from "./pages/Vendors";
import VendorDetail from "./pages/VendorDetail";
import Findings from "./pages/Findings";
import Questionnaires from "./pages/Questionnaires";
import QuestionnaireDetail from "./pages/QuestionnaireDetail";
import Concentration from "./pages/Concentration";
import Digest from "./pages/Digest";
import Traces from "./pages/Traces";
import Dlq from "./pages/Dlq";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="login" element={<Login />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="agents" element={<Agents />} />
          <Route path="vendors" element={<Vendors />} />
          <Route path="vendors/:vendorId" element={<VendorDetail />} />
          <Route path="findings" element={<Findings />} />
          <Route path="questionnaires" element={<Questionnaires />} />
          <Route path="questionnaires/:questionnaireId" element={<QuestionnaireDetail />} />
          <Route path="concentration" element={<Concentration />} />
          <Route path="digest" element={<Digest />} />
          <Route path="traces" element={<Traces />} />
          <Route path="dlq" element={<Dlq />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
