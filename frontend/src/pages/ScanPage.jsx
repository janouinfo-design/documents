import { useState } from "react";
import { useParams, useSearchParams, useNavigate, Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2 } from "lucide-react";
import { getVehicle } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import ScanDocumentDialog, { DOC_TYPE_OPTIONS } from "@/components/ScanDocumentDialog";

export default function ScanPage() {
  const { vehicleId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [open, setOpen] = useState(true);
  const type = DOC_TYPE_OPTIONS.some((t) => t.key === params.get("type")) ? params.get("type") : null;
  const { data: vehicle, isLoading, isError } = useQuery({
    queryKey: ["vehicle", vehicleId],
    queryFn: () => getVehicle(vehicleId),
  });

  const done = () => navigate("/vehicules", { replace: true });

  if (user?.role === "read_only") return <Navigate to="/vehicules" replace />;

  return (
    <div className="mx-auto max-w-2xl space-y-4" data-testid="scan-page">
      <button onClick={done} data-testid="scan-page-back"
              className="flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" /> Scanner{vehicle ? ` · ${vehicle.plaque}` : ""}
      </button>
      {isLoading && (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
      )}
      {isError && (
        <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="scan-page-error">
          Véhicule introuvable — vérifiez que vous êtes connecté au bon compte.
        </p>
      )}
      {vehicle && (
        <ScanDocumentDialog
          open={open}
          onOpenChange={(o) => {
            setOpen(o);
            if (!o) done();
          }}
          vehicle={vehicle}
          initialMode="import"
          forcedType={type || undefined}
          askType={!type}
          onValidated={() => {
            ["vehicles", "vehicle", "documents", "dashboard"].forEach((k) =>
              qc.invalidateQueries({ queryKey: [k] })
            );
          }}
        />
      )}
    </div>
  );
}
