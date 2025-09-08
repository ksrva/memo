import re
import nltk
from typing import List, Dict, Any, Optional
from ..models import ComposeRequest, ContextBundle, SalientSection, Memory
from .openai_service import OpenAIService
from ..database import Database


class ContextService:
    def __init__(self, openai_service: OpenAIService, database: Database):
        self.openai_service = openai_service
        self.database = database
        
        # Download NLTK data if needed (handle silently)
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
    
    def compose_context(self, request: ComposeRequest) -> ContextBundle:
        """Build context bundle from page data"""
        
        # Clean and process main text
        cleaned_text = self._clean_text(request.main_text)
        
        # Generate summary hint
        summary_hint = self._generate_summary_hint(cleaned_text, request.title)
        
        # Extract entities
        entities_hint = self._extract_entities(cleaned_text, request.title)
        
        # Rank text sections by relevance
        salient_sections = self._rank_sections(cleaned_text, request.selection or "", request.goal)
        
        # Retrieve relevant memories
        memories = self._get_relevant_memories(request.url, cleaned_text)
        
        return ContextBundle(
            summary_hint=summary_hint,
            entities_hint=entities_hint,
            salient_sections=salient_sections,
            memories=memories
        )
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common web artifacts
        text = re.sub(r'(Skip to|Jump to|Click here|Read more)', '', text, flags=re.IGNORECASE)
        
        # Remove navigation elements
        text = re.sub(r'(Home|About|Contact|Menu|Navigation)', '', text, flags=re.IGNORECASE)
        
        # Limit length for processing
        if len(text) > 5000:
            text = text[:5000] + "..."
        
        return text.strip()
    
    def _generate_summary_hint(self, text: str, title: str) -> str:
        """Generate a quick summary hint from title and text"""
        # Use first few sentences + title
        sentences = nltk.sent_tokenize(text)
        first_sentences = ' '.join(sentences[:2]) if sentences else ""
        
        if len(first_sentences) > 200:
            first_sentences = first_sentences[:200] + "..."
        
        return f"{title}. {first_sentences}".strip()
    
    def _extract_entities(self, text: str, title: str) -> List[str]:
        """Extract key entities using simple heuristics"""
        entities = []
        
        # Extract capitalized words/phrases
        capitalized = re.findall(r'\b[A-Z][a-z]*(?:\s+[A-Z][a-z]*)*\b', text + " " + title)
        
        # Filter and dedupe
        for entity in capitalized:
            if len(entity) > 2 and entity not in entities and len(entities) < 10:
                # Skip common words
                if entity.lower() not in ['the', 'and', 'for', 'with', 'this', 'that']:
                    entities.append(entity)
        
        # Extract company/tech terms
        tech_patterns = [
            r'\b(TypeScript|JavaScript|Python|React|FastAPI|OpenAI|GPT)\b',
            r'\b(\w+\.(com|io|org|net))\b',
            r'\b(\$\d+[KMB]?)\b',  # Dollar amounts
            r'\b(\d+%)\b'  # Percentages
        ]
        
        for pattern in tech_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match not in entities and len(entities) < 15:
                    entities.append(match)
        
        return entities[:8]  # Limit to most relevant
    
    def _rank_sections(self, text: str, selection: str, goal: str) -> List[SalientSection]:
        """Rank text sections by relevance to goal and selection"""
        sentences = nltk.sent_tokenize(text)
        
        sections = []
        goal_words = set(goal.lower().split()) if goal else set()
        selection_words = set(selection.lower().split()) if selection else set()
        
        for sentence in sentences:
            if len(sentence) < 20:  # Skip very short sentences
                continue
                
            sentence_words = set(sentence.lower().split())
            
            # Score based on overlap with goal and selection
            goal_overlap = len(sentence_words & goal_words) / len(goal_words) if goal_words else 0
            selection_overlap = len(sentence_words & selection_words) / len(selection_words) if selection_words else 0
            
            # Boost sentences with entities/numbers
            entity_boost = 0.1 * len(re.findall(r'\b[A-Z][a-z]*\b', sentence))
            number_boost = 0.1 * len(re.findall(r'\b\d+\b', sentence))
            
            score = goal_overlap * 0.4 + selection_overlap * 0.4 + entity_boost + number_boost
            
            if len(sentence) > 300:
                sentence = sentence[:300] + "..."
            
            sections.append(SalientSection(text=sentence, score=score))
        
        # Sort by score and return top sections
        sections.sort(key=lambda x: x.score, reverse=True)
        return sections[:5]
    
    def _get_relevant_memories(self, url: str, text: str) -> List[Memory]:
        """Retrieve relevant memories from past visits"""
        try:
            # Get embedding for current content
            embedding = self.openai_service.get_embedding(text[:1000])  # Limit text for embedding
            
            # Search similar memories
            similar_memories = self.database.search_memories(embedding, k=3)
            
            memories = []
            for mem_data in similar_memories:
                if mem_data["score"] > 0.7:  # Only high similarity
                    why = "high similarity" if mem_data["score"] > 0.85 else "related content"
                    
                    memory = Memory(
                        id=mem_data["id"],
                        text=mem_data["text"][:200],  # Truncate for context
                        why=why,
                        score=mem_data["score"]
                    )
                    memories.append(memory)
            
            return memories
            
        except Exception as e:
            # Gracefully handle embedding/search failures
            return []