from pydantic import BaseModel


class ReferenceExcerpt(BaseModel):
    source_id: str
    title: str
    source_url: str
    revision: str
    section: str
    page_number: int | None
    content: str
