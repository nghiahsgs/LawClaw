"""Legislative branch — loads constitution and laws from markdown files."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


class LegislativeBranch:
    """Reads constitution + laws + skills playbooks. Injected into the agent's system prompt
    so the LLM self-regulates (like citizen consciousness)."""

    def __init__(self, constitution_path: Path, laws_dir: Path, skills_dir: Path | None = None) -> None:
        self._constitution_path = constitution_path
        self._laws_dir = laws_dir
        self._skills_dir = skills_dir

    def load_constitution(self) -> str:
        """Read the constitution file."""
        try:
            return self._constitution_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.error("Could not read constitution at {}: {}", self._constitution_path, exc)
            return ""

    def load_laws(self) -> str:
        """Concatenate all .md files in the laws directory."""
        if not self._laws_dir.exists():
            return ""
        parts: list[str] = []
        for md_file in sorted(self._laws_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
            except OSError as exc:
                logger.warning("Could not read law file {}: {}", md_file, exc)
        return "\n\n---\n\n".join(parts)

    def load_skills(self) -> str:
        """Concatenate all .md playbooks in the skills directory."""
        if not self._skills_dir or not self._skills_dir.exists():
            return ""
        parts: list[str] = []
        for md_file in sorted(self._skills_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
            except OSError as exc:
                logger.warning("Could not read skill playbook {}: {}", md_file, exc)
        return "\n\n---\n\n".join(parts)
