import { useState } from "react";
import Dashboard from "./components/Dashboard";
import DocumentUpload from "./pages/DocumentUpload";
import Hero from "./pages/Hero";
import { ThemeProvider } from "./context/ThemeContext";
import "./index.css";

type Page = "hero" | "dashboard" | "upload";

export default function App() {
  const [page, setPage] = useState<Page>("hero");

  return (
    <ThemeProvider>
      <div className="min-h-screen bg-cream text-text-dark transition-colors duration-300">
        <header className="border-b border-white/20 backdrop-blur-md bg-white/40 sticky top-0 z-50">
          <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-brown via-brown-light to-brown-lighter shadow-lg shadow-brown/25 p-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full text-cream">
                <path d="M8 8a4 4 0 1 0 0 8 4 4 0 0 0 4-4 4 4 0 1 1 0-8 4 4 0 0 1 4 4 4 4 0 1 0 0 8 4 4 0 0 0 4-4" />
              </svg>
            </div>
            <div className="flex-1 cursor-pointer" onClick={() => setPage("hero")}>
              <h1 className="text-xl font-black tracking-tight text-brown">
                Recon<span className="bg-gradient-to-r from-brown-light to-brown-lighter bg-clip-text text-transparent">Loop</span>
              </h1>
              <p className="text-xs text-slate-600 font-medium">
                Multi-source reconciliation · explainable exceptions · audited decisions
              </p>
            </div>
            <nav className="ml-auto flex items-center gap-3">
              <button
                onClick={() => setPage("dashboard")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  page === "dashboard"
                    ? "bg-brown text-cream"
                    : "text-slate-600 hover:text-brown"
                }`}
              >
                Dashboard
              </button>
              <button
                onClick={() => setPage("upload")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  page === "upload"
                    ? "bg-brown text-cream"
                    : "text-slate-600 hover:text-brown"
                }`}
              >
                Upload
              </button>
              <span className="hidden rounded-full border border-brown/30 bg-brown/10 px-3 py-1 text-[11px] font-bold tracking-wider text-brown uppercase sm:block">
                Razorpay AI Buildathon · Track 04
              </span>
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-6 py-6">
          {page === "hero" && <Hero onGetStarted={() => setPage("dashboard")} />}
          {page === "dashboard" && <Dashboard />}
          {page === "upload" && <DocumentUpload />}
        </main>

        <footer className="border-t border-brown/10 py-4 text-center text-[11px] text-slate-500 font-medium">
          Every match and exception on this page is written to an immutable audit trail.
        </footer>
      </div>
    </ThemeProvider>
  );
}