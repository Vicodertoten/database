# ADR-0002 — Plan Directeur Noyau Canonique Fort

Date: `2026-04-08`  
Statut: `accepted`

## Contexte

Le repo a dépassé le stade MVP propre et possède déjà une gouvernance canonique crédible.
Le risque principal n'est plus l'absence de structure, mais la dispersion d'exécution:
- ouvrir trop de chantiers en parallèle,
- sur-déclarer des règles canonique sans signaux opératoires explicites,
- laisser coexister trop longtemps des contrats export hétérogènes.

Cet ADR verrouille la trajectoire d'exécution pour transformer le pilote en noyau canonique fort.

## Décisions

1. Cadence d'exécution: `gates séquentiels` stricts.
- Aucune priorité `N+1` ne démarre tant que le DoD de la priorité `N` n'est pas complet.
- Les dépendances sont explicites et ordonnées (détection canonique -> événements -> qualification -> export -> ops).

2. Politique canonique: `auto_clear équilibrée`.
- Hard blockers obligatoires vers `manual_reviewed`:
  - cible absente,
  - cible `provisional`,
  - conflit de mapping sans candidat préféré unique.
- Hors blockers: score sur 5 signaux normalisés.
- Décision: `auto_clear` si score `>= 3`, sinon `manual_reviewed`.
- Toute décision doit porter `reason_code` + `signal_breakdown`.

3. Stratégie export: `v4 breaking` + sidecar `v3` transitoire.
- Le contrat principal est `export.bundle.v4`.
- `export.bundle.v3` reste en sidecar pendant `2 cycles de release`, puis retrait.
- La génération standard `v2` est arrêtée.

## Conséquences

- Le coût de migration downstream est assumé tôt pour stabiliser rapidement un contrat riche.
- L'audit et la roadmap doivent distinguer explicitement:
  - `acté implémenté`,
  - `acté cible`.
- Les revues de run et smokes utilisent un KPI set unique pour éviter les débats implicites.

## Références

- `docs/05_audit_reference.md`
- `docs/10_program_kpis.md`
