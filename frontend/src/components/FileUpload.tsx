import { useCallback, useState, useRef } from "react";

interface FileInfo {
  file: File;
  detectedType: string | null;
  assignedType: string;
  headers: string[];
  previewRows: string[][];
  size: number;
}

type FileType = "ledger" | "settlement" | "bank";

const FILE_TYPES: { value: FileType; label: string; description: string; color: string }[] = [
  { value: "ledger", label: "Internal Ledger", description: "Orders, amounts, customer info", color: "bg-indigo-500/20 text-indigo-400 border-indigo-400/30" },
  { value: "settlement", label: "Gateway Settlement", description: "Settlement IDs, fees, UTRs", color: "bg-emerald-500/20 text-emerald-400 border-emerald-400/30" },
  { value: "bank", label: "Bank Statement", description: "Credits, debits, references", color: "bg-amber-500/20 text-amber-400 border-amber-400/30" },
];

interface FileUploadProps {
  onFilesConfirmed: (files: Record<string, File>) => void;
  onCancel?: () => void;
}

export default function FileUpload({ onFilesConfirmed, onCancel }: FileUploadProps) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const detectType = useCallback((headers: string[]): string | null => {
    const headersLower = headers.map(h => h.toLowerCase().trim());
    if (headersLower.includes("utr") || headersLower.includes("ref")) return "bank";
    if (headersLower.includes("settlement") || headersLower.includes("fee")) return "settlement";
    return "ledger";
  }, []);

  const parseCSV = useCallback((content: string) => {
    const lines = content.trim().split("\n");
    if (lines.length < 2) return { headers: [], previewRows: [] };

    const headers = lines[0].split(",").map(h => h.trim());
    const previewRows = lines.slice(1, 6).map(line => line.split(",").map(c => c.trim()));

    return { headers, previewRows };
  }, []);

  const handleFilesAdded = async (newFiles: File[]) => {
    const processedFiles = await Promise.all(
      newFiles.map(async (file) => {
        const text = await file.text();
        const { headers, previewRows } = parseCSV(text);
        const assignedType = detectType(headers) || "ledger";
        return {
          file,
          detectedType: assignedType,
          assignedType,
          headers,
          previewRows,
          size: file.size,
        };
      })
    );
    setFiles((prev) => [...prev, ...processedFiles]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFilesAdded(Array.from(e.target.files));
    }
  };

  const handleConfirm = () => {
    const filesData: Record<string, File> = {};
    files.forEach(f => {
      filesData[f.assignedType] = f.file;
    });
    onFilesConfirmed(filesData);
  };

  const handleCancel = () => {
    onCancel?.();
  };

  const getTypeInfo = (type: FileType) => FILE_TYPES.find(t => t.value === type)!;

  return (
    <div className="card relative overflow-hidden">
      <div className="p-6">
        <h1 className="text-2xl font-black tracking-tight text-brown mb-4">
          Upload Data Files
        </h1>
        {files.length === 0 && (
          <p className="text-muted mb-4">
            Please select the CSV files you want to reconcile.
          </p>
        )}
        
        {files.map((fileInfo, _index) => (
          <div key={fileInfo.file.name} className="card flex flex-col sm:flex-row sm:items-center gap-4 p-4 mb-3 border border-brown/10">
            <div className="flex-1 min-w-0">
              <p className="font-mono text-sm text-brown truncate">{fileInfo.file.name}</p>
              <p className="text-xs text-muted mt-0.5">
                {(fileInfo.size / 1024).toFixed(1)} KB · {fileInfo.headers.length} columns · {fileInfo.previewRows.length} preview rows
              </p>
            </div>
            <div className="flex flex-col sm:items-end gap-1">
              <select 
                value={fileInfo.assignedType}
                onChange={(e) => {
                  const newType = e.target.value;
                  setFiles(prev => prev.map(f => 
                    f.file.name === fileInfo.file.name 
                      ? { ...f, assignedType: newType } 
                      : f
                  ));
                }}
                className={`text-sm rounded-md border p-1.5 focus:ring-2 focus:outline-none focus:ring-brown/30 font-medium bg-transparent transition-colors ${
                  fileInfo.assignedType === "ledger" ? "text-indigo-700 border-indigo-300" :
                  fileInfo.assignedType === "settlement" ? "text-emerald-700 border-emerald-300" :
                  "text-amber-700 border-amber-300"
                }`}
              >
                {FILE_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              {fileInfo.detectedType === fileInfo.assignedType ? (
                <span className="text-[10px] text-muted opacity-70 px-1">auto-detected</span>
              ) : (
                <span className="text-[10px] text-brown font-medium px-1">manually assigned</span>
              )}
            </div>
          </div>
        ))}
        
        <div className="pt-4 flex flex-col gap-3">
          <input
            type="file"
            multiple
            accept=".csv"
            ref={fileInputRef}
            className="hidden"
            onChange={handleFileSelect}
          />
          <button
            className="btn-ghost w-full border border-brown/20 hover:bg-brown/10 text-brown py-2 rounded-lg"
            onClick={() => fileInputRef.current?.click()}
          >
            {files.length === 0 ? "Browse Files" : "Add More Files"}
          </button>
          
          {files.length > 0 && (
            <div className="mt-4 pt-4 border-t border-brown/10 space-y-3">
              <button onClick={handleConfirm} className="btn-primary w-full py-2 rounded-lg bg-brown text-cream hover:bg-brown/90 transition-colors">
                Confirm & Start Processing
              </button>
              <button onClick={handleCancel} className="btn-ghost w-full text-brown/60 hover:text-brown transition-colors">
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}