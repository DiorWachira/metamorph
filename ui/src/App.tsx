import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/Toast";
import { CasePage } from "./pages/CasePage";
import { Home } from "./pages/Home";
import { Lab } from "./pages/Lab";
import { NotFound } from "./pages/NotFound";
import { Relations } from "./pages/Relations";
import { RunPage } from "./pages/RunPage";
import { Runs } from "./pages/Runs";

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="runs" element={<Runs />} />
            <Route path="runs/:runId" element={<RunPage />} />
            <Route path="cases/:caseId" element={<CasePage />} />
            <Route path="relations" element={<Relations />} />
            <Route path="lab" element={<Lab />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
