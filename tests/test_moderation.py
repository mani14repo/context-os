import uuid

import pytest

from contextos import ContextOS
from contextos.moderation import KeywordModerator


@pytest.mark.asyncio
async def test_keyword_moderator_flags_content_containing_a_blocked_term() -> None:
    moderator = KeywordModerator(["Project Phoenix"])
    result = await moderator.moderate("The launch date for Project Phoenix is confidential.")
    assert result.flagged is True
    assert result.categories == ["project phoenix"]


@pytest.mark.asyncio
async def test_keyword_moderator_is_case_insensitive() -> None:
    moderator = KeywordModerator(["project phoenix"])
    result = await moderator.moderate("PROJECT PHOENIX ships next quarter.")
    assert result.flagged is True


@pytest.mark.asyncio
async def test_keyword_moderator_does_not_flag_clean_content() -> None:
    moderator = KeywordModerator(["Project Phoenix"])
    result = await moderator.moderate("The quarterly report is ready for review.")
    assert result.flagged is False
    assert result.categories == []


@pytest.mark.asyncio
async def test_keyword_moderator_reports_every_matched_term() -> None:
    moderator = KeywordModerator(["Project Phoenix", "Acme Corp"])
    result = await moderator.moderate("Project Phoenix is a joint venture with Acme Corp.")
    assert result.flagged is True
    assert set(result.categories) == {"project phoenix", "acme corp"}


@pytest.mark.asyncio
async def test_context_os_moderate_delegates_to_configured_moderator() -> None:
    os = ContextOS(moderator=KeywordModerator(["Project Phoenix"]))
    result = await os.moderate("Mentions Project Phoenix by name.")
    assert result.flagged is True


@pytest.mark.asyncio
async def test_context_os_moderate_raises_without_a_configured_moderator() -> None:
    os = ContextOS()
    with pytest.raises(RuntimeError):
        await os.moderate("anything")


@pytest.mark.asyncio
async def test_context_os_without_moderator_is_unaffected_by_other_operations() -> None:
    # Sanity check that adding the moderator param didn't break unrelated facade calls.
    os = ContextOS()
    with pytest.raises(KeyError):
        await os.record_feedback("t1", uuid.uuid4(), helpful=True)
