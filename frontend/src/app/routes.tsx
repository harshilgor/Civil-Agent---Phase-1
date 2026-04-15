import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { UploadPage } from "@/pages/UploadPage/UploadPage";
import { ProcessingPage } from "@/pages/ProcessingPage/ProcessingPage";
import { ViewerPage } from "@/pages/ViewerPage/ViewerPage";

export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/processing/:jobId" element={<ProcessingPage />} />
        <Route path="/viewer/:jobId" element={<ViewerPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
