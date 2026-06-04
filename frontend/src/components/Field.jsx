import { cn } from "@/lib/utils";

export const fileSize = (n) => {
  if (!n) return "";
  if (n < 1024) return `${n} o`;
  if (n < 1048576) return `${(n / 1024).toFixed(0)} Ko`;
  return `${(n / 1048576).toFixed(1)} Mo`;
};

export function Stat({ label, value, icon: Icon, className }) {
  return (
    <div className={cn("rounded-xl border border-slate-200 bg-white p-4", className)}>
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
        {Icon && <Icon className="h-3.5 w-3.5" />} {label}
      </div>
      <p className="mt-1.5 break-words font-medium text-slate-900">{value ?? "—"}</p>
    </div>
  );
}

export function SectionCard({ title, description, action, children, testId, className }) {
  return (
    <section data-testid={testId} className={cn("rounded-xl border border-slate-200 bg-white p-5 sm:p-6", className)}>
      {(title || action) && (
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            {title && <h4 className="font-display text-base font-semibold tracking-tight text-slate-900">{title}</h4>}
            {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function FormRow({ label, children, className }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label className="text-[11px] font-bold uppercase tracking-[0.1em] text-slate-500">{label}</label>
      {children}
    </div>
  );
}
