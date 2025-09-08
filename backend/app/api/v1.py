from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
import time
from datetime import datetime
from ..models import (
    ComposeRequest, ComposeResponse, SummarizeRequest, SummarizeResponse,
    MemoryUpsertRequest, MemoryUpsertResponse, MemorySearchResponse, Memory
)
from ..services.context_service import ContextService
from ..services.openai_service import OpenAIService
from ..database import Database


router = APIRouter(prefix="/v1")

# Initialize services (in production, use dependency injection)
from dotenv import load_dotenv
import os
load_dotenv()

database = Database()
openai_service = OpenAIService()
context_service = ContextService(openai_service, database)


@router.post("/compose", response_model=ComposeResponse)
async def compose_context(request: ComposeRequest):
    """Build context bundle from page data"""
    start_time = time.time()
    success = False
    
    try:
        context_bundle = context_service.compose_context(request)
        success = True
        
        return ComposeResponse(context_bundle=context_bundle)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Context composition failed: {str(e)}")
    
    finally:
        latency_ms = (time.time() - start_time) * 1000
        database.record_metric("compose", latency_ms, 0, success)


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_context(request: SummarizeRequest):
    """Generate structured memo from context bundle"""
    start_time = time.time()
    success = False
    tokens_used = 0
    
    try:
        result = openai_service.summarize_context(request.context_bundle, request.goal)
        tokens_used = result.pop("_tokens_used", 0)
        success = True
        
        return SummarizeResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")
    
    finally:
        latency_ms = (time.time() - start_time) * 1000
        database.record_metric("summarize", latency_ms, tokens_used, success)


@router.post("/memory/upsert", response_model=MemoryUpsertResponse)
async def upsert_memory(request: MemoryUpsertRequest):
    """Save memo to memory store"""
    start_time = time.time()
    success = False
    tokens_used = 0
    
    try:
        # Generate embedding for the text
        embedding = openai_service.get_embedding(request.text)
        tokens_used = len(request.text.split()) // 4  # Rough token estimate
        
        # Store in database
        memory_id = database.upsert_memory(
            url=request.url,
            title=request.title,
            text=request.text,
            tags=request.tags,
            embedding=embedding,
            ts=request.ts,
            metadata=request.metadata
        )
        
        success = True
        return MemoryUpsertResponse(id=memory_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Memory upsert failed: {str(e)}")
    
    finally:
        latency_ms = (time.time() - start_time) * 1000
        database.record_metric("memory_upsert", latency_ms, tokens_used, success)


@router.get("/memory/search", response_model=MemorySearchResponse)
async def search_memories(q: str, k: int = 5, url_filter: str = None):
    """Search memories by text similarity"""
    start_time = time.time()
    success = False
    tokens_used = 0
    
    try:
        # Generate query embedding
        query_embedding = openai_service.get_embedding(q)
        tokens_used = len(q.split()) // 4  # Rough token estimate
        
        # Search database
        results = database.search_memories(query_embedding, k, url_filter)
        
        # Convert to Memory objects
        memories = []
        for result in results:
            memory = Memory(
                id=result["id"],
                text=result["text"][:300],  # Truncate for response
                why=f"similarity: {result['score']:.2f}",
                score=result["score"]
            )
            memories.append(memory)
        
        success = True
        return MemorySearchResponse(hits=memories)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Memory search failed: {str(e)}")
    
    finally:
        latency_ms = (time.time() - start_time) * 1000
        database.record_metric("memory_search", latency_ms, tokens_used, success)


@router.get("/metrics")
async def get_metrics():
    """Get Prometheus-style metrics"""
    try:
        metrics_data = database.get_metrics()
        
        # Format as Prometheus text
        prometheus_text = f"""# HELP memo_latency_p95 95th percentile latency in milliseconds
# TYPE memo_latency_p95 gauge
memo_latency_p95 {metrics_data['latency_p95']}

# HELP memo_tokens_total Total tokens used
# TYPE memo_tokens_total counter
memo_tokens_total {metrics_data['token_usage_total']}

# HELP memo_success_rate Success rate (0.0-1.0)
# TYPE memo_success_rate gauge
memo_success_rate {metrics_data['success_rate']}

# HELP memo_memory_recall_rate Memory recall rate (0.0-1.0)
# TYPE memo_memory_recall_rate gauge
memo_memory_recall_rate {metrics_data['memory_recall_rate']}
"""
        
        return PlainTextResponse(content=prometheus_text)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics retrieval failed: {str(e)}")


@router.put("/memory/{memory_id}")
async def update_memory(memory_id: str, request: MemoryUpsertRequest):
    """Update an existing memo"""
    start_time = time.time()
    success = False
    tokens_used = 0
    
    try:
        # Generate new embedding if text changed
        embedding = openai_service.get_embedding(request.text)
        tokens_used = len(request.text.split()) // 4  # Rough token estimate
        
        # Update in database
        updated = database.update_memory(
            memory_id=memory_id,
            url=request.url,
            title=request.title,
            text=request.text,
            tags=request.tags,
            embedding=embedding,
            ts=request.ts,
            metadata=request.metadata
        )
        
        if not updated:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        success = True
        return {"id": memory_id, "updated": True}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Memory update failed: {str(e)}")
    
    finally:
        latency_ms = (time.time() - start_time) * 1000
        database.record_metric("memory_update", latency_ms, tokens_used, success)


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}