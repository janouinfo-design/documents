import { cn } from "@/lib/utils";
import { metaOf } from "@/lib/fuelImport";

// Pastille générique (statut ligne / rattachement / carte / anomalie) — codes techniques de l'API, libellés FR
export default function Pill({ map, code, testId, className, prefix }) {
  const m = metaOf(map, code);
  return (
    <span data-testid={testId} className={cn("inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-bold", m.cls, className)}>
      {prefix}{m.label}
    </span>
  );
}
