import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, UserRound, X } from "lucide-react";
import { getDrivers } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

export const driverLabel = (d) => d?.display || [d?.prenom, d?.nom].filter(Boolean).join(" ") || "Conducteur";

// Combobox conducteur : liste du tenant courant uniquement, recherche nom/matricule, JAMAIS d'auto-sélection.
export default function DriverPicker({ value, onChange, disabled = false, testId = "driver-picker", allowEmpty = true, placeholder = "Non identifié" }) {
  const [open, setOpen] = useState(false);
  const { data: drivers = [] } = useQuery({ queryKey: ["drivers", "picker"], queryFn: () => getDrivers({ include_archived: "1" }) });
  const selectable = useMemo(() => drivers.filter((d) => !d.is_deleted && d.actif !== false), [drivers]);
  const current = drivers.find((d) => d.id === value);

  return (
    <div className="flex items-center gap-1">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" role="combobox" aria-expanded={open} disabled={disabled} data-testid={`${testId}-trigger`}
            className={cn("h-9 w-full justify-between font-normal", !current && "text-slate-400")}>
            <span className="flex min-w-0 items-center gap-2">
              <UserRound className="h-4 w-4 shrink-0 text-slate-400" />
              <span className="truncate">{current ? driverLabel(current) : placeholder}{current?.is_deleted ? " (archivé)" : current && current.actif === false ? " (inactif)" : ""}</span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command>
            <CommandInput placeholder="Rechercher nom, prénom, matricule…" data-testid={`${testId}-search`} />
            <CommandList>
              <CommandEmpty>Aucun conducteur actif dans ce tenant.</CommandEmpty>
              <CommandGroup>
                {selectable.map((d) => (
                  <CommandItem key={d.id} value={`${d.nom} ${d.prenom || ""} ${d.matricule_interne || ""}`} data-testid={`${testId}-option-${d.id}`}
                    onSelect={() => { onChange(d.id === value ? (allowEmpty ? null : d.id) : d.id); setOpen(false); }}>
                    <Check className={cn("mr-2 h-4 w-4", value === d.id ? "opacity-100" : "opacity-0")} />
                    <span className="truncate">{driverLabel(d)}</span>
                    {d.affectations?.length > 0 && <span className="ml-auto text-[10px] text-slate-400">{d.affectations.map((a) => a.plaque).join(", ")}</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {allowEmpty && value && !disabled && (
        <button type="button" onClick={() => onChange(null)} data-testid={`${testId}-clear`} aria-label="Retirer le conducteur"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
