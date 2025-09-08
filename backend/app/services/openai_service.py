import openai
import json
import os
from typing import List, Dict, Any
from ..models import ContextBundle, SummarizeResponse


class OpenAIService:
    def __init__(self):
        self.client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
    
    def get_embedding(self, text: str) -> List[float]:
        """Get text embedding using OpenAI embeddings"""
        response = self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    
    def summarize_context(self, context_bundle: ContextBundle, goal: str) -> Dict[str, Any]:
        """Generate structured memo from context bundle"""
        
        # Build context string
        context_parts = []
        context_parts.append(f"Summary hint: {context_bundle.summary_hint}")
        
        if context_bundle.entities_hint:
            context_parts.append(f"Key entities: {', '.join(context_bundle.entities_hint)}")
        
        context_parts.append("Most relevant sections:")
        for section in context_bundle.salient_sections[:3]:
            context_parts.append(f"- {section.text} (relevance: {section.score:.2f})")
        
        if context_bundle.memories:
            context_parts.append("Related past memories:")
            for memory in context_bundle.memories[:2]:
                context_parts.append(f"- {memory.text} ({memory.why})")
        
        context_text = "\n".join(context_parts)
        
        system_prompt = """You are Memo, a browser-native assistant that creates structured memos.

Your task is to turn messy page context into a clean, actionable memo with:
- summary: ≤150 words capturing the essence
- entities: key companies, people, tools, metrics, concepts  
- tasks: 3-5 specific actionable next steps
- risks: potential pitfalls, ambiguities, or concerns

Return ONLY valid JSON in this exact format:
{
  "summary": "...",
  "entities": ["Entity1", "Entity2", ...],
  "tasks": ["Task 1", "Task 2", ...],
  "risks": ["Risk 1", "Risk 2", ...]
}"""

        user_prompt = f"""Goal: {goal}

Context:
{context_text}

Generate a structured memo as JSON:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            # Parse JSON response
            content = response.choices[0].message.content.strip()
            
            # Try to extract JSON if it's wrapped in markdown
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content)
            
            # Generate markdown version
            markdown = self._generate_markdown(result)
            result["markdown"] = markdown
            
            # Track token usage
            result["_tokens_used"] = response.usage.total_tokens
            
            return result
            
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                "summary": "Failed to parse AI response",
                "entities": [],
                "tasks": [],
                "risks": ["AI response parsing error"],
                "markdown": "# Error\nFailed to generate memo",
                "_tokens_used": 0
            }
    
    def _generate_markdown(self, memo_data: Dict[str, Any]) -> str:
        """Convert memo data to markdown format"""
        markdown_parts = []
        
        markdown_parts.append("# Memo")
        markdown_parts.append("")
        
        if memo_data.get("summary"):
            markdown_parts.append("## Summary")
            markdown_parts.append(memo_data["summary"])
            markdown_parts.append("")
        
        if memo_data.get("entities"):
            markdown_parts.append("## Key Entities")
            for entity in memo_data["entities"]:
                markdown_parts.append(f"- {entity}")
            markdown_parts.append("")
        
        if memo_data.get("tasks"):
            markdown_parts.append("## Next Steps")
            for i, task in enumerate(memo_data["tasks"], 1):
                markdown_parts.append(f"{i}. {task}")
            markdown_parts.append("")
        
        if memo_data.get("risks"):
            markdown_parts.append("## Risks & Considerations")
            for risk in memo_data["risks"]:
                markdown_parts.append(f"- {risk}")
            markdown_parts.append("")
        
        return "\n".join(markdown_parts)