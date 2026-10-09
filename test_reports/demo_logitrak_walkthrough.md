# Démo LogiTrak — parcours commercial 5 minutes (`demo-logitrak`)

> Objectif : présentation fluide, sans chercher où cliquer. Chaque étape nomme l'entité exacte à montrer.
> Connexion : `admin@demo-logitrak.ch` (mot de passe → `memory/test_credentials.md` §6, non affiché ici).
> Avant chaque présentation : `python3 test_reports/demo_logitrak_seed.py reset` (remet la démo à neuf).
> À tout moment : `python3 test_reports/demo_logitrak_seed.py snapshot` (santé + isolation).

Repères constants (les dates sont relatives au jour du dernier seed/reset) :
- Flotte : 10 véhicules — 4 thermiques · 3 électriques · 2 hybrides rechargeables · 1 utilitaire.
- EV vedette : **Tesla Model 3 — GE 771 902** (conducteur **Marc Rochat**, recharges, facture leasing, carte grise).
- Conducteurs : Marc Rochat · Sophie Berger · Daniel Keller · Camille Favre · Luca Moretti · **Elena Schneider (sans véhicule)**.
- Cartes : Migrol ••1182 (active) · Shell ••4473 (active) · **Tamoil ••7290 (expirée)** · **Avia ••3651 (suspendue)**.
- Amendes : **GE-2026-114502 (ouverte)** · **ZH-2026-203994 (en retard)** · **VD-2026-090877 (contestée)** · **VD-2026-088211 (payée)**.

---

## 1. Tableau de bord (≈ 30 s) — « tout voir d'un coup d'œil »
Onglet **Tableau de bord**. Pointer dans l'ordre :
- Cartes rouges/oranges : **Éléments expirés**, **À traiter ≤ 30 jours**, **Documents manquants** (10 véhicules concernés), **Documents à vérifier** (1).
- **Véhicules conformes 6/10**, **Coût annuel flotte ≈ 134 000 CHF**, **Amendes à payer : 3 (1 en retard)**.
- Tableau **Prochaines actions** : échéances de leasing/contrôle les plus urgentes (GE 142 880 Škoda, ZH 556 713 BMW…).
> Message : *« Le gestionnaire sait immédiatement quoi traiter en priorité. »*

## 2. Véhicules → ouvrir un EV (≈ 45 s)
Onglet **Véhicules** → ligne **GE 771 902 — Tesla Model 3** → ouvrir la fiche (drawer).
- **Infos générales + énergie EV** : autonomie 491 km, batterie 75/82 kWh, conso officielle 14.9 kWh/100.
- **Conducteur** : Marc Rochat (affectation active).
- **Documents** : carte grise + contrat de leasing.
- **Énergie** : recharges récentes · **Factures/Coûts** : facture leasing mensuelle.
> Message : *« Une fiche véhicule = centre administratif complet. »*

## 3. Conducteurs (≈ 30 s) — affectation actuelle + historique
Onglet **Conducteurs**.
- **Daniel Keller** : affectation **active BMW 320d (ZH 556 713)** + **historique terminé Toyota Corolla (BE 208 455)**.
- **Elena Schneider** : conductrice **sans véhicule** (nouvelle arrivée).
> Message : *« Historique d'affectation daté, jamais perdu. »*

## 4. Cartes carburant (≈ 30 s) — active vs expirée/suspendue
Onglet **Énergie → Cartes**.
- **Migrol ••1182** : active, valide (véhicule GE 142 880).
- **Tamoil ••7290** : **expirée** (badge rouge) — assignée à la BMW.
- **Avia ••3651** : **suspendue** (statut non actif) — utilitaire Sprinter VS 173 448.
> Message : *« Cartes, affectations et alertes d'expiration centralisées. »*

## 5. Énergie (≈ 45 s) — thermique + recharge EV + rapprochement
Onglet **Énergie → Transactions**.
- Montrer un **plein thermique** (ex. Shell Lausanne-Sébeillon, VW Passat) **rapproché à une carte**.
- Montrer une **recharge EV** (ex. Ionity Nyon, Tesla) en kWh.
- Filtrer **« Tout rattachement »** → pointer une **transaction sans carte** (Coop Pronto Berne, Toyota Corolla) et les **anomalies ouvertes**.
- Onglet **Rapprochements** : achats ↔ consommation (CAN prioritaire).
> Message : *« Dépenses énergie suivies et rapprochées automatiquement, thermique comme électrique. »*

## 6. Documents (≈ 45 s) — les 4 cas clés
Onglet **Documents** (ou via la fiche véhicule).
- **Carte grise** : document présent (Škoda GE 142 880 / Tesla GE 771 902).
- **Facture** : facture entretien **F-2026-3380** (Garage Rondo SA) = enregistrement de coût.
- **Document requis manquant** : **Hyundai Ioniq 5 (ZH 884 326)** — aucun document (apparaît dans « Documents manquants »).
- **Document à valider** : document « à vérifier » sur la **Renault Mégane (VD 640 118)**.
> Message : *« Arborescence par dossier, conformité calculée, factures = coûts. »*

## 7. Amendes (≈ 45 s) — les 4 statuts
Onglet **Amendes**. Montrer une amende de chaque statut :
- **Ouverte** : GE-2026-114502 (Tesla / Marc Rochat) — à payer, échéance future.
- **En retard** : ZH-2026-203994 (BMW / Daniel Keller) — badge rouge, délai dépassé.
- **Contestée** : VD-2026-090877 (Mégane / Camille Favre).
- **Payée** : VD-2026-088211 (Passat / Sophie Berger) — preuve de paiement.
> Message : *« Cycle de vie complet des amendes, avec conducteur identifié. »*

## 8. Connexion chauffeur (≈ 40 s) — self-service
Se déconnecter → se reconnecter avec **`driver@demo-logitrak.ch`** (Marc Rochat).
- **Mes véhicules** : Tesla Model 3 (affectation active).
- **Mes pleins** : ses recharges EV.
- **Mes amendes** : GE-2026-114502.
> Message : *« Le chauffeur ne voit que ce qui le concerne — aucune donnée sensible. »*

## 9. Connexion lecteur (≈ 20 s) — consultation seule
Se reconnecter avec **`readonly@demo-logitrak.ch`**.
- Naviguer librement (Tableau de bord, Véhicules, Amendes) — **lecture autorisée**.
- Tenter une modification (ex. éditer un véhicule / marquer une amende payée) → **refusée (403)**, boutons masqués.
> Message : *« Accès en lecture seule pour la direction/les auditeurs, sans risque de modification. »*

---

### Récapitulatif des 3 niveaux d'accès
| Compte | Rôle | Démontre |
|---|---|---|
| `admin@demo-logitrak.ch` | admin | Administration complète (étapes 1–7) |
| `driver@demo-logitrak.ch` | driver | Self-service chauffeur (étape 8) |
| `readonly@demo-logitrak.ch` | read_only | Consultation seule (étape 9) |

### Après la démo
`python3 test_reports/demo_logitrak_seed.py reset` → remet `demo-logitrak` à l'état initial.
Vérifier : `DEMO RESET = PASS` · `DEFAULT UNCHANGED = PASS` · `OTHER TENANTS UNCHANGED = PASS`.
