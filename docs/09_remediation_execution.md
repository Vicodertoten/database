# Directive De Remédiation En Exécution

Document de pilotage opérationnel lié à l’audit (`docs/05_audit_reference.md`) et à la charte canonique (`docs/06_charte_canonique_v1.md`).

## Directive active

Implémenter une gouvernance canonique réellement opérable:
- transitions déterministes appliquées automatiquement (`auto_clear`),
- transitions ambiguës routées explicitement vers revue opérateur (`manual_reviewed`),
- traçabilité immuable par run.

## Tranche en cours

Objectif: fermer le gap "structure présente" -> "gouvernance exécutable" sans casser la reproductibilité pipeline.

Livrables visés:
1. moteur de décisions canoniques basé sur état précédent vs état courant,
2. file de revue canonique dédiée pour transitions ambiguës,
3. inspectabilité opérateur de cette file,
4. tests ciblés sur règles ambiguës et transitions déterministes,
5. gestion explicite des conflits de mapping multi-sources (priorité claire sinon review).

## Règles de travail

1. Toute évolution doit être reliée à un risque explicite de `docs/05_audit_reference.md`.
2. Toute règle automatique doit avoir un test de non-régression.
3. Aucun changement de gouvernance sans trace persistée (event + reason + status).
