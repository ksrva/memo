from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from ..services.linking_service import SemanticLinkingService
from ..services.openai_service import OpenAIService
from ..database import Database


router = APIRouter(prefix="/v1/links")

# Initialize services
database = Database()
openai_service = OpenAIService()
linking_service = SemanticLinkingService(database, openai_service)


@router.get("/memo/{memo_id}")
async def get_memo_links(memo_id: str, min_score: float = Query(0.3, ge=0.0, le=1.0)):
    """Get semantically linked memos for a specific memo"""
    try:
        # First get the memo to analyze
        conn = database._get_connection()
        result = conn.execute("""
            SELECT id, text, tags FROM memories WHERE id = ?
        """, (memo_id,)).fetchone()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Memo not found")
        
        memo_text = result[1]
        memo_tags = eval(result[2]) if result[2] else []
        
        # Find linked memos
        links = linking_service.find_linked_memos(
            memo_text=memo_text,
            memo_entities=memo_tags,
            exclude_id=memo_id,
            min_score=min_score
        )
        
        return {
            "memo_id": memo_id,
            "links": links,
            "total_links": len(links)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to find links: {str(e)}")


@router.post("/discover")
async def discover_links_for_content(
    content: Dict[str, Any],
    min_score: float = Query(0.3, ge=0.0, le=1.0)
):
    """Discover potential links for new content before saving"""
    try:
        text = content.get("text", "")
        entities = content.get("entities", [])
        
        if not text:
            raise HTTPException(status_code=400, detail="Text content is required")
        
        # Find potential links
        links = linking_service.find_linked_memos(
            memo_text=text,
            memo_entities=entities,
            min_score=min_score
        )
        
        return {
            "potential_links": links,
            "total_potential_links": len(links),
            "recommendations": _generate_link_recommendations(links)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover links: {str(e)}")


@router.get("/graph")
async def get_memo_graph(limit: int = Query(50, ge=10, le=100)):
    """Get graph representation of memo relationships"""
    try:
        graph_data = linking_service.create_memo_graph(limit=limit)
        
        return {
            "graph": graph_data,
            "metadata": {
                "node_count": graph_data["total_nodes"],
                "edge_count": graph_data["total_edges"],
                "density": _calculate_graph_density(
                    graph_data["total_nodes"], 
                    graph_data["total_edges"]
                )
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate graph: {str(e)}")


@router.get("/clusters")
async def get_memo_clusters(min_cluster_size: int = Query(3, ge=2, le=10)):
    """Get clusters of related memos"""
    try:
        # Get all memories for clustering
        all_memories = linking_service._get_all_memories()[:100]
        
        if len(all_memories) < min_cluster_size:
            return {"clusters": [], "total_clusters": 0}
        
        # Simple clustering based on shared entities
        clusters = _cluster_memos_by_entities(all_memories, min_cluster_size)
        
        return {
            "clusters": clusters,
            "total_clusters": len(clusters),
            "coverage": sum(len(cluster["memos"]) for cluster in clusters)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate clusters: {str(e)}")


@router.get("/trending")
async def get_trending_topics(days: int = Query(7, ge=1, le=30)):
    """Get trending topics based on recent memo creation"""
    try:
        import sqlite3
        from collections import Counter
        import json
        from datetime import datetime, timedelta
        
        cutoff_time = int((datetime.now() - timedelta(days=days)).timestamp())
        
        conn = sqlite3.connect(database.db_path)
        results = conn.execute("""
            SELECT tags, text FROM memories 
            WHERE ts > ? 
            ORDER BY ts DESC
        """, (cutoff_time,)).fetchall()
        conn.close()
        
        # Count entity frequencies
        entity_counter = Counter()
        memo_count = 0
        
        for row in results:
            memo_count += 1
            tags = json.loads(row[0]) if row[0] else []
            text = row[1]
            
            # Count tags
            for tag in tags:
                entity_counter[tag.lower()] += 1
            
            # Extract and count text entities
            text_entities = linking_service._extract_text_entities(text)
            for entity in text_entities:
                entity_counter[entity] += 1
        
        # Get top trending topics
        trending = [
            {
                "topic": topic,
                "frequency": count,
                "percentage": (count / memo_count * 100) if memo_count > 0 else 0
            }
            for topic, count in entity_counter.most_common(10)
            if count > 1  # Only include topics mentioned multiple times
        ]
        
        return {
            "trending_topics": trending,
            "period_days": days,
            "total_memos": memo_count,
            "unique_topics": len(entity_counter)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending topics: {str(e)}")


def _generate_link_recommendations(links: List[Dict[str, Any]]) -> List[str]:
    """Generate human-readable recommendations based on links"""
    if not links:
        return ["No related content found"]
    
    recommendations = []
    
    high_score_links = [link for link in links if link['score'] > 0.7]
    if high_score_links:
        recommendations.append(f"Found {len(high_score_links)} highly related memos")
    
    entity_links = [link for link in links if link['link_type'] == 'entity_similarity']
    if entity_links:
        recommendations.append(f"Connected by shared topics: {len(entity_links)} matches")
    
    semantic_links = [link for link in links if link['link_type'] == 'semantic_similarity']
    if semantic_links:
        recommendations.append(f"Semantically related content: {len(semantic_links)} matches")
    
    return recommendations


def _calculate_graph_density(nodes: int, edges: int) -> float:
    """Calculate graph density (0 to 1)"""
    if nodes < 2:
        return 0.0
    
    max_edges = nodes * (nodes - 1) / 2
    return edges / max_edges if max_edges > 0 else 0.0


def _cluster_memos_by_entities(memories: List[Dict], min_size: int) -> List[Dict[str, Any]]:
    """Simple clustering based on shared entities"""
    import json
    from collections import defaultdict
    
    # Group by shared entities
    entity_groups = defaultdict(list)
    
    for memory in memories:
        tags = memory.get('tags', [])
        if tags:
            # Use the most common tag as cluster key
            primary_tag = tags[0].lower()
            entity_groups[primary_tag].append({
                "id": memory["id"],
                "title": memory["title"],
                "url": memory["url"],
                "tags": tags
            })
    
    # Filter clusters by minimum size
    clusters = []
    for entity, memos in entity_groups.items():
        if len(memos) >= min_size:
            clusters.append({
                "cluster_id": f"cluster_{entity}",
                "primary_entity": entity,
                "memos": memos,
                "size": len(memos)
            })
    
    # Sort by cluster size
    clusters.sort(key=lambda x: x["size"], reverse=True)
    return clusters