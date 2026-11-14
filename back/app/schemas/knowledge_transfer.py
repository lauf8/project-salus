from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


StableId = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
NonemptyText = Annotated[str, Field(min_length=1)]


class PublicPassage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stable_id: StableId
    section: NonemptyText
    page_number: int | None = Field(default=None, ge=1)
    content: NonemptyText
    topic_codes: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]]


class PublicDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stable_id: StableId
    title: NonemptyText
    source_url: HttpUrl
    revision: NonemptyText
    document_type: Literal["technical_standard", "technical_brief", "evidence_report", "risk_summary", "reference"]
    imported_at: AwareDatetime | None = None
    passages: list[PublicPassage]


class PublicKnowledgeBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = 1
    documents: list[PublicDocument]

    @model_validator(mode="after")
    def unique_identities(self) -> Self:
        document_ids = [document.stable_id for document in self.documents]
        identities = [(str(document.source_url), document.revision) for document in self.documents]
        passage_ids = [passage.stable_id for document in self.documents for passage in document.passages]
        if len(set(document_ids)) != len(document_ids) or len(set(identities)) != len(identities):
            raise ValueError("Duplicate document identity")
        if len(set(passage_ids)) != len(passage_ids):
            raise ValueError("Duplicate passage identity")
        for document in self.documents:
            sections = [passage.section for passage in document.passages]
            if len(set(sections)) != len(sections):
                raise ValueError("Duplicate section in document")
        return self
