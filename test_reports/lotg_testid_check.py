"""Lot G — inventaire statique des data-testid frontend (fichiers Lot G) : total, motifs dynamiques, doublons statiques."""
import collections
import re
import sys

FILES = ["src/lib/fuelStatements.js", "src/components/energy/ExportButtons.jsx", "src/components/energy/ReconciliationDialogs.jsx",
         "src/components/energy/ReconciliationDrawer.jsx", "src/pages/FuelReconciliationsPage.jsx", "src/components/energy/StatementDialogs.jsx",
         "src/components/energy/DeclaredSection.jsx", "src/components/energy/StatementLines.jsx", "src/components/energy/StatementDrawer.jsx",
         "src/pages/FuelStatementsPage.jsx", "src/components/energy/EnergyTabs.jsx"]
PAT = [r'data-testid=\{?["`]([^"`]+)["`]\}?', r'testId="([^"]+)"', r'testId=\{`([^`]+)`\}', r'testIdPrefix="([^"]+)"']
static, dyn, per_file = collections.Counter(), set(), {}
for f in FILES:
    s = open(f"/app/frontend/{f}").read()
    ids = [i for p in PAT for i in re.findall(p, s)]
    per_file[f] = len(ids)
    for i in ids:
        (dyn.add(i) if "${" in i else static.update([i]))
dups = {k: v for k, v in static.items() if v > 1}
print("files:", per_file)
print(f"static ids: {len(static)} · dynamic patterns: {len(dyn)} · total patterns: {len(static) + len(dyn)}")
print("DUPLICATES (static, across Lot G files):", dups or "0")
sys.exit(1 if dups else 0)
