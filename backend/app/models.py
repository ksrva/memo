from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class DOMElement(BaseModel):
    role: str
    text: str
    selector: str


class UserEvent(BaseModel):
    type: str
    text: str
    ts: int


class ComposeRequest(BaseModel):
    url: str
    title: str
    main_text: str
    selection: Optional[str] = ""
    dom_map: List[DOMElement] = []
    recent_events: List[UserEvent] = []
    goal: Optional[str] = "Create a structured memo"


class SalientSection(BaseModel):
    text: str
    score: float


class Memory(BaseModel):
    id: str
    text: str
    why: str
    score: float = 0.0


class ContextBundle(BaseModel):
    summary_hint: str
    entities_hint: List[str]
    salient_sections: List[SalientSection]
    memories: List[Memory] = []


class ComposeResponse(BaseModel):
    context_bundle: ContextBundle


class SummarizeRequest(BaseModel):
    context_bundle: ContextBundle
    goal: Optional[str] = "Create a structured memo"


class SummarizeResponse(BaseModel):
    summary: str
    entities: List[str]
    tasks: List[str]
    risks: List[str]
    markdown: str


class MemoryUpsertRequest(BaseModel):
    url: str
    title: str
    text: str
    tags: List[str] = []
    ts: Optional[int] = None
    metadata: Dict[str, Any] = {}


class MemoryUpsertResponse(BaseModel):
    id: str


class MemorySearchResponse(BaseModel):
    hits: List[Memory]


class MetricsResponse(BaseModel):
    latency_p95: float
    token_usage_total: int
    success_rate: float
    memory_recall_rate: float