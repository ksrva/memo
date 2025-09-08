import sqlite3
import sqlite_vss
import json
import uuid
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import numpy as np


class Database:
    def __init__(self, db_path: str = "memo.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database with schema and vector search extension"""
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vss.load(conn)
        
        # Create memories table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                tags TEXT,
                ts INTEGER NOT NULL,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create vector search table for embeddings
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING vss0(embedding(1536))")
        
        # Create metrics table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                tokens_used INTEGER,
                success BOOLEAN NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def upsert_memory(self, url: str, title: str, text: str, tags: List[str], 
                     embedding: List[float], ts: Optional[int] = None, 
                     metadata: Dict[str, Any] = None) -> str:
        """Store memory with vector embedding"""
        memory_id = str(uuid.uuid4())
        if ts is None:
            ts = int(datetime.now().timestamp())
        
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vss.load(conn)
        
        try:
            # Insert memory
            conn.execute("""
                INSERT OR REPLACE INTO memories 
                (id, url, title, text, tags, ts, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (memory_id, url, title, text, json.dumps(tags), ts, 
                 json.dumps(metadata or {})))
            
            # Insert embedding into VSS table
            rowid = abs(hash(memory_id)) % (2**63 - 1)
            conn.execute("""
                INSERT INTO memory_embeddings(rowid, embedding)
                VALUES (?, ?)
            """, (rowid, json.dumps(embedding)))
            
            conn.commit()
            return memory_id
        finally:
            conn.close()
    
    def update_memory(self, memory_id: str, url: str, title: str, text: str, 
                     tags: List[str], embedding: List[float], ts: Optional[int] = None, 
                     metadata: Dict[str, Any] = None) -> bool:
        """Update existing memory with new content"""
        if ts is None:
            ts = int(datetime.now().timestamp())
        
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vss.load(conn)
        
        try:
            # Update memory record
            cursor = conn.execute("""
                UPDATE memories 
                SET url = ?, title = ?, text = ?, tags = ?, ts = ?, metadata = ?
                WHERE id = ?
            """, (url, title, text, json.dumps(tags), ts, 
                 json.dumps(metadata or {}), memory_id))
            
            if cursor.rowcount == 0:
                return False  # Memory not found
            
            # Update embedding in VSS table
            rowid = abs(hash(memory_id)) % (2**63 - 1)
            conn.execute("""
                UPDATE memory_embeddings 
                SET embedding = ?
                WHERE rowid = ?
            """, (json.dumps(embedding), rowid))
            
            conn.commit()
            return True
        finally:
            conn.close()
    
    def search_memories(self, query_embedding: List[float], k: int = 5, 
                       url_filter: Optional[str] = None) -> List[Dict]:
        """Search memories by vector similarity using sqlite-vss"""
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vss.load(conn)
        
        try:
            # Use vss_search with proper syntax (requires LIMIT)
            search_results = conn.execute("""
                SELECT rowid, distance 
                FROM memory_embeddings 
                WHERE vss_search(embedding, ?) 
                LIMIT ?
            """, (json.dumps(query_embedding), k * 2)).fetchall()  # Get more results to filter
            
            if not search_results:
                return []
            
            # Create a mapping table to link VSS rowid to memory_id
            memories = []
            vss_rowids = [str(vss_rowid) for vss_rowid, _ in search_results]
            
            # Get all memories and match them by the hash calculation
            all_memories = conn.execute("""
                SELECT id, url, title, text, tags, ts
                FROM memories
                ORDER BY created_at DESC
            """).fetchall()
            
            # Create rowid to memory mapping
            rowid_to_memory = {}
            for row in all_memories:
                memory_id = row[0]
                calculated_rowid = abs(hash(memory_id)) % (2**63 - 1)
                rowid_to_memory[calculated_rowid] = {
                    "id": row[0],
                    "url": row[1],
                    "title": row[2], 
                    "text": row[3],
                    "tags": json.loads(row[4]) if row[4] else [],
                    "ts": row[5]
                }
            
            # Match search results with memories
            for vss_rowid, distance in search_results:
                if vss_rowid in rowid_to_memory:
                    memory = rowid_to_memory[vss_rowid].copy()
                    memory["score"] = max(0.0, 1.0 - distance)  # Convert distance to similarity
                    
                    # Apply URL filter if needed
                    if url_filter and url_filter.lower() not in memory["url"].lower():
                        continue
                        
                    memories.append(memory)
            
            # Sort by similarity score and return top k
            memories.sort(key=lambda x: x["score"], reverse=True)
            return memories[:k]
            
        finally:
            conn.close()
    
    def record_metric(self, endpoint: str, latency_ms: float, tokens_used: int, 
                     success: bool):
        """Record performance metrics"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO metrics (endpoint, latency_ms, tokens_used, success)
            VALUES (?, ?, ?, ?)
        """, (endpoint, latency_ms, tokens_used, success))
        conn.commit()
        conn.close()
    
    def get_metrics(self) -> Dict[str, float]:
        """Get aggregated metrics"""
        conn = sqlite3.connect(self.db_path)
        
        # Get P95 latency
        latency_p95 = conn.execute("""
            SELECT latency_ms FROM metrics 
            ORDER BY latency_ms 
            LIMIT 1 OFFSET (SELECT COUNT(*) * 95 / 100 FROM metrics)
        """).fetchone()
        latency_p95 = latency_p95[0] if latency_p95 else 0.0
        
        # Get total tokens
        token_total = conn.execute("""
            SELECT SUM(tokens_used) FROM metrics WHERE tokens_used IS NOT NULL
        """).fetchone()
        token_total = token_total[0] if token_total and token_total[0] else 0
        
        # Get success rate
        success_rate = conn.execute("""
            SELECT AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) FROM metrics
        """).fetchone()
        success_rate = success_rate[0] if success_rate else 0.0
        
        conn.close()
        
        return {
            "latency_p95": latency_p95,
            "token_usage_total": int(token_total),
            "success_rate": success_rate,
            "memory_recall_rate": 0.7  # Placeholder - would need more complex tracking
        }