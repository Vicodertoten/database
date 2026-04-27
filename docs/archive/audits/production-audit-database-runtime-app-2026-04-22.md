# Audit Production-Grade - database + runtime-app

Date: 2026-04-22
Portee: `database` + `runtime-app` + interfaces inter-repos
Repos audites:
- `/Users/ryelandt/Documents/database`
- `/Users/ryelandt/Documents/runtime-app`

## Section A - Executive Summary

Verdict global: GO_WITH_GAPS

Decision d'usage:
- GO_WITH_GAPS pour un pilot/staging controle, avec correction immediate des items P0 ci-dessous.
- Pas de GO plein "production-hardened" a ce stade.

Niveau de confiance de l'audit: Moyen
- Eleve sur le code, les contrats documentes, les tests locaux et les workflows CI lisibles.
- Moyen global car plusieurs controles critiques de plateforme et d'exploitation sont non auditables depuis les deux repos seuls: protections GitHub, secrets/rotation sur Fly/Vercel, exposition reseau reelle, permissions cloud, alerting live, traces live, backups/restores et drills de rollback.

Top 5 risques majeurs:
1. `database` n'est pas release-ready: le gate `verify_repo` n'est pas vert a cause d'un echec de test de coherence documentaire et d'un gate Ruff rouge.
2. Historical note: this audit flagged weak runtime payload validation, but runtime guards now validate key structural shape beyond version tags; keep improving by generating validators directly from owner schemas.
3. La supply chain est asymetrique et insuffisamment durcie: secret scan present dans `database`, absent dans `runtime-app`; aucun SBOM ni scan de vulnerabilites bloqueur n'a ete trouve.
4. Les controles plateforme critiques restent non auditables: protections de branches GitHub, politiques de secrets, rotation effective des cles, exposition effective des services Fly/Vercel, permissions Supabase/GitHub.
5. L'observabilite et la readiness d'incident sont partielles: metriques et runbooks existent, mais pas de preuves d'alerting, de dashboards, de traces distribuees, ni de seuils automatiques appliques en environnement reel.

Effort de remediation estime:
- Court terme: 2 a 5 jours pour remettre `database` au vert, ajouter les scans secrets manquants, brancher les smokes manquants dans la CI, et verrouiller la validation forte des contrats owner-side.
- Moyen terme: 2 a 4 semaines pour ajouter du cross-repo E2E nominal, durcir migrations/versioning, ajouter audit de dependances, dashboards/alertes et preuves de rotation/rollback.
- Long terme: 1 a 2 trimestres pour atteindre un niveau production-hardened (RBAC/service identity, SBOM/provenance, drills formels, benchmark/perf budgets, gouvernance plateforme codifiee).

Principales zones non auditables et impact sur la decision:
- GitHub branch protection, CODEOWNERS effectifs, environments/protections: non auditables; empeche de conclure a un GO plein.
- Fly/Vercel/secret stores/reseaux prives/rotation effective: non auditables; empeche de conclure a une posture securisee en production.
- Supabase permissions: aucune configuration ni preuve d'usage/absence d'usage n'a ete fournie; non auditable.
- Logs/metrics/traces/alertes de production: non auditables; empeche de conclure sur la fiabilite operationnelle reelle.

## Section B - Coverage Ledger

| Domaine | Statut de couverture | Preuves principales | Risques residuels |
|---|---|---|---|
| 1. Architecture globale et separation database vs runtime-app | Couvert | `database/README.md`, `runtime-app/README.md`, `runtime-app/docs/10_architecture/00_architecture_boundaries.md` | Frontieres bien documentees, mais validation E2E nominale cross-repo absente de la CI. |
| 2. Contrats de donnees, schemas, versioning, compatibilite | Partiel | `database/schemas/*.schema.json`, `database/src/database_core/playable/contract.py`, `database/src/database_core/pack/contract.py`, `runtime-app/packages/contracts/src/index.ts`, `runtime-app/packages/contracts/src/guards.ts` | Contrats owner versionnes, mais miroir consumer manuel et validation runtime insuffisante. |
| 3. Flux inter-repos, dependances, couplages, points de rupture | Couvert | `database/docs/20_execution/chantiers/INT-017-runtime-app-handoff-checklist.md`, `database/docs/20_execution/integration_log.md`, `runtime-app/docs/20_execution/integration_log.md`, `runtime-app/docs/deployment_v1.md` | Points de rupture identifies, mais pas de CI composee cross-repo nominale. |
| 4. Qualite du code et maintainability | Partiel | `runtime-app/.github/workflows/ci.yml`, `database/scripts/verify_repo.py`, execution locale `pnpm run check`, execution locale `ruff check` | `runtime-app` vert localement; `database` rouge sur doc/test + Ruff. |
| 5. Build, CI/CD, release management, migrations, rollback | Partiel | `database/.github/workflows/verify-repo.yml`, `runtime-app/.github/workflows/ci.yml`, `database/src/database_core/storage/postgres_migrations.py`, `runtime-app/apps/api/src/scripts/migrate-runtime-db.ts`, `runtime-app/docs/deployment_v1.md` | Rollback documente mais pas de drill prouve; migrations `database` sans checksum; CI cross-repo absente. |
| 6. Pipeline database de bout en bout | Couvert | `database/docs/02_pipeline.md`, `database/scripts/run_pipeline.py`, `database/scripts/fetch_inat_snapshot.py`, `database/scripts/qualify_inat_snapshot.py`, tests locaux `pytest` | Flux e2e present, mais smoke live reste manuel et non CI. |
| 7. Fonctionnement interne database: invariants, indexation, integrite | Couvert | `database/src/database_core/storage/postgres_schema.py`, `database/src/database_core/storage/postgres.py` | Invariants schema bons; auditabilite des migrations perfectible. |
| 8. Securite applicative | Partiel | `database/src/database_core/runtime_read/http_server.py`, `database/src/database_core/editorial_write/http_server.py`, `runtime-app/apps/api/src/security/operator-auth.ts`, `runtime-app/apps/api/src/routes/*` | Auth presente mais minimale (API keys/shared token), validation des payloads trop faible, pas de RBAC. |
| 9. Securite plateforme | Non auditable | Docs de deploiement seulement: `runtime-app/docs/deployment_v1.md` | Pas de preuves GitHub/Fly/Vercel/Supabase exploitables depuis les repos. |
| 10. Supply chain | Partiel | `database/.github/workflows/secret-scan.yml`, `runtime-app/.github/workflows/ci.yml`, `database/pyproject.toml`, `runtime-app/pnpm-lock.yaml` | `runtime-app` sans secret-scan, sans SBOM, sans audit dep; `database` sans lock Python reproductible. |
| 11. Resilience et fiabilite | Partiel | `runtime-app/apps/api/src/integrations/database/owner-http-provider.ts`, `runtime-app/apps/api/src/integrations/database/owner-http-editorial-provider.ts`, `runtime-app/apps/api/src/storage/session-store.ts` | Retries/timeouts/idempotence presentes, mais pas de circuit breaker, bulkhead, ni drill de reprise. |
| 12. Observabilite et exploitation | Partiel | `runtime-app/apps/api/src/observability/metrics.ts`, `database/src/database_core/runtime_read/http_server.py`, `database/src/database_core/editorial_write/http_server.py`, `runtime-app/docs/20_execution/phase6_pilot_runbook.md`, `database/docs/security_incident_runbook.md` | Logs/metriques/runbooks presents, mais pas d'alerting/traces/dashboards ni preuves live. |
| 13. Performance et cout | Partiel | `runtime-app/scripts/pilot-load-test.mjs`, `runtime-app/apps/api/src/observability/metrics.ts`, `database/src/database_core/storage/postgres_schema.py`, `database/src/database_core/runtime_read/http_server.py` | Outils de mesure presents, mais pas de benchmarks/couts/slow queries reels fournis. |
| 14. Qualite de tests | Partiel | `runtime-app/apps/api/src/tests/*`, `runtime-app/apps/web/tests/smoke/*`, `runtime-app/apps/mobile/App.smoke.test.tsx`, `database/tests/*` | Bonne couverture locale, mais certains tests critiques ne tournent pas en CI; `database` gate rouge. |
| 15. Qualite pedagogique de la database | Partiel | `database/README.md`, `database/docs/02_pipeline.md`, `database/tests/test_multilingual_pedagogy.py`, `database/src/database_core/storage/playable_store.py` | Signaux pedagogiques presents, couverture multilingue encore explicitement partielle. |
| 16. Gouvernance documentaire | Partiel | `database/scripts/check_doc_code_coherence.py`, `database/tests/test_verify_repo.py`, `database/docs/05_audit_reference.md`, `database/docs/codex_execution_plan.md` | Garde-fous presents, mais une divergence bloque deja le gate de verification. |
| 17. Conformite et risques operationnels | Partiel | `database/docs/security_incident_runbook.md`, tables historiques et events dans `database/src/database_core/storage/postgres_schema.py`, integration logs cross-repo | Traçabilite bonne cote data; retention, suppression, backups, preuves cloud et controle d'acces reels non audites. |

Registre de non-couverture explicite:
- Protections de branches GitHub: non auditable, faute d'acces aux reglages du repository GitHub.
- Environments GitHub, required reviewers, secrets GitHub Actions: non auditables.
- Fly.io/Vercel reseaux prives, secrets, rotation, policies: non auditables.
- Supabase permissions/configuration: non auditable; aucun artefact ni preuve d'usage ou de non-usage n'a ete trouve.
- Logs, metriques, traces, couts et alertes de production: non auditables; aucune exportation live ni dashboard fournis.
- Backups, restore drills, rollback drills executes: non auditables.

## Section C - Findings priorises

### F-001

- Severite: Moyenne
- Domaine: Contrats et interfaces database <-> runtime-app
- Constat factuel: this finding is partially outdated. `runtime-app` now enforces structural guards beyond version tags for core owner payloads, but schema-derived validation remains recommended to reduce drift risk.
- Preuve tracable:
  - Type: fichier
  - Emplacement exact: `runtime-app/packages/contracts/src/guards.ts`; `runtime-app/apps/api/src/integrations/database/owner-http-provider.ts`; `runtime-app/apps/api/src/integrations/database/owner-http-editorial-provider.ts`
  - Extrait observe: guards verify version + required structural fields; recommendation remains to align validation generation directly with owner JSON schemas.
  - Reproductibilite: `cd /Users/ryelandt/Documents/runtime-app && sed -n '1,220p' packages/contracts/src/guards.ts && sed -n '1,240p' apps/api/src/integrations/database/owner-http-provider.ts && sed -n '1,320p' apps/api/src/integrations/database/owner-http-editorial-provider.ts`
- Impact business: un payload owner-side mal forme peut traverser l'API runtime, casser les parcours web/mobile/editorial/institutional, ou produire des erreurs tardives plus couteuses a diagnostiquer.
- Probabilite: Moyenne
- Recommandation minimale: valider les payloads owner-side contre les schemas JSON officiels avant exposition runtime; refuser tout payload incomplet avec `owner_payload_invalid`.
- Recommandation structurante: generer types + validateurs consumer directement depuis les schemas `database/schemas/*` pour supprimer le drift manuel.
- Quick win < 1 jour: oui
- Validation: ajouter des tests negatifs injectant un payload avec seulement le tag de version et verifier un rejet explicite; relancer `cd /Users/ryelandt/Documents/runtime-app && pnpm --filter @runtime-app/api run test:all`.

### F-002

- Severite: Haute
- Domaine: Gouvernance documentaire / release gate `database`
- Constat factuel: le gate de verification `database` echoue sur un test de coherence documentaire. `tests/test_verify_repo.py` attend encore un marqueur `Politique distracteurs v2`, tandis que `docs/codex_execution_plan.md` documente `Politique distracteurs v3`.
- Preuve tracable:
  - Type: test + fichier + commande
  - Emplacement exact: `database/tests/test_verify_repo.py`; `database/docs/codex_execution_plan.md`
  - Extrait observe: le test contient `_assert_any_contains(plan, ("Politique distracteurs v2", "distracteurs v2"))`; le plan documente `Gate 5 - Politique distracteurs v3`.
  - Reproductibilite: `cd /Users/ryelandt/Documents/database && ./.venv/bin/python -m pytest -q -p no:capture tests/test_verify_repo.py::test_gate_8_docs_keep_playable_gap_and_gate_ordering_visible`
- Impact business: impossible de considerer le repo `database` comme release-ready; les garanties docs/code sont deja brisees sur un controle bloqueur.
- Probabilite: Elevee
- Recommandation minimale: aligner le test et la doctrine courante sur la meme nomenclature de gate.
- Recommandation structurante: centraliser les marqueurs de gates/versionnement documentaire dans une source unique testee, plutot que dupliquer les chaines dans plusieurs fichiers.
- Quick win < 1 jour: oui
- Validation: relancer `cd /Users/ryelandt/Documents/database && ./.venv/bin/python -m pytest -q -p no:capture tests/test_verify_repo.py::test_gate_8_docs_keep_playable_gap_and_gate_ordering_visible`.

### F-003

- Severite: Haute
- Domaine: Qualite du code / maintenabilite / release gate `database`
- Constat factuel: le lint gate du repo `database` est rouge avec 46 erreurs Ruff (imports non tries, longueurs de ligne, imports inutilises, variable inutilisee), principalement dans les scripts et tests de la phase 3.x.
- Preuve tracable:
  - Type: commande
  - Emplacement exact: `database/src/database_core/ops/phase3_taxon_remediation.py`, `database/scripts/phase3_1_complete_measurement.py`, `database/scripts/phase3_1_preflight_v2_protocol.py`, `database/tests/test_phase3_taxon_remediation.py`, etc.
  - Extrait observe: `Found 46 errors.` a la fin de `ruff check src tests scripts`.
  - Reproductibilite: `cd /Users/ryelandt/Documents/database && ./.venv/bin/python -m ruff check src tests scripts`
- Impact business: la chaine locale de verification n'est pas promouvable telle quelle; la dette s'accumule dans des scripts deja relies a des protocoles de mesure et de remediation.
- Probabilite: Elevee
- Recommandation minimale: corriger les erreurs Ruff existantes sur les scripts/tests phase 3.x avant nouvelle extension de perimetre.
- Recommandation structurante: isoler les scripts experimentaux hors du gate principal tant qu'ils ne respectent pas le meme niveau de qualite que le coeur produit.
- Quick win < 1 jour: non
- Validation: rerun `cd /Users/ryelandt/Documents/database && ./.venv/bin/python -m ruff check src tests scripts` avec sortie vide.

### F-004

- Severite: Haute
- Domaine: Supply chain / securite plateforme
- Constat factuel: `runtime-app` n'expose aucun workflow de secret scan bloqueur, aucun scan de dependances, aucun SBOM ou provenance artifact visible dans le repo. Le seul workflow detecte est `ci.yml`.
- Preuve tracable:
  - Type: workflow + commande
  - Emplacement exact: `runtime-app/.github/workflows/ci.yml`
  - Extrait observe: la recherche `gitleaks|secret-scan|audit|sbom|cyclonedx|snyk|dependabot` sur `.github`, `package.json`, `apps`, `packages`, `infra`, `docs` ne retourne rien; a l'inverse `database` expose `secret-scan.yml` avec Gitleaks.
  - Reproductibilite: `cd /Users/ryelandt/Documents/runtime-app && find .github -maxdepth 2 -type f | sort && grep -RniE 'gitleaks|secret-scan|audit|sbom|cyclonedx|snyk|dependabot' .github package.json apps packages infra docs || true`
- Impact business: fuite de secrets, dependances vulnerables et absence de trace de composition logicielle peuvent atteindre la production sans garde-fou dedie.
- Probabilite: Moyenne a elevee
- Recommandation minimale: ajouter un job Gitleaks bloqueur et un audit dep minimal sur le lockfile `pnpm`.
- Recommandation structurante: produire un SBOM CycloneDX en CI, gerer les dependances via politique de mise a jour, et signer/provenir les artefacts de release.
- Quick win < 1 jour: oui
- Validation: nouvelle CI `runtime-app` avec jobs `secret-scan`, `dependency-audit` et artefact SBOM genere.

### F-005

- Severite: Haute
- Domaine: Reproductibilite build / supply chain `database`
- Constat factuel: `database` utilise des ranges de versions Python non verrouilles et la CI installe les dependances par `pip install -e ".[dev]"` sans lockfile ni constraints file.
- Preuve tracable:
  - Type: fichier + workflow
  - Emplacement exact: `database/pyproject.toml`; `database/.github/workflows/verify-repo.yml`
  - Extrait observe: dependances `jsonschema>=4.0,<5`, `psycopg[binary]>=3.2,<4`, etc.; en CI: `pip install -e ".[dev]"`.
  - Reproductibilite: `cd /Users/ryelandt/Documents/database && sed -n '1,120p' pyproject.toml && sed -n '1,120p' .github/workflows/verify-repo.yml`
- Impact business: deux runs CI a dates differentes peuvent resoudre des transients differents et introduire des regressions non controlees.
- Probabilite: Elevee
- Recommandation minimale: geler un jeu de dependances via `constraints.txt` ou lock Python dedie au CI/release.
- Recommandation structurante: adopter un workflow de dependances reproductible (uv/pip-tools/poetry/pixi) avec revue explicite des mises a jour.
- Quick win < 1 jour: oui
- Validation: build CI `database` avec resolution immuable et diff detecte lors d'une tentative de bump non revu.

### F-006

- Severite: Haute
- Domaine: Securite plateforme / conformite operationnelle
- Constat factuel: les controles critiques GitHub/Fly/Vercel/Supabase ne sont pas auditables a partir des deux repos. Les docs de deploiement decrivent une posture cible, mais aucune preuve d'application effective n'est presente dans les artefacts audites.
- Preuve tracable:
  - Type: documentation + absence d'artefacts exploitables
  - Emplacement exact: `runtime-app/docs/deployment_v1.md`; `runtime-app/.github/workflows/ci.yml`; `database/.github/workflows/*`
  - Extrait observe: la doc indique des secrets et services prives (`db-owner-read.internal`, `OWNER_SERVICE_TOKEN`, `OPERATOR_API_KEY_CURRENT`), mais aucun export IaC, policy-as-code, ni preuve de protection GitHub/secret rotation n'est present dans les repos.
  - Reproductibilite: revue documentaire + collecte des workflows seulement; aucune commande repo ne permet de prouver les reglages SaaS/console.
- Impact business: impossible d'attester que la posture documentee est effectivement appliquee en production/staging.
- Probabilite: Elevee
- Recommandation minimale: fournir preuves exportables des protections actives (captures de settings, CLI exports, policies, inventaire secrets, dates de rotation).
- Recommandation structurante: codifier ces controles en IaC/policy-as-code et relier leur validation a la CI/CD.
- Quick win < 1 jour: non
- Validation: fournir/exporter la preuve de protection des branches, d'environnements proteges, de rotation de cles, de restriction reseau et de configuration des secrets pour chaque environnement.

### F-007

- Severite: Moyenne
- Domaine: Tests / robustesse cross-repo
- Constat factuel: les tests existent pour les smokes web/mobile et la persistance Postgres runtime, mais la CI `runtime-app` ne les execute pas. La CI ne valide pas non plus un scenario nominal combine avec les owner services `database` reels.
- Preuve tracable:
  - Type: workflow + scripts/tests
  - Emplacement exact: `runtime-app/.github/workflows/ci.yml`; `runtime-app/apps/web/tests/smoke/player-smoke.spec.ts`; `runtime-app/apps/mobile/App.smoke.test.tsx`; `runtime-app/apps/api/package.json`
  - Extrait observe: le workflow racine appelle `pnpm --filter @runtime-app/api run test:all`, mais pas `@runtime-app/web run test:smoke`, pas `@runtime-app/mobile run test:smoke`, pas `test:sessions:postgres`, et aucun workflow cross-repo compose n'a ete trouve.
  - Reproductibilite: `cd /Users/ryelandt/Documents/runtime-app && sed -n '1,220p' .github/workflows/ci.yml && sed -n '1,220p' apps/api/package.json`
- Impact business: des regressions sur les parcours visibles ou sur la persistance Postgres peuvent atteindre la branche principale sans garde-fou automatique.
- Probabilite: Moyenne
- Recommandation minimale: ajouter web smoke, mobile smoke et `test:sessions:postgres` dans la CI `runtime-app`.
- Recommandation structurante: ajouter une CI cross-repo par `docker compose` validant `owner-http` nominal de bout en bout.
- Quick win < 1 jour: oui
- Validation: pipeline CI etendue, puis `pnpm --filter @runtime-app/web run test:smoke`, `pnpm --filter @runtime-app/mobile run test:smoke`, `pnpm --filter @runtime-app/api run test:sessions:postgres` en environnement CI.

### F-008

- Severite: Moyenne
- Domaine: Migrations / rollback / auditabilite des changements
- Constat factuel: `database` stocke seulement un numero de version de migration (`schema_migrations.version`) sans checksum ni detection de script modifie a posteriori, alors que `runtime-app` stocke `filename + checksum`. Aucun des deux repos n'expose de down migrations ni de preuve de rollback drill.
- Preuve tracable:
  - Type: fichier
  - Emplacement exact: `database/src/database_core/storage/postgres_migrations.py`; `runtime-app/apps/api/src/scripts/migrate-runtime-db.ts`; `runtime-app/docs/deployment_v1.md`
  - Extrait observe: `database` cree `schema_migrations(version INTEGER PRIMARY KEY, applied_at ...)`; `runtime-app` cree `runtime_schema_migrations(filename, checksum, applied_at)` et refuse une migration modifiee; la doc rollback reste orientee service, pas DB down migration.
  - Reproductibilite: `cd /Users/ryelandt/Documents/database && sed -n '1,220p' src/database_core/storage/postgres_migrations.py && cd /Users/ryelandt/Documents/runtime-app && sed -n '1,220p' apps/api/src/scripts/migrate-runtime-db.ts && sed -n '1,220p' docs/deployment_v1.md`
- Impact business: difficultes accrues pour detecter une migration historique altreee, prouver la chaine de changement, ou restaurer proprement un etat precedent sous contrainte.
- Probabilite: Moyenne
- Recommandation minimale: ajouter un checksum des migrations `database` et documenter explicitement la strategie de rollback DB.
- Recommandation structurante: standardiser forward-only + checksum + restore drill + rehearsal de rollback sur les deux repos.
- Quick win < 1 jour: non
- Validation: tests de migration tamper-detection + compte rendu de rollback drill avec temps de reprise mesure.

### F-009

- Severite: Moyenne
- Domaine: Observabilite / exploitation
- Constat factuel: des metriques et logs existent, mais l'observabilite reste locale/processus et documentaire. `runtime-app` expose des compteurs et pseudo-quantiles en memoire; les services owner `database` emettent du JSON log; aucune config d'alerting, dashboard, traces distribuees ou budget d'erreur n'a ete trouvee.
- Preuve tracable:
  - Type: fichier
  - Emplacement exact: `runtime-app/apps/api/src/observability/metrics.ts`; `runtime-app/docs/20_execution/phase6_pilot_runbook.md`; `database/src/database_core/runtime_read/http_server.py`; `database/src/database_core/editorial_write/http_server.py`
  - Extrait observe: `renderPrometheus()` calcule des `p50/p95` a partir d'echantillons en memoire; le runbook documente des seuils, mais aucun artefact d'alerting n'est versionne.
  - Reproductibilite: `cd /Users/ryelandt/Documents/runtime-app && sed -n '1,220p' apps/api/src/observability/metrics.ts && sed -n '1,220p' docs/20_execution/phase6_pilot_runbook.md`
- Impact business: la detection precoce des incidents et l'analyse post-incident restent fragiles et dependantes d'actions manuelles.
- Probabilite: Moyenne
- Recommandation minimale: versionner des alertes minimales (owner_timeout, 5xx, p95) et des dashboards de base.
- Recommandation structurante: ajouter tracing distribue, budgets d'erreur, retention de metriques et correlation cross-repo par request id.
- Quick win < 1 jour: oui
- Validation: presence d'artefacts d'alerting versionnes et exercice de simulation incident reussi.

### F-010

- Severite: Moyenne
- Domaine: Authn/Authz et surfaces d'attaque
- Constat factuel: l'acces operateur dans `runtime-app` repose sur des API keys statiques (`x-api-key`), et l'acces owner-side repose sur un shared token `X-Owner-Service-Token` optionnel. Aucun RBAC, aucune identite de service forte ni mTLS n'est visible dans les artefacts audites.
- Preuve tracable:
  - Type: fichier + doc
  - Emplacement exact: `runtime-app/apps/api/src/security/operator-auth.ts`; `runtime-app/docs/deployment_v1.md`; `database/src/database_core/runtime_read/http_server.py`; `database/src/database_core/editorial_write/http_server.py`
  - Extrait observe: `authorizeOperatorRequest(...)` compare des secrets statiques `current`/`next`; `OWNER_SERVICE_TOKEN` est lu depuis l'environnement et compare a un header.
  - Reproductibilite: `cd /Users/ryelandt/Documents/runtime-app && sed -n '1,220p' apps/api/src/security/operator-auth.ts && sed -n '1,220p' docs/deployment_v1.md && cd /Users/ryelandt/Documents/database && sed -n '1,220p' src/database_core/runtime_read/http_server.py`
- Impact business: controle d'acces acceptable pour un pilot limite, insuffisant pour une posture production-hardened sur surfaces operateur.
- Probabilite: Moyenne
- Recommandation minimale: rendre les tokens mandatory en environnements stricts, journaliser la rotation, durcir la distribution et la portee des cles.
- Recommandation structurante: passer a une authn/authz fondee sur identites de service + RBAC/ABAC pour les surfaces operateur.
- Quick win < 1 jour: non
- Validation: tests d'autorisation multi-profils + preuve de rotation + restrictions reseau appliquees.

## Section D - Contrats et interfaces database <-> runtime-app

### Inventaire des contrats observes

Contrats de lecture officiels:
- `playable_corpus.v1`
  - Source de verite owner: `database/schemas/playable_corpus_v1.schema.json`
  - Validation owner: `database/src/database_core/playable/contract.py`
  - Surface owner: `database/src/database_core/runtime_read/http_server.py` -> `GET /playable-corpus`
  - Consommation runtime: `runtime-app/apps/api/src/integrations/database/owner-http-provider.ts`

- `pack.compiled.v1`
  - Source de verite owner: `database/schemas/pack_compiled_v1.schema.json`
  - Validation owner: `database/src/database_core/pack/contract.py`
  - Surface owner: `GET /packs/:packId/compiled/:revision?`
  - Consommation runtime: `runtime-app/apps/api/src/integrations/database/owner-http-provider.ts`

- `pack.materialization.v1`
  - Source de verite owner: `database/schemas/pack_materialization_v1.schema.json`
  - Validation owner: `database/src/database_core/pack/contract.py`
  - Surface owner: `GET /materializations/:materializationId`
  - Consommation runtime: `runtime-app/apps/api/src/integrations/database/owner-http-provider.ts`

Contrats d'operations editoriales observes:
- `pack.create.v1`
- `pack.diagnose.v1`
- `pack.compile.v1`
- `pack.materialize.v1`
- `enrichment.request.status.v1`
- `enrichment.enqueue.v1`
- `enrichment.execute.v1`

Ces enveloppes sont exposees owner-side par `database/src/database_core/editorial_write/http_server.py` et consommees par `runtime-app/apps/api/src/integrations/database/owner-http-editorial-provider.ts`.

### Compatibilite ascendante / descendante

Constat:
- Les contrats owner sont explicitement versionnes et valides cote `database` avant emission/persistance.
- `runtime-app` maintient un miroir manuel des types dans `packages/contracts/src/index.ts`.
- La compatibilite descendante est seulement partiellement protegee cote consumer, car la validation runtime repose principalement sur des version tags.

Evaluation:
- Compatibilite ascendante cote owner: bonne discipline de versionnement (`*.v1`, `schema_version`, schemas JSON).
- Compatibilite cote consumer: partielle; un changement de structure non detecte par le miroir manuel ou les guards peut casser le runtime a l'execution.

### Risques de rupture et blast radius

Ruptures probables:
1. ajout/suppression/renommage de champs dans `playable_corpus.v1`
   - blast radius: `runtime-app/apps/api`, web `/play`, mobile `App.tsx`, index de corpus et scoring/session DTOs
2. rupture de forme sur `pack.materialization.v1`
   - blast radius: creation de session, parcours institutional, session snapshots, correction UX
3. rupture sur enveloppes editoriales
   - blast radius: `/editorial`, surfaces operateur, pilot load flows

### Strategie de versionnement recommandee

1. Conserver `database/schemas/*` comme seule source de verite.
2. Generer types + validateurs consumer a partir de ces schemas.
3. Interdire tout changement breaking sans nouveau suffixe de contrat (`*.v2`).
4. Maintenir un mode dual-read / dual-accept au runtime tant qu'un contrat `v1` reste consomme en production.
5. Exiger un changelog de contrat et un schema diff en PR.

### Garde-fous CI a ajouter

1. Job cross-repo qui monte `database` owner services et `runtime-app` via `infra/docker-compose.yml`, puis execute un smoke nominal `owner-http`.
2. Job de schema diff entre `database/schemas/*` et le consumer package genere.
3. Tests negatifs de validation structurelle sur tous les payloads owner-side.
4. Blocage CI si web smoke, mobile smoke ou `sessions:postgres` ne passent pas.

## Section E - Tests et qualite

### Matrice risques <-> tests existants

| Risque | Tests existants observes | Statut |
|---|---|---|
| Drift de contrat runtime read | `runtime-app/apps/api/src/tests/contracts.integration.test.ts`, `owner-http-provider.integration.test.ts`, `database/tests/test_runtime_read_owner_service.py` | Partiel: bonne couverture positive, faible validation structurelle runtime. |
| Drift de contrat editorial owner-write | `runtime-app/apps/api/src/tests/owner-http-editorial-provider.integration.test.ts`, `database/tests/test_editorial_write_owner_service.py` | Partiel: flux verifies, validation structurelle consumer faible. |
| Regression UI visible web | `runtime-app/apps/web/tests/smoke/player-smoke.spec.ts`, `editorial-smoke.spec.ts`, `institutional-smoke.spec.ts` | Partiel: passe localement, non branche en CI. |
| Regression UI visible mobile | `runtime-app/apps/mobile/App.smoke.test.tsx` | Partiel: passe localement, non branche en CI racine. |
| Persistance session Postgres runtime | `runtime-app/apps/api/src/tests/sessions.postgres.integration.test.ts` | Partiel: test existe, non lance dans la CI racine. |
| Idempotence et erreurs API runtime | `runtime-app/apps/api/src/tests/sessions.integration.test.ts`, `observability-and-errors.integration.test.ts` | Couvert localement. |
| Cohesion docs/code database | `database/scripts/check_doc_code_coherence.py`, `database/tests/test_verify_repo.py` | Partiel: controle existe, actuellement rouge sur un marqueur de gate. |
| Pipeline database e2e | `database` `pytest` global local, plus scripts de smoke/runbooks | Partiel: largement teste localement, mais smoke live manuel. |

### Gaps de tests classes P0 / P1 / P2

P0:
- Validation negative structurelle des payloads owner read cote `runtime-app`.
- Validation negative structurelle des enveloppes editoriales cote `runtime-app`.
- CI racine `runtime-app` pour web smoke, mobile smoke et `sessions:postgres`.
- CI cross-repo nominale `owner-http` via compose.

P1:
- Tests de migration tamper-detection cote `database`.
- Tests de rollback rehearsal / restore rehearsal sur les deux repos.
- Tests de rotation effective des cles operateur et owner token en environnement strict.

P2:
- Tests de charge avec seuils budgetises et assertions de p95/5xx.
- Tests de perf owner-side sous contention DB / limitation de connexions.
- Tests de non-regression sur dashboards/alerting (si configuration versionnee).

### 10 tests prioritaires a ajouter en premier

1. `runtime-app`: payload `playable_corpus.v1` avec seul tag de version -> doit etre rejete.
2. `runtime-app`: payload `pack.compiled.v1` incomplet -> doit etre rejete.
3. `runtime-app`: payload `pack.materialization.v1` incomplet -> doit etre rejete.
4. `runtime-app`: enveloppe `pack.create.v1` avec `operation_version` correct mais payload invalide -> rejet.
5. Cross-repo compose: `database-runtime-read` + `runtime-api` + `runtime-web` -> parcours `/play` nominal.
6. Cross-repo compose: `database-editorial-write` + `runtime-api` + web editorial -> parcours editorial nominal.
7. CI racine `runtime-app`: `pnpm --filter @runtime-app/api run test:sessions:postgres`.
8. `database`: test de checksum/tamper detection pour les migrations owner-side (apres implementation).
9. `database`: test de gouvernance documentaire aligne sur la nomenclature de gate valide actuelle.
10. `runtime-app/scripts/pilot-load-test.mjs`: mode seuils avec echec si `p95` ou `5xx` depassent un budget fixe.

### Flaky tests, causes probables, plan de stabilisation

Constat observe:
- Aucun test explicitement flaky n'a ete demontre dans les executions locales faites pour cet audit.

Risques de flakiness probables:
- smokes web Playwright reposant sur des dev servers demarres a la volee;
- tests Postgres dependent d'un DSN local/CI correctement provisionne;
- tests `database` longs (`pytest` complet ~8 minutes) avec logs volumineux des services owner et du parcours Gemini synthetique.

Plan de stabilisation:
1. executer les smokes web/mobile dans la CI sur environnements propres;
2. separer les suites lentes vs rapides avec timeouts explicites;
3. conserver fixtures synthetiques deterministes pour les chemins IA et owner HTTP;
4. versionner les preconditions navigateurs/base de donnees dans les workflows.

## Section F - Securite et exploitation

### Secrets, permissions, dependances, surfaces d'attaque

Etat conforme / positif:
- `database` dispose d'un secret scan bloqueur avec Gitleaks (`database/.github/workflows/secret-scan.yml`).
- `runtime-app` force des garde-fous d'environnement strict pour interdire `filesystem` et `mock` en `staging/pilot/production` (`runtime-app/apps/api/src/integrations/database/index.ts`).
- `runtime-app` exige `RUNTIME_DATABASE_URL` en environnement strict (`runtime-app/apps/api/src/storage/postgres.ts`).
- Les services owner `database` peuvent exiger un token partage `X-Owner-Service-Token`.

Risques / manques:
- Pas de secret scan equivalent dans `runtime-app`.
- Pas de scan de vulnerabilites dependances visible.
- Pas de SBOM ni provenance visible.
- Permissions GitHub/Fly/Vercel/Supabase non auditables.
- Auth operateur par cles statiques seulement, sans RBAC.

### Observabilite, alerting, runbooks, readiness incident

Etat conforme / positif:
- `runtime-app` expose `/metrics` avec compteurs owner read, soumissions session et latence HTTP.
- Les services owner `database` emettent des logs JSON de requete avec `status`, `error`, `latency_ms`.
- Des runbooks existent: `runtime-app/docs/20_execution/phase6_pilot_runbook.md`, `database/docs/security_incident_runbook.md`, `database/docs/04_smoke_runbook.md`.

Manques:
- pas de dashboards versionnes;
- pas d'alertes versionnees;
- pas de traces distribuees;
- pas de preuves de correlation multi-service en environnement reel;
- pas de preuves de drill incident/rollback executes.

### Plan de hardening 30 / 60 / 90 jours

30 jours:
- remettre `database` au vert sur `pytest + doc coherence + ruff`
- ajouter `runtime-app` secret scan bloqueur
- implementer validation structurelle forte des contrats owner-side dans `runtime-app`
- brancher web smoke, mobile smoke et `sessions:postgres` dans la CI `runtime-app`
- Resultats mesurables:
  - 0 gate rouge sur `database`
  - 100% des PR `runtime-app` scannees pour secrets
  - 100% des payloads owner-side invalides rejetes par tests negatifs

60 jours:
- ajouter CI cross-repo nominale `owner-http`
- ajouter audit dependances + SBOM
- ajouter checksums migration cote `database`
- versionner alertes et dashboard minimum (5xx, owner_timeout, p95)
- documenter et prouver une rotation de cles operateur/owner
- Resultats mesurables:
  - 1 pipeline E2E cross-repo verte par merge
  - 1 SBOM par build de release
  - 1 preuve de rotation de secrets par environnement

90 jours:
- mettre en place authn/authz operateur fondee sur identites/RBAC
- formaliser rollback drill et restore drill
- ajouter provenance artefacts / signing
- definir budgets de perf et fiabilite applicables
- Resultats mesurables:
  - 1 drill rollback/restore execute et documente
  - 1 modele d'acces operateur role-based deploye
  - 1 tableau de bord SLO avec alertes reliees aux budgets

## Section G - Performance et cout

### Goulots d'etranglement probables et preuves

1. Owner services `database` synchrones et threades, sans preuve de pooling de connexions applicatif
- Preuve: `database/src/database_core/runtime_read/http_server.py` utilise `ThreadingHTTPServer`; `database/src/database_core/storage/postgres.py` ouvre une connexion `psycopg.connect(...)` dans `connect()`.
- Risque: contention DB et cout CPU/latence sous charge.

2. Mesure de latence runtime non persistante
- Preuve: `runtime-app/apps/api/src/observability/metrics.ts` calcule `p50/p95` en memoire a partir d'echantillons du processus.
- Risque: redemarrage = perte de contexte; utile pour debug local, insuffisant comme base unique de pilotage production.

3. Charge pilote documentee mais non gatee
- Preuve: `runtime-app/scripts/pilot-load-test.mjs` sait lancer `100` learners concurrents et sortir un resume, sans seuils d'echec codifies.
- Risque: le test produit un rapport, pas une decision automatique.

4. Non-auditabilite du cout reel
- Preuve manquante: aucune metrique live de cout API, cout DB, cout web, slow queries, saturation CPU/RAM, nb de connexions, ou budget Gemini n'a ete fournie.

### Opportunites d'optimisation a faible risque

1. Ajouter un budget et un mode `--fail-on-threshold` au load test `runtime-app/scripts/pilot-load-test.mjs`.
2. Ajouter un pooling explicite ou un proxy de connexions owner-side avant toute montee en charge.
3. Mesurer et paginer/borner explicitement les lectures `playable_corpus` si le volume depasse le limiteur actuel.
4. Ajouter `EXPLAIN ANALYZE` cible sur les lectures owner-side frequentes et les index Geo/temps deja presents.

### Plan de mesure: metriques, seuils, protocole de benchmark

Metriques minimales a relever:
- `runtime_http_requests_total` par endpoint et famille de status
- `runtime_http_request_latency_ms` p50/p95 par endpoint
- `runtime_owner_read_failures_total` par type (`owner_timeout`, `owner_http_error`, etc.)
- p95 `startSession`, `getQuestion`, `submitAnswer`
- nb de connexions DB owner + runtime
- 5xx et timeouts owner-side
- cout/volume Gemini cote `database` sur qualification live

Seuils recommandes de depart:
- p95 runtime API <= 800 ms sur les endpoints critiques
- 0 erreur structurelle de contrat owner-side
- 0 `owner_timeout` sur smoke nominal
- 0 5xx sur `sessions/*`, `/institutional/*`, `/editorial/*` pendant le load test pilote

Protocole:
1. monter la stack composee cross-repo nominale
2. executer `node scripts/pilot-load-test.mjs` avec 100 learners
3. collecter `/metrics` runtime + logs JSON owner + `EXPLAIN ANALYZE` des requetes clefs
4. consigner les seuils, ecarts et capacite max atteinte dans un rapport versionne

## Section H - Plan d'action executable

| Priorite | Item | Resultat attendu | Modules / fichiers touches | Risque de regression | Validation | Estimation | Owner recommande |
|---|---|---|---|---|---|---|---|
| P0 | Remettre `database` verification au vert | `pytest`, doc coherence et Ruff verts | `database/docs/codex_execution_plan.md`, `database/tests/test_verify_repo.py`, scripts/tests phase3.x | Faible a moyen | `./.venv/bin/python scripts/verify_repo.py` | S | Data engineering |
| P0 | Validation forte des contrats owner-side | Rejet explicite de tout payload structurellement invalide | `runtime-app/packages/contracts`, `runtime-app/apps/api/src/integrations/database/*` | Moyen | `pnpm --filter @runtime-app/api run test:all` + nouveaux tests negatifs | M | Runtime backend |
| P0 | Secret scan bloqueur `runtime-app` | PR bloquees sur secret leak | `runtime-app/.github/workflows/*` | Faible | CI verte + test de secret leak synthetique | S | DevSecOps |
| P0 | Brancher smokes web/mobile + sessions Postgres en CI | Regression UX/persistance detectee automatiquement | `runtime-app/.github/workflows/ci.yml` | Moyen | CI verte sur `web test:smoke`, `mobile test:smoke`, `test:sessions:postgres` | S | Runtime backend + frontend |
| P0 | Ajouter E2E cross-repo nominal `owner-http` | Validation reelle des interfaces combinees | `runtime-app/infra/docker-compose.yml`, workflow CI cross-repo, scripts smoke | Moyen | pipeline composee verte | M | Runtime backend + data engineering |
| P1 | Verrouiller la reproductibilite Python `database` | Resolution deps deterministe | `database/pyproject.toml`, constraints/lock, workflow CI | Faible | install reproduisible en CI et local | S | Data engineering |
| P1 | Ajouter checksums migration `database` + politique rollback | Auditabilite et reprise DB renforcees | `database/src/database_core/storage/postgres_migrations.py`, docs rollback | Moyen | test tamper-detection + drill documente | M | Data engineering + SRE |
| P1 | Versionner alertes/dashboards minimum | Exploitation moins manuelle | artefacts observabilite a creer dans `runtime-app` et docs associees | Faible | simulation incident + alertes visibles | M | SRE |
| P1 | Durcir auth operateur/owner | Reduction du risque d'acces non autorise | `runtime-app/apps/api/src/security/*`, `database` owner services, docs deploiement | Moyen | tests authn/authz + rotation prouvee | L | Security + backend |
| P2 | Ajouter SBOM/provenance/signing | Supply chain auditable de bout en bout | CI/CD des deux repos | Faible | SBOM genere et archive a chaque release | M | DevSecOps |
| P2 | Budget perf et charge gatee | Decision de capacite objectivable | `runtime-app/scripts/pilot-load-test.mjs`, observabilite, docs runbook | Faible a moyen | load test avec seuils d'echec | M | SRE + runtime backend |

## Section I - Annexes

### Commandes executees

Commandes de validation executees pendant l'audit:
- `cd /Users/ryelandt/Documents/runtime-app && pnpm run check`
- `cd /Users/ryelandt/Documents/runtime-app && pnpm --filter @runtime-app/api run test:all`
- `cd /Users/ryelandt/Documents/runtime-app && pnpm --filter @runtime-app/mobile run test:smoke`
- `cd /Users/ryelandt/Documents/runtime-app && pnpm --filter @runtime-app/web run test:smoke`
- `cd /Users/ryelandt/Documents/database && export DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' .env)" && ./.venv/bin/python scripts/verify_repo.py`
- `cd /Users/ryelandt/Documents/database && ./.venv/bin/python scripts/check_doc_code_coherence.py`
- `cd /Users/ryelandt/Documents/database && ./.venv/bin/python -m ruff check src tests scripts`
- `cd /Users/ryelandt/Documents/runtime-app && find .github -maxdepth 2 -type f | sort && grep -RniE 'gitleaks|secret-scan|audit|sbom|cyclonedx|snyk|dependabot' .github package.json apps packages infra docs || true`
- `cd /Users/ryelandt/Documents/database && find .github -maxdepth 2 -type f | sort && grep -RniE 'gitleaks|secret-scan|audit|sbom|cyclonedx|snyk|dependabot|pip-audit|safety' .github pyproject.toml README.md docs scripts src || true`

Resultats saillants observes:
- `runtime-app`:
  - `pnpm run check`: succes
  - `pnpm --filter @runtime-app/api run test:all`: succes
  - web smokes: `3 passed (14.7s)`
  - mobile smoke: `3 passed`
- `database`:
  - `scripts/check_doc_code_coherence.py`: succes
  - `pytest -q -p no:capture` via `verify_repo`: `1 failed, 165 passed`
  - `ruff check src tests scripts`: `Found 46 errors`

### Limites de l'audit

- Audit limite aux artefacts lisibles et aux validations locales executables depuis les deux repos.
- Aucune conclusion n'est tiree sur les reglages GitHub/Fly/Vercel/Supabase non fournis.
- Aucune conclusion n'est tiree sur la fiabilite live sans logs/metriques/traces reels.
- Aucun scan de vulnerabilites externe n'a ete invente ni simule.

### Hypotheses restantes a valider

- Que les docs de deploiement correspondent bien aux reglages effectifs des environnements de staging/pilot/production.
- Que les branches `main` des deux repos sont protegees avec revues obligatoires et statuts requis.
- Que les services owner sont bien prives en environnement reel.
- Que les rotations de cles operateur et owner token sont executees et auditees.

### Donnees manquantes demandees pour fermer les risques

1. Export ou preuve des protections GitHub (branch protection, required checks, environments, reviewers).
2. Preuves Fly/Vercel de reseau prive, secrets actifs, historique de rotation et access policies.
3. Toute configuration Supabase pertinente, ou preuve explicite que Supabase n'est pas dans le chemin de prod.
4. Dashboards/alertes/traces et logs reels sur une fenetre representative.
5. Preuve de backup/restore drill et rollback drill executes.
6. Eventuels rapports de dependabot/SCA/SBOM si deja produits hors repo.
