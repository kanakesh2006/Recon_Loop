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

export default function DocumentUpload() {
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
                <div className="relative w-16 h-16 mx-auto mb-4">
                  <svg className="w-full h-16 animate-spin text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="animate-spin" stroke="currentColor" strokeLinecap="round" strokeWidth={4} d="M12 2v4m0 12v4M12 2a10 10 0 010 20M12 2a10 10 0 000 20" />
                  </svg>
                </div>
                <h3 className="text-xl font-bold text-brown dark:text-cream mb-2">
                  Processing your files...
                </h3>
                <p className="text-muted mb-6">{jobStatus?.message || "Processing..."}</p>
                <div className="w-full h-2 bg-white/10 dark:bg-brown-lighter/20 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-400 to-amber-500 transition-all duration-300 ease-out"
                    style={{ width: `${jobStatus?.progress || 0}%` }}
                  />
                </div>
                <p className="mt-3 text-sm text-muted">
                  {jobStatus?.progress ?? 0}% complete
                </p>
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
            </div>
          </div>
        )}
      </main>
    </div>
  );
}