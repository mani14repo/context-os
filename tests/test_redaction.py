import pytest

from contextos import Classification, ContextNode, ContextOS, MemoryType
from contextos.redaction import RegexRedactor


@pytest.mark.asyncio
async def test_redacts_email() -> None:
    redactor = RegexRedactor()
    result = await redactor.redact("Contact jane.doe@example.com for details.")
    assert "jane.doe@example.com" not in result
    assert "[REDACTED:EMAIL]" in result


@pytest.mark.asyncio
async def test_redacts_ssn() -> None:
    redactor = RegexRedactor()
    result = await redactor.redact("SSN on file: 123-45-6789.")
    assert "123-45-6789" not in result
    assert "[REDACTED:SSN]" in result


@pytest.mark.asyncio
async def test_redacts_phone_number() -> None:
    redactor = RegexRedactor()
    result = await redactor.redact("Call 555-123-4567 for support.")
    assert "555-123-4567" not in result
    assert "[REDACTED:PHONE]" in result


@pytest.mark.asyncio
async def test_redacts_credit_card_without_mangling_surrounding_text() -> None:
    redactor = RegexRedactor()
    result = await redactor.redact("Card number 4111 1111 1111 1111 was charged.")
    assert "4111 1111 1111 1111" not in result
    assert result == "Card number [REDACTED:CREDIT_CARD] was charged."


@pytest.mark.asyncio
async def test_leaves_non_pii_text_unchanged() -> None:
    redactor = RegexRedactor()
    text = "The disaster recovery cutover is triggered manually by the on-call engineer."
    assert await redactor.redact(text) == text


@pytest.mark.asyncio
async def test_contextos_redact_uses_default_regex_redactor() -> None:
    context_os = ContextOS()
    result = await context_os.redact("Email me at test@example.com")
    assert "[REDACTED:EMAIL]" in result


@pytest.mark.asyncio
async def test_contextos_accepts_custom_redactor() -> None:
    class UppercaseRedactor:
        async def redact(self, content: str) -> str:
            return content.upper()

    context_os = ContextOS(redactor=UppercaseRedactor())
    assert await context_os.redact("hello") == "HELLO"


def test_classification_defaults_to_internal() -> None:
    node = ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    assert node.classification is Classification.INTERNAL


def test_classification_is_settable() -> None:
    node = ContextNode(
        tenant_id="t1",
        node_type="fact",
        memory_type=MemoryType.SEMANTIC,
        classification=Classification.RESTRICTED,
    )
    assert node.classification is Classification.RESTRICTED
