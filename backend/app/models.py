"""Data models for Memo.

The central unit is a Note: a passage the reader highlighted plus, crucially,
what the reader thought about it. The reader's words are required — the machine
is allowed to describe the source, never to supply the opinion.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone


RelationKind = Literal["agrees", "contradicts", "extends", "example_of", "related"]


class NoteCreate(BaseModel):
    """What the extension sends when the reader saves a highlight."""

    url: str
    title: str
    passage: str = Field(
        default="",
        description="The text the reader highlighted. May be empty when noting a whole article.",
    )
    note: str = Field(
        min_length=1,
        description="The reader's own words. Required — this is the irreplaceable half.",
    )
    tags: List[str] = []

    @field_validator("note")
    @classmethod
    def note_must_have_substance(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("A note needs your own words — that is the point of the tool.")
        return cleaned

    @field_validator("passage", "title")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class Enrichment(BaseModel):
    """The machine's contribution: it describes the source, it does not opine."""

    claim: str = Field(default="", description="One sentence: what the passage argues.")
    open_question: str = Field(default="", description="A question the passage leaves open.")
    tags: List[str] = []


class Link(BaseModel):
    """A connection between this note and an earlier one."""

    note_id: str
    title: str
    url: str
    note: str = Field(description="The earlier note's text, truncated for display.")
    relation: RelationKind = "related"
    score: float = 0.0
    why: str = ""


class Note(BaseModel):
    id: str
    url: str
    title: str
    passage: str
    note: str
    claim: str = ""
    open_question: str = ""
    tags: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    links: List[Link] = []

    def as_markdown(self) -> str:
        parts = [f"# {self.title}", "", f"<{self.url}>", ""]
        if self.passage:
            parts += ["> " + self.passage.replace("\n", "\n> "), ""]
        parts += ["**My take:** " + self.note, ""]
        if self.claim:
            parts += [f"*Claim:* {self.claim}", ""]
        if self.open_question:
            parts += [f"*Open question:* {self.open_question}", ""]
        if self.tags:
            parts += ["*Tags:* " + ", ".join(self.tags), ""]
        if self.links:
            parts.append("*Connects to:*")
            parts += [f"- ({l.relation}) [{l.title}]({l.url}) — {l.note[:80]}" for l in self.links]
        return "\n".join(parts)


class SearchHit(BaseModel):
    note: Note
    score: float
    matched_on: Literal["note", "passage"] = "note"


class SearchResponse(BaseModel):
    query: str
    mode: Literal["semantic", "keyword"] = "semantic"
    hits: List[SearchHit] = []


class RelatedRequest(BaseModel):
    """Ask what prior reading bears on the page currently open."""

    url: str
    title: str = ""
    text: str = Field(default="", description="Page text, or the passage being read.")


class RelatedResponse(BaseModel):
    hits: List[Link] = []
