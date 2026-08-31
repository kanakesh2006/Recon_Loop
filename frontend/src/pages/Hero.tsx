export default function Hero({ onGetStarted }: { onGetStarted: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-center px-4 animate-fade-up">
      <div className="max-w-3xl space-y-8">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brown/5 border border-brown/10 text-brown font-semibold text-xs tracking-wider uppercase mb-4">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          The future of reconciliation
        </div>
        
        <h1 className="text-5xl md:text-6xl font-black text-brown tracking-tight leading-tight">
          Untangle messy data with{" "}
          <span className="bg-gradient-to-r from-brown-light to-accent bg-clip-text text-transparent">
            ReconLoop
          </span>
        </h1>
        
        <p className="text-lg md:text-xl text-slate-600 font-medium leading-relaxed max-w-2xl mx-auto">
          Automatically reconcile transactions across internal databases, payment gateways, and bank settlements. 
          Powered by a tiered deterministic and AI matching engine that achieves 94.2% accuracy.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-8">
          <button
            onClick={onGetStarted}
            className="btn-primary text-base px-8 py-3 w-full sm:w-auto shadow-xl shadow-brown/20"
          >
            Launch Dashboard
          </button>
          <a
            href="https://github.com/kanakesh2006/Recon_Loop"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary text-base px-8 py-3 w-full sm:w-auto bg-transparent border-brown/20"
          >
            View on GitHub
          </a>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 pt-16 text-left">
          <div className="card bg-white/60 border-white/40 shadow-sm">
            <div className="h-10 w-10 rounded-lg bg-brown/10 text-brown flex items-center justify-center text-xl font-bold mb-4">1</div>
            <h3 className="font-bold text-brown text-lg mb-2">Ingest & Standardize</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Upload multi-format settlement files. ReconLoop auto-maps messy schema variants into a unified timeline.
            </p>
          </div>
          <div className="card bg-white/60 border-white/40 shadow-sm">
            <div className="h-10 w-10 rounded-lg bg-accent/20 text-accent flex items-center justify-center text-xl font-bold mb-4">2</div>
            <h3 className="font-bold text-brown text-lg mb-2">Tiered Matching</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Rules catch 80% instantly. Vector embeddings (Pinecone) handle fuzzy logic for the rest.
            </p>
          </div>
          <div className="card bg-white/60 border-white/40 shadow-sm">
            <div className="h-10 w-10 rounded-lg bg-brown/10 text-brown flex items-center justify-center text-xl font-bold mb-4">3</div>
            <h3 className="font-bold text-brown text-lg mb-2">AI Copilot</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Ask questions directly via Voice or Text to understand why a specific transaction failed reconciliation.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
