import math
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DocumentChunk(BaseModel):
    id: str
    doc_title: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = {}


class RAGKnowledgeBase:
    def __init__(self, openai_client: Optional[AsyncOpenAI] = None):
        self.client = openai_client
        self.chunks: List[DocumentChunk] = []

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        norm_a = math.sqrt(sum(a * a for a in v1))
        norm_b = math.sqrt(sum(b * b for b in v2))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def get_embedding(self, text: str) -> List[float]:
        if not self.client:
            return [0.0] * 1536
        res = await self.client.embeddings.create(
            input=text.replace("\n", " "),
            model="text-embedding-3-small"
        )
        return res.data[0].embedding

    async def add_document(self, doc_id: str, title: str, content: str, chunk_size: int = 500, overlap: int = 50):
        """Chunks and embeds a document for semantic retrieval."""
        words = content.split()
        idx = 0
        while idx < len(words):
            chunk_words = words[idx : idx + chunk_size]
            chunk_text = " ".join(chunk_words)
            emb = await self.get_embedding(chunk_text)
            self.chunks.append(
                DocumentChunk(
                    id=f"{doc_id}_{idx}",
                    doc_title=title,
                    content=chunk_text,
                    embedding=emb
                )
            )
            idx += (chunk_size - overlap)

    async def search(self, query: str, top_k: int = 3, min_similarity: float = 0.6) -> List[Dict[str, Any]]:
        """
        Retrieves top-k semantically relevant chunks with citation metadata.
        """
        if not self.chunks or not self.client:
            return []

        query_emb = await self.get_embedding(query)
        scored = []
        for ch in self.chunks:
            sim = self.cosine_similarity(query_emb, ch.embedding)
            if sim >= min_similarity:
                scored.append((sim, ch))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sim, ch in scored[:top_k]:
            results.append({
                "score": sim,
                "title": ch.doc_title,
                "content": ch.content,
                "citation": f"[Source: {ch.doc_title}]"
            })
        return results
