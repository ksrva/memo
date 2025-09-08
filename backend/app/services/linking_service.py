from typing import List, Dict, Any, Set
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from ..database import Database
from .openai_service import OpenAIService


class SemanticLinkingService:
    def __init__(self, database: Database, openai_service: OpenAIService):
        self.database = database
        self.openai_service = openai_service
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
    
    def find_linked_memos(self, memo_text: str, memo_entities: List[str], 
                         exclude_id: str = None, min_score: float = 0.3) -> List[Dict[str, Any]]:
        """Find semantically linked memos based on content and entities"""
        
        # Get all memories for comparison
        all_memories = self._get_all_memories(exclude_id)
        
        if len(all_memories) < 2:
            return []
        
        # Find links using multiple methods
        entity_links = self._find_entity_based_links(memo_entities, all_memories, min_score)
        semantic_links = self._find_semantic_similarity_links(memo_text, all_memories, min_score)
        
        # Combine and deduplicate links
        combined_links = self._combine_link_scores(entity_links, semantic_links)
        
        # Sort by score and return top links
        combined_links.sort(key=lambda x: x['score'], reverse=True)
        return combined_links[:5]  # Return top 5 links
    
    def _get_all_memories(self, exclude_id: str = None) -> List[Dict]:
        """Get all memories from database for linking analysis"""
        conn = self.database._get_connection()
        
        try:
            if exclude_id:
                query = """
                    SELECT id, url, title, text, tags, ts 
                    FROM memories 
                    WHERE id != ? 
                    ORDER BY created_at DESC 
                    LIMIT 100
                """
                results = conn.execute(query, (exclude_id,)).fetchall()
            else:
                query = """
                    SELECT id, url, title, text, tags, ts 
                    FROM memories 
                    ORDER BY created_at DESC 
                    LIMIT 100
                """
                results = conn.execute(query).fetchall()
            
            memories = []
            for row in results:
                memories.append({
                    "id": row[0],
                    "url": row[1], 
                    "title": row[2],
                    "text": row[3],
                    "tags": json.loads(row[4]) if row[4] else [],
                    "ts": row[5]
                })
            
            return memories
        finally:
            conn.close()
    
    def _find_entity_based_links(self, memo_entities: List[str], 
                                all_memories: List[Dict], min_score: float) -> List[Dict[str, Any]]:
        """Find links based on shared entities"""
        entity_set = set([entity.lower() for entity in memo_entities])
        links = []
        
        for memory in all_memories:
            # Check entities in tags
            memory_entities = set([tag.lower() for tag in memory.get('tags', [])])
            
            # Also extract entities from text (simple approach)
            text_entities = self._extract_text_entities(memory['text'])
            memory_entities.update(text_entities)
            
            # Calculate entity overlap
            common_entities = entity_set.intersection(memory_entities)
            
            if common_entities:
                # Score based on Jaccard similarity
                union_entities = entity_set.union(memory_entities)
                jaccard_score = len(common_entities) / len(union_entities)
                
                if jaccard_score >= min_score:
                    links.append({
                        'memory_id': memory['id'],
                        'title': memory['title'],
                        'text': memory['text'][:200] + "..." if len(memory['text']) > 200 else memory['text'],
                        'url': memory['url'],
                        'score': jaccard_score,
                        'link_type': 'entity_similarity',
                        'shared_entities': list(common_entities)
                    })
        
        return links
    
    def _find_semantic_similarity_links(self, memo_text: str, 
                                       all_memories: List[Dict], min_score: float) -> List[Dict[str, Any]]:
        """Find links based on semantic text similarity using TF-IDF"""
        if len(all_memories) == 0:
            return []
        
        # Prepare texts for vectorization
        texts = [memo_text] + [memory['text'] for memory in all_memories]
        
        try:
            # Compute TF-IDF vectors
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
            
            # Calculate cosine similarity
            similarity_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
            
            links = []
            for i, score in enumerate(similarity_scores):
                if score >= min_score:
                    memory = all_memories[i]
                    links.append({
                        'memory_id': memory['id'],
                        'title': memory['title'],
                        'text': memory['text'][:200] + "..." if len(memory['text']) > 200 else memory['text'],
                        'url': memory['url'],
                        'score': float(score),
                        'link_type': 'semantic_similarity',
                        'shared_entities': []
                    })
            
            return links
            
        except Exception as e:
            # Fallback to simple keyword matching if TF-IDF fails
            return self._fallback_keyword_matching(memo_text, all_memories, min_score)
    
    def _fallback_keyword_matching(self, memo_text: str, 
                                  all_memories: List[Dict], min_score: float) -> List[Dict[str, Any]]:
        """Simple keyword-based matching as fallback"""
        memo_words = set(memo_text.lower().split())
        links = []
        
        for memory in all_memories:
            memory_words = set(memory['text'].lower().split())
            
            # Calculate word overlap
            common_words = memo_words.intersection(memory_words)
            union_words = memo_words.union(memory_words)
            
            if len(union_words) > 0:
                jaccard_score = len(common_words) / len(union_words)
                
                if jaccard_score >= min_score:
                    links.append({
                        'memory_id': memory['id'],
                        'title': memory['title'],
                        'text': memory['text'][:200] + "..." if len(memory['text']) > 200 else memory['text'],
                        'url': memory['url'],
                        'score': jaccard_score,
                        'link_type': 'keyword_similarity',
                        'shared_entities': []
                    })
        
        return links
    
    def _extract_text_entities(self, text: str) -> Set[str]:
        """Simple entity extraction from text"""
        import re
        
        entities = set()
        
        # Extract capitalized words/phrases (basic NER)
        capitalized = re.findall(r'\b[A-Z][a-z]*(?:\s+[A-Z][a-z]*)*\b', text)
        for entity in capitalized:
            if len(entity) > 2 and entity.lower() not in {'the', 'and', 'for', 'with'}:
                entities.add(entity.lower())
        
        # Extract tech terms
        tech_terms = re.findall(r'\b(JavaScript|TypeScript|Python|React|Vue|Angular|Docker|Kubernetes|API|REST|GraphQL|SQL|NoSQL|AWS|GCP|Azure)\b', text, re.IGNORECASE)
        for term in tech_terms:
            entities.add(term.lower())
        
        return entities
    
    def _combine_link_scores(self, entity_links: List[Dict], 
                           semantic_links: List[Dict]) -> List[Dict[str, Any]]:
        """Combine scores from different linking methods"""
        combined = {}
        
        # Add entity-based links
        for link in entity_links:
            memory_id = link['memory_id']
            combined[memory_id] = {
                **link,
                'entity_score': link['score'],
                'semantic_score': 0.0
            }
        
        # Add or update with semantic similarity scores
        for link in semantic_links:
            memory_id = link['memory_id']
            if memory_id in combined:
                combined[memory_id]['semantic_score'] = link['score']
                # Combined score: weighted average
                combined[memory_id]['score'] = (
                    0.6 * combined[memory_id]['entity_score'] + 
                    0.4 * link['score']
                )
                combined[memory_id]['link_type'] = 'combined_similarity'
            else:
                combined[memory_id] = {
                    **link,
                    'entity_score': 0.0,
                    'semantic_score': link['score']
                }
        
        return list(combined.values())
    
    def create_memo_graph(self, limit: int = 50) -> Dict[str, Any]:
        """Create a graph representation of memo relationships"""
        all_memories = self._get_all_memories()[:limit]
        
        if len(all_memories) < 2:
            return {"nodes": [], "edges": []}
        
        nodes = []
        edges = []
        
        # Create nodes
        for memory in all_memories:
            nodes.append({
                "id": memory['id'],
                "title": memory['title'],
                "url": memory['url'],
                "tags": memory.get('tags', []),
                "text_preview": memory['text'][:100] + "..." if len(memory['text']) > 100 else memory['text']
            })
        
        # Create edges by finding links between all pairs
        for i, memory1 in enumerate(all_memories):
            for j, memory2 in enumerate(all_memories[i+1:], start=i+1):
                # Calculate similarity between this pair
                entity_links = self._find_entity_based_links(
                    memory1.get('tags', []), [memory2], min_score=0.2
                )
                
                if entity_links:
                    link = entity_links[0]
                    edges.append({
                        "source": memory1['id'],
                        "target": memory2['id'],
                        "score": link['score'],
                        "type": link['link_type'],
                        "shared_entities": link.get('shared_entities', [])
                    })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges)
        }
    
    def _get_connection(self):
        """Get database connection"""
        import sqlite3
        return sqlite3.connect(self.database.db_path)