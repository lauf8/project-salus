import json

import pytest
from pydantic import ValidationError

from app.core.knowledge_identity import document_key, passage_key
from app.schemas.knowledge_transfer import PublicKnowledgeBundle
from scripts.knowledge import SEED_PATH, load_bundle


def test_seed_has_stable_identities_and_requested_tags():
    bundle = load_bundle(SEED_PATH)
    assert len(bundle.documents) == 7
    tags = set()
    for document in bundle.documents:
        assert document.stable_id == document_key(str(document.source_url), document.revision)
        assert document.source_url.host.endswith("nasa.gov")
        for passage in document.passages:
            assert passage.stable_id == passage_key(document.stable_id, passage.section)
            tags.update(passage.topic_codes)
    assert {
        "headache", "cabin_co2", "blurred_vision", "vision_changes", "preflight_screening",
        "preventive_care", "in_flight_medical_care", "space_motion_sickness", "back_pain",
        "eva_dehydration", "sleep_quality", "fatigue", "circadian_rhythm", "cabin_noise",
        "exercise", "physical_performance", "nutrition",
    }.issubset(tags)
    assert PublicKnowledgeBundle.model_validate_json(bundle.model_dump_json()) == bundle


@pytest.mark.parametrize("change", ["duplicate_document", "duplicate_passage", "duplicate_section", "private_field", "wrong_version", "invalid_page"])
def test_invalid_transfer_bundle_is_rejected(change):
    bundle = json.loads(SEED_PATH.read_text())
    if change == "duplicate_document":
        bundle["documents"].append(bundle["documents"][0])
    elif change == "duplicate_passage":
        bundle["documents"][1]["passages"][0]["stable_id"] = bundle["documents"][0]["passages"][0]["stable_id"]
    elif change == "duplicate_section":
        passage = dict(bundle["documents"][0]["passages"][0], stable_id="fictional-other")
        bundle["documents"][0]["passages"].append(passage)
    elif change == "private_field":
        bundle["documents"][0]["patients"] = [{"name": "Fictional patient"}]
    elif change == "wrong_version":
        bundle["format_version"] = 2
    else:
        bundle["documents"][0]["passages"][0]["page_number"] = 0
    with pytest.raises(ValidationError):
        PublicKnowledgeBundle.model_validate(bundle)
