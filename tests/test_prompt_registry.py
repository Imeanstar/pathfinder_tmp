"""프롬프트 버전관리 레지스트리 — 서비스 고도화(2026-08-24).

지금까지 프롬프트는 각 모듈(app/llm.py, app/agents/chat.py) 안에 그냥 Python 문자열
상수였다 — git 커밋 이력으로만 "언제 바뀌었나"를 알 수 있고, "이 버전이 왜 바뀌었는지"를
프롬프트 단위로 남기는 장치가 없었다. app/prompts/*.yaml로 옮기면서 각 프롬프트가
명시적인 version·changelog를 갖게 했다. 이 테스트는 (1) 레지스트리가 정상 동작하는지,
(2) 등록된 모든 프롬프트가 필수 필드(name·version·updated·changelog·template)를
갖췄는지, (3) changelog 마지막 항목이 현재 version을 언급하는지(버전을 올릴 때
changelog도 같이 남기라는 강제) 검증한다.
"""
import re

import pytest

from app.prompts import get_prompt, get_prompt_record, get_prompt_version, list_prompts


def test_list_prompts_returns_all_four_registered_prompts():
    assert set(list_prompts()) == {
        "chat_system",
        "chat_query_rewrite",
        "transcript_extraction",
        "recommendation_reason",
    }


def test_get_prompt_returns_nonempty_template_string():
    template = get_prompt("chat_system")
    assert isinstance(template, str)
    assert len(template) > 0


def test_get_prompt_version_returns_positive_int():
    assert get_prompt_version("chat_system") >= 1


def test_get_prompt_raises_for_unknown_name():
    with pytest.raises(FileNotFoundError):
        get_prompt("이런_프롬프트는_없음")


@pytest.mark.parametrize("name", list_prompts())
def test_every_prompt_has_required_fields(name):
    record = get_prompt_record(name)
    assert record.name == name
    assert isinstance(record.version, int) and record.version >= 1
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", record.updated), "updated는 YYYY-MM-DD 형식이어야 함"
    assert record.changelog, "changelog가 비어있으면 안 됨"
    assert record.template.strip(), "template이 비어있으면 안 됨"


@pytest.mark.parametrize("name", list_prompts())
def test_changelog_latest_entry_mentions_current_version(name):
    """버전을 올렸는데 changelog에 그 버전 항목을 안 남기는 실수를 막는다 —
    프롬프트를 고칠 때마다 반드시 "vN (날짜): 무엇을 왜"를 changelog 맨 끝에
    추가해야 한다는 걸 테스트로 강제한다."""
    record = get_prompt_record(name)
    latest_entry = record.changelog[-1]
    assert f"v{record.version}" in latest_entry, (
        f"{name}.yaml: version={record.version}인데 changelog 마지막 항목에 "
        f"'v{record.version}'이 없음 — {latest_entry!r}"
    )
