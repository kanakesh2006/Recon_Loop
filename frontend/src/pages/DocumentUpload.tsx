import { useCallback, useEffect, useState } from "react";
import FileUpload from "../components/FileUpload";
import { uploadFiles, streamJobProgress, formatMatchRate } from "../api";

interface JobStatus {
  job_id: string;
  status: string;
  progress: number;
  message: string;
  result?: {
    match_rate: number | null;
    auto_matched: number | null;
    needs_review: number | null;
    exceptions: number | null;
  };
  error?: string;
}

interface DocumentUploadProps {
  onNavigateToDashboard?: () => void;
}

export default function DocumentUpload({ onNavigateToDashboard }: DocumentUploadProps) {
  const [step, setStep] = useState<"upload" | "processing" | "results">("upload");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFilesConfirmed = useCallback(async (filesParam: Record<string, File>) => {
    setError(null);
    const result = await uploadFiles(filesParam);
    if (result.job_id) {
      setJobId(result.job_id);
      setStep("processing");
    } else {
      setError("Failed to start processing");
    }
  }, []);

  useEffect(() => {
    if (!jobId || step !== "processing") return;

    let cleanup: (() => void) | undefined;

    const setupStream = async () => {
      try {
        cleanup = await streamJobProgress(
          jobId,
          (data) => {
            setJobStatus((prev) => ({
              ...prev,
              job_id: jobId,
              ...data,
            }) as JobStatus);
          },
          (data) => {
            setJobStatus((prev) => ({
              ...prev,
              job_id: jobId,
              ...data,
            }) as JobStatus);
            setStep("results");
            if (data.status === "failed") {
              // @ts-ignore fallback to message if error is not specifically provided
              setError(data.error || data.message || "Processing failed");
            }
          },
          (err) => {
            console.error("SSE stream error:", err);
            setError(err.message || "Stream connection lost");
          }
        );
      } catch (err) {
        console.error("Failed to start job stream:", err);
      }
    };

    setupStream();

    return () => {
      if (cleanup) cleanup();
    };
  }, [jobId, step]);

  const handleCancel = () => {
    setStep("upload");
    setJobId(null);
    setJobStatus(null);
    setError(null);
  };

  const handleRetry = () => {
    setError(null);
    setStep("upload");
    setJobId(null);
    setJobStatus(null);
  };

  return (
    <div className="min-h-screen bg-cream text-text-dark dark:bg-brown dark:text-cream transition-colors duration-300">
      <main className="mx-auto max-w-4xl px-6 py-8">
        {error && (
          <div className="mb-6 animate-fade-up card border-rose-400/30 bg-rose-50/50 dark:bg-rose-950/20 p-5 text-sm text-rose-700 dark:text-rose-300">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">Error</p>
                <p className="mt-1 text-rose-300/80 dark:text-rose-400">{error}</p>
              </div>
              <button onClick={handleRetry} className="btn-secondary">
                Try Again
              </button>
            </div>
          </div>
        )}

        {step === "upload" && (
          <div className="animate-fade-up">
            <div className="mb-6">
              <h1 className="text-3xl font-black tracking-tight text-brown dark:text-cream mb-2">
                Upload Reconciliation Files
              </h1>
              <p className="text-muted">
                Upload your Ledger, Settlement, and Bank Statement CSV files.
                We'll auto-detect the file types and run the reconciliation pipeline.
              </p>
            </div>

            <FileUpload
              onFilesConfirmed={(files) => handleFilesConfirmed(files)}
              onCancel={() => {}}
            />
          </div>
        )}

        {step === "processing" && (
          <div className="animate-fade-up text-center">
            <div className="card max-w-md mx-auto p-8">
              <div className="mb-6">
                <div className="relative w-20 h-20 mx-auto mb-6">
                  {/* Outer pulsing ring */}
                  <div
                    className="absolute inset-0 rounded-full border-4 border-amber-400/20"
                    style={{ animation: "pulse-ring 2s ease-in-out infinite" }}
                  />
                  {/* Spinning arc */}
                  <svg className="w-full h-full" viewBox="0 0 80 80" style={{ animation: "spin 1.2s linear infinite" }}>
                    <circle
                      cx="40" cy="40" r="34"
                      fill="none"
                      stroke="rgba(212, 165, 67, 0.15)"
                      strokeWidth="6"
                    />
                    <circle
                      cx="40" cy="40" r="34"
                      fill="none"
                      stroke="url(#spinner-gradient)"
                      strokeWidth="6"
                      strokeLinecap="round"
                      strokeDasharray="160"
                      strokeDashoffset="120"
                    />
                    <defs>
                      <linearGradient id="spinner-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#F59E0B" />
                        <stop offset="100%" stopColor="#D4A543" />
                      </linearGradient>
                    </defs>
                  </svg>
                  {/* Center percentage */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-sm font-black text-brown">{jobStatus?.progress ?? 0}%</span>
                  </div>
                </div>
                <h3 className="text-xl font-bold text-brown dark:text-cream mb-2">
                  Processing your files...
                </h3>
                <p className="text-muted mb-6">{jobStatus?.message || "Processing..."}</p>
                <div className="w-full h-2.5 bg-brown/10 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500 ease-out"
                    style={{
                      width: `${jobStatus?.progress || 0}%`,
                      background: "linear-gradient(90deg, #D4A543, #F59E0B)",
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {step === "results" && jobStatus && (
          <div className="animate-fade-up space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-black tracking-tight text-brown dark:text-cream">
                  Reconciliation Complete
                </h1>
                <p className="text-muted mt-1">
                  Processing completed successfully. Here are your results.
                </p>
              </div>
              <button onClick={handleCancel} className="btn-secondary">
                New Upload
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
              <div className="card">
                <p className="text-xs font-semibold tracking-widest text-muted uppercase">Match Rate</p>
                <p className="mt-2 text-4xl font-black tracking-tight stat-value">
                  {formatMatchRate(jobStatus.result?.match_rate as number | null)}
                </p>
              </div>
              <div className="card">
                <p className="text-xs font-semibold tracking-widest text-muted uppercase">Auto Matched</p>
                <p className="mt-2 text-4xl font-black tracking-tight stat-value-emerald">
                  {jobStatus.result?.auto_matched ?? "—"}
                </p>
              </div>
              <div className="card">
                <p className="text-xs font-semibold tracking-widest text-muted uppercase">Needs Review</p>
                <p className="mt-2 text-4xl font-black tracking-tight stat-value-amber">
                  {jobStatus.result?.needs_review ?? "—"}
                </p>
              </div>
              <div className="card">
                <p className="text-xs font-semibold tracking-widest text-muted uppercase">Exceptions</p>
                <p className="mt-2 text-4xl font-black tracking-tight stat-value-rose">
                  {jobStatus.result?.exceptions ?? "—"}
                </p>
              </div>
            </div>

            <div className="card">
              <h3 className="text-lg font-bold text-brown dark:text-cream mb-4">Processing Details</h3>
              <pre className="text-sm text-muted overflow-auto max-h-60">
                {JSON.stringify(jobStatus, null, 2)}
              </pre>
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={handleCancel} className="btn-secondary">
                New Upload
              </button>
              <button
                onClick={() => onNavigateToDashboard?.()}
                className="btn-primary"
              >
                Go to Dashboard →
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Keyframe for pulse-ring animation */}
      <style>{`
        @keyframes pulse-ring {
          0%, 100% { transform: scale(1); opacity: 0.5; }
          50% { transform: scale(1.15); opacity: 0.2; }
        }
      `}</style>
    </div>
  );
}