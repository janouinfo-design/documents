import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Car, FileText, ShieldCheck, ScrollText, Images, ClipboardCheck, FolderTree,
  Gauge, MapPin, User, Radio, Loader2, Hash,
} from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { getVehicle, getDocuments } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { cn } from "@/lib/utils";
import StatusBadge from "@/components/StatusBadge";
import GeneralTab from "@/components/tabs/GeneralTab";
import LeasingTab from "@/components/tabs/LeasingTab";
import AssuranceTab from "@/components/tabs/AssuranceTab";
import CarteGriseTab from "@/components/tabs/CarteGriseTab";
import InspectionTab from "@/components/tabs/InspectionTab";
import ControleTab from "@/components/tabs/ControleTab";
import DocumentsTab from "@/components/tabs/DocumentsTab";

const TABS = [
  { key: "general", label: "Général", icon: Car },
  { key: "leasing", label: "Leasing", icon: FileText },
  { key: "assurance", label: "Assurance", icon: ShieldCheck },
  { key: "carte-grise", label: "Carte grise", icon: ScrollText },
  { key: "etat-des-lieux", label: "État des lieux", icon: Images },
  { key: "controle", label: "Contrôles", icon: ClipboardCheck },
  { key: "documents", label: "Documents", icon: FolderTree },
];

function Chip({ icon: Icon, children }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 px-2.5 py-1 text-xs font-medium text-slate-600">
      <Icon className="h-3.5 w-3.5 text-slate-400" />
      {children}
    </span>
  );
}

export default function VehicleDrawer({ open, onOpenChange, vehicleId, initialTab = "general" }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab);

  useEffect(() => {
    if (open) setTab(initialTab);
  }, [open, initialTab, vehicleId]);

  const { data: vehicle, isLoading } = useQuery({
    queryKey: ["vehicle", vehicleId],
    queryFn: () => getVehicle(vehicleId),
    enabled: open && !!vehicleId,
  });

  const { data: docs = [], refetch: refetchDocs } = useQuery({
    queryKey: ["documents", vehicleId],
    queryFn: () => getDocuments(vehicleId),
    enabled: open && !!vehicleId,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["vehicle", vehicleId] });
    qc.invalidateQueries({ queryKey: ["vehicles"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["timeline"] });
  };

  const m = vehicle?.metrics || {};
  const tabProps = { vehicle, metrics: m, onSaved: refresh, docs, refetchDocs };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-3xl lg:max-w-4xl"
        data-testid="vehicle-drawer"
      >
        {isLoading || !vehicle ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="shrink-0 border-b border-slate-200 bg-white p-5 sm:p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <div className="h-28 w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-100 sm:h-24 sm:w-40">
                  {vehicle.photo_url ? (
                    <img src={vehicle.photo_url} alt={vehicle.plaque} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-slate-300"><Car className="h-8 w-8" /></div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <SheetTitle className="font-display text-2xl font-bold tracking-tight text-slate-900">
                      {vehicle.plaque}
                    </SheetTitle>
                    <StatusBadge level={m.overall} testId="drawer-overall-status" />
                  </div>
                  <SheetDescription className="mt-0.5 text-sm text-slate-500">
                    {vehicle.marque} {vehicle.modele} · {vehicle.annee}
                  </SheetDescription>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Chip icon={Hash}>{vehicle.vin || "VIN —"}</Chip>
                    <Chip icon={Gauge}>{fmtKm(vehicle.kilometrage)}</Chip>
                    <Chip icon={MapPin}>{vehicle.base || "—"} · {vehicle.groupe || "—"}</Chip>
                    <Chip icon={User}>{vehicle.responsable || "—"}</Chip>
                    <Chip icon={Radio}>{vehicle.tracker_gps || "—"}</Chip>
                  </div>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
              <div className="shrink-0 overflow-x-auto border-b border-slate-200 bg-white">
                <TabsList className="h-auto w-max justify-start gap-1 rounded-none bg-transparent px-4 py-0">
                  {TABS.map((t) => {
                    const Icon = t.icon;
                    return (
                      <TabsTrigger
                        key={t.key}
                        value={t.key}
                        data-testid={`tab-${t.key}`}
                        className="gap-1.5 rounded-none border-b-2 border-transparent px-3 py-3 text-sm font-medium text-slate-500 shadow-none transition-colors data-[state=active]:border-slate-900 data-[state=active]:bg-transparent data-[state=active]:text-slate-900 data-[state=active]:shadow-none"
                      >
                        <Icon className="h-4 w-4" />
                        {t.label}
                      </TabsTrigger>
                    );
                  })}
                </TabsList>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-4 sm:p-6">
                <TabsContent value="general" className="mt-0"><GeneralTab {...tabProps} /></TabsContent>
                <TabsContent value="leasing" className="mt-0"><LeasingTab {...tabProps} /></TabsContent>
                <TabsContent value="assurance" className="mt-0"><AssuranceTab {...tabProps} /></TabsContent>
                <TabsContent value="carte-grise" className="mt-0"><CarteGriseTab {...tabProps} /></TabsContent>
                <TabsContent value="etat-des-lieux" className="mt-0"><InspectionTab {...tabProps} /></TabsContent>
                <TabsContent value="controle" className="mt-0"><ControleTab {...tabProps} /></TabsContent>
                <TabsContent value="documents" className="mt-0"><DocumentsTab {...tabProps} /></TabsContent>
              </div>
            </Tabs>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
