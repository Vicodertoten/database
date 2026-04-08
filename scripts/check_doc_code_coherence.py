from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOC_PATH = ROOT / "docs" / "05_audit_reference.md"
README_PATH = ROOT / "README.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "verify-repo.yml"
VERSIONING_PATH = ROOT / "src" / "database_core" / "versioning.py"


def main() -> int:
    issues: list[str] = []

    audit_doc = AUDIT_DOC_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    versioning = VERSIONING_PATH.read_text(encoding="utf-8")

    version_tokens = _extract_version_tokens(versioning)
    for token in (
        version_tokens["SCHEMA_VERSION_LABEL"],
        version_tokens["EXPORT_VERSION"],
        version_tokens["LEGACY_EXPORT_VERSION"],
        version_tokens["REVIEW_OVERRIDE_VERSION"],
    ):
        if token not in audit_doc:
            issues.append(f"docs/05 is missing version token: {token}")

    for name, token in version_tokens.items():
        if token not in readme:
            issues.append(f"README is missing version token {name}: {token}")

    if "schemas/qualified_resources_bundle_v4.schema.json" not in readme:
        issues.append("README must reference schemas/qualified_resources_bundle_v4.schema.json")
    if "schemas/qualified_resources_bundle_v3.schema.json" not in readme:
        issues.append(
            "README must reference sidecar schemas/qualified_resources_bundle_v3.schema.json"
        )
    if "database-migrate" not in readme:
        issues.append("README must document the database-migrate entrypoint")

    if WORKFLOW_PATH.exists() and "absence de ci visible" in audit_doc.lower():
        issues.append("docs/05 still claims CI is not visible while workflow file exists")

    if "État réel" not in audit_doc:
        issues.append("docs/05 must contain an explicit 'État réel' section")
    if "Cible" not in audit_doc:
        issues.append("docs/05 must contain an explicit 'Cible' section")

    if issues:
        for issue in issues:
            print(f"[doc-code-coherence] {issue}")
        return 1
    print("Doc/code coherence checks passed")
    return 0


def _extract_version_tokens(versioning_content: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for key in (
        "SCHEMA_VERSION_LABEL",
        "SNAPSHOT_MANIFEST_VERSION",
        "NORMALIZED_SNAPSHOT_VERSION",
        "ENRICHMENT_VERSION",
        "QUALIFICATION_VERSION",
        "EXPORT_VERSION",
        "LEGACY_EXPORT_VERSION",
        "REVIEW_OVERRIDE_VERSION",
    ):
        match = re.search(rf'^{key}\s*=\s*"([^"]+)"', versioning_content, flags=re.MULTILINE)
        if match:
            tokens[key] = match.group(1)
        else:
            raise RuntimeError(f"Missing version token in versioning.py: {key}")
    return tokens


if __name__ == "__main__":
    raise SystemExit(main())
