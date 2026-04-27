from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ACTIVE_DIRS = [DOCS / "foundation", DOCS / "runbooks"]
ALLOWED_STATUS = {"planned", "in_progress", "blocked", "ready_for_validation", "stable"}
REQUIRED_KEYS = {"owner", "status", "last_reviewed", "source_of_truth", "scope"}


@dataclass
class FrontMatter:
    data: dict[str, str]


def parse_front_matter(path: Path) -> FrontMatter | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    block = text[4:end]
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip()
    return FrontMatter(data=data)


def main() -> int:
    issues: list[str] = []

    for ds in DOCS.rglob(".DS_Store"):
        issues.append(f"forbidden file: {ds.relative_to(ROOT)}")

    active_files: list[Path] = []
    for active_dir in ACTIVE_DIRS:
        active_files.extend(sorted(active_dir.rglob("*.md")))

    for path in active_files:
        fm = parse_front_matter(path)
        rel = path.relative_to(ROOT)
        if fm is None:
            issues.append(f"missing front matter: {rel}")
            continue
        missing = REQUIRED_KEYS - set(fm.data)
        if missing:
            issues.append(f"front matter missing keys {sorted(missing)}: {rel}")
        status = fm.data.get("status", "")
        if status not in ALLOWED_STATUS:
            issues.append(f"invalid status '{status}' in {rel}")

    chantier_dir = DOCS / "runbooks" / "inter-repo" / "chantiers"
    for path in sorted(chantier_dir.glob("INT-*.md")):
        fm = parse_front_matter(path)
        if fm is None:
            issues.append(f"missing front matter: {path.relative_to(ROOT)}")
            continue
        status = fm.data.get("status", "")
        if status == "closed" or status.startswith("closed"):
            issues.append(f"closed chantier must be archived: {path.relative_to(ROOT)}")

    legacy_execution = DOCS / "20_execution"
    allowed = {legacy_execution / "README.md"}
    if legacy_execution.exists():
        for path in legacy_execution.rglob("*"):
            if path.is_file() and path not in allowed:
                issues.append(
                    f"docs/20_execution must be pointer-only; unexpected file {path.relative_to(ROOT)}"
                )

    for path in sorted((DOCS / "archive" / "evidence").rglob("*")):
        if not path.is_dir():
            continue
        name = path.name
        if name.startswith("phase") and re.search(r"_", name):
            issues.append(f"phase naming should be kebab-case in archive paths: {path.relative_to(ROOT)}")

    if issues:
        for issue in issues:
            print(f"[docs-hygiene] {issue}")
        return 1

    print("Docs hygiene checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
