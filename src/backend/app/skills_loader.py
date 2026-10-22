# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT

SKILLS_DIR = REPO_ROOT / "skills"


@dataclass(frozen=True)
class SkillDoc:
    name: str
    body: str
    references: tuple[tuple[str, str], ...]

    def prompt_block(self) -> str:
        parts = [f"# SKILL.md ({self.name})\n\n{self.body.strip()}"]
        for filename, text in self.references:
            parts.append(f"# references/{filename}\n\n{text.strip()}")
        return "\n\n".join(parts)


def load_skill(name: str) -> SkillDoc:
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"Skill 不存在: {name}")
    refs: list[tuple[str, str]] = []
    refdir = path.parent / "references"
    if refdir.is_dir():
        for item in sorted(refdir.glob("*.md")):
            refs.append((item.name, item.read_text(encoding="utf-8")))
    return SkillDoc(name=name, body=path.read_text(encoding="utf-8"), references=tuple(refs))


def load_skills(names: list[str]) -> list[SkillDoc]:
    return [load_skill(name) for name in names]