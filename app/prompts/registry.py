"""프롬프트 버전관리 레지스트리 — 서비스 고도화(2026-08-24).

지금까지 프롬프트는 각 모듈(app/llm.py, app/agents/chat.py) 안에 Python 문자열
상수로 박혀 있었다. git 커밋 이력으로 "코드가 언제 바뀌었나"는 알 수 있지만,
"이 프롬프트가 왜 이렇게 바뀌었나"를 프롬프트 단위로 남기는 장치는 없었다.

이 모듈은 app/prompts/*.yaml 하나하나를 명시적인 version·changelog가 붙은
레코드로 취급한다. 프롬프트를 바꾸려면 반드시 (1) template을 고치고 (2) version을
올리고 (3) changelog 맨 끝에 "vN (날짜): 무엇을 왜" 항목을 추가해야 한다 —
tests/test_prompt_registry.py가 이 세 가지 중 (2)(3)을 놓치면 실패로 잡는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PromptRecord:
    name: str
    version: int
    updated: str
    changelog: list[str]
    template: str


@lru_cache(maxsize=None)
def get_prompt_record(name: str) -> PromptRecord:
    path = PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"등록된 프롬프트가 아님: {name} ({path})")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PromptRecord(
        name=data["name"],
        version=data["version"],
        updated=data["updated"],
        changelog=data["changelog"],
        template=data["template"],
    )


def get_prompt(name: str) -> str:
    """최신 버전의 프롬프트 템플릿 문자열을 돌려준다. 호출부는 그대로 .format(...)."""
    return get_prompt_record(name).template


def get_prompt_version(name: str) -> int:
    return get_prompt_record(name).version


def list_prompts() -> list[str]:
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.yaml"))
