import CopilotChat from "./components/CopilotChat";
import Dashboard from "./components/Dashboard";

export default function App() {
  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,#131c33_0%,#070b14_55%)]">
      <header className="border-b border-white/5 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-5">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-400 via-fuchsia-500 to-rose-500 text-lg font-black text-white shadow-lg shadow-fuchsia-500/25">
            ⟳
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-slate-50">
              Recon
              <span className="bg-gradient-to-r from-indigo-300 to-fuchsia-300 bg-clip-text text-transparent">
                Loop
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              Multi-source reconciliation · explainable exceptions · audited
              decisions
            </p>
          </div>
          <span className="ml-auto hidden rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-bold tracking-wider text-emerald-300 uppercase sm:block">
            Razorpay AI Buildathon · Track 04
          </span>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-6 lg:grid-cols-[1fr_380px]">
        <div className="min-w-0">
          <Dashboard />
        </div>
        <aside className="lg:sticky lg:top-6 lg:h-[calc(100vh-7rem)]">
          <CopilotChat />
        </aside>
      </main>

      <footer className="border-t border-white/5 py-4 text-center text-[11px] text-slate-600">
        Every match and exception on this page is written to an immutable audit
        trail.
      </footer>
    </div>
  );
}
