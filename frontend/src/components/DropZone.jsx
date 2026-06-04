import { useState, useRef } from "react";
import { UploadCloud, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export default function DropZone({
  onFiles,
  multiple = true,
  accept,
  label = "Glissez vos fichiers ici",
  hint = "PDF · JPG · PNG · DOCX · XLSX · ZIP",
  busy = false,
  compact = false,
  testId,
}) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const handle = (files) => {
    if (files && files.length) onFiles(Array.from(files));
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        handle(e.dataTransfer.files);
      }}
      onClick={() => !busy && inputRef.current?.click()}
      data-testid={testId}
      role="button"
      aria-label={label}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed text-center transition-colors duration-200",
        compact ? "p-4" : "p-8",
        drag ? "border-slate-900 bg-slate-100" : "border-slate-300 bg-slate-50 hover:border-slate-500 hover:bg-slate-100"
      )}
    >
      <input
        ref={inputRef}
        type="file"
        multiple={multiple}
        accept={accept}
        className="hidden"
        onChange={(e) => {
          handle(e.target.files);
          e.target.value = "";
        }}
      />
      {busy ? (
        <Loader2 className={cn("animate-spin text-slate-400", compact ? "h-5 w-5" : "h-7 w-7")} />
      ) : (
        <UploadCloud className={cn("text-slate-400", compact ? "h-5 w-5" : "h-7 w-7")} />
      )}
      <div>
        <p className={cn("font-medium text-slate-700", compact ? "text-xs" : "text-sm")}>
          {busy ? "Téléversement…" : label}
        </p>
        {!compact && !busy && <p className="text-xs text-slate-400">{hint}</p>}
      </div>
    </div>
  );
}
