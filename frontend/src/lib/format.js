export const chf = (n) =>
  new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(Number(n) || 0);

export const chfShort = (n) => {
  const v = Number(n) || 0;
  if (v >= 1000) return `${(v / 1000).toLocaleString("fr-CH", { maximumFractionDigits: 1 })}k`;
  return v.toLocaleString("fr-CH");
};

export const dateFr = (s) => {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("fr-CH", { day: "2-digit", month: "2-digit", year: "numeric" });
};

export const dateFrLong = (s) => {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("fr-CH", { day: "numeric", month: "long", year: "numeric" });
};

export const fmtKm = (n) => `${new Intl.NumberFormat("fr-CH").format(Number(n) || 0)} km`;

export const fmtNum = (n) => new Intl.NumberFormat("fr-CH").format(Number(n) || 0);

export const daysLabel = (days) => {
  if (days === null || days === undefined) return "—";
  if (days < 0) return `Échu depuis ${Math.abs(days)} j`;
  if (days === 0) return "Aujourd'hui";
  return `Dans ${days} j`;
};
