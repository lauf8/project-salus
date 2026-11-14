import asyncio
import json
from unittest.mock import Mock

import pytest

from app.providers.ai import AiInvalidResponseError
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge import ReferenceExcerpt
from app.services.assessment_service import AssessmentService


EXCERPT = ReferenceExcerpt(
    source_id="nasa:1", title="Fictional reference", source_url="https://example.test",
    revision="Fictional revision", section="Fictional section", page_number=1,
    content="Fictional reference context",
)


class FakeProvider:
    def __init__(self, source_ids, symptom="headache"):
        self.source_ids = source_ids
        self.symptom = symptom
        self.context = None
        self.instructions = None

    async def generate(self, instructions, context):
        self.instructions = instructions
        self.context = json.loads(context)
        return json.dumps({
            "symptom": self.symptom, "activity_context": None, "source_ids": self.source_ids,
        })


def test_no_codes_does_not_query_database():
    session = Mock()
    assert KnowledgeRepository(session).find_by_symptom_codes([]) == []
    session.exec.assert_not_called()


def test_confirmed_codes_supply_references():
    repository = Mock()
    repository.find_by_symptom_codes.return_value = [EXCERPT]
    provider = FakeProvider(["nasa:1"])
    result = asyncio.run(AssessmentService(provider, "Fictional instructions", repository).extract(
        "Fictional headache report", ["headache"]
    ))
    assert result.source_ids == ["nasa:1"]
    repository.find_by_symptom_codes.assert_called_once_with(["headache"])
    assert provider.context["reference_excerpts"] == [EXCERPT.model_dump()]
    assert "mission protocol" in provider.instructions


@pytest.mark.parametrize("codes", [None, []])
def test_unconfirmed_report_does_not_retrieve(codes):
    repository = Mock()
    provider = FakeProvider([])
    asyncio.run(AssessmentService(provider, "Fictional instructions", repository).extract(
        "Fictional headache report", codes
    ))
    repository.find_by_symptom_codes.assert_not_called()
    assert provider.context["reference_excerpts"] == []


@pytest.mark.parametrize("source_ids,symptom", [
    (["nasa:999"], "headache"), (["nasa:1"], "headache"),
    ([], "Fictional headache [nasa:999]"), (["record:1"], "headache"),
])
def test_unsent_references_are_rejected(source_ids, symptom):
    provider = FakeProvider(source_ids, symptom)
    with pytest.raises(AiInvalidResponseError):
        asyncio.run(AssessmentService(provider, "Fictional instructions").extract("Fictional report"))


def test_reference_from_another_call_is_rejected():
    repository = Mock()
    repository.find_by_symptom_codes.return_value = [EXCERPT]
    provider = FakeProvider(["nasa:1"])
    service = AssessmentService(provider, "Fictional instructions", repository)
    asyncio.run(service.extract("Fictional report", ["headache"]))
    with pytest.raises(AiInvalidResponseError):
        asyncio.run(service.extract("Another fictional report", []))
