"""
Persistent Memory Bank for Plexir using ChromaDB.
"""

import os
import logging
import uuid
from typing import List, Dict, Any, Optional

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    HAS_MEMORY_DEPS = True
except ImportError:
    HAS_MEMORY_DEPS = False

logger = logging.getLogger(__name__)

MEMORY_DIR = os.path.expanduser("~/.plexir/memory")

class MemoryBank:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryBank, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
            
        if not HAS_MEMORY_DEPS:
            logger.warning("MemoryBank dependencies (chromadb, sentence-transformers) not found. Memory features disabled.")
            self.initialized = False
            return

        os.makedirs(MEMORY_DIR, exist_ok=True)
        
        try:
            self.client = chromadb.PersistentClient(path=MEMORY_DIR)
            
            # Use a lightweight model for local embeddings
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
            
            self.collection = self.client.get_or_create_collection(
                name="plexir_memory",
                metadata={"hnsw:space": "cosine"}
            )
            self.initialized = True
            logger.info("MemoryBank initialized with ChromaDB.")
        except Exception as e:
            logger.error(f"Failed to initialize MemoryBank: {e}")
            self.initialized = False

    def add(self, text: str, metadata: Dict[str, Any] = None) -> str:
        if not self.initialized:
            return "MemoryBank not initialized."

        try:
            doc_id = str(uuid.uuid4())
            embedding = self.embedder.encode(text).tolist()
            
            self.collection.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )
            return f"Memory saved (ID: {doc_id})"
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return f"Error saving memory: {e}"

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        if not self.initialized:
            return []

        try:
            query_embedding = self.embedder.encode(query).tolist()
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            # Flatten results structure
            documents = results['documents'][0]
            metadatas = results['metadatas'][0]
            ids = results['ids'][0]
            distances = results['distances'][0]
            
            formatted_results = []
            for i in range(len(documents)):
                formatted_results.append({
                    "id": ids[i],
                    "content": documents[i],
                    "metadata": metadatas[i],
                    "score": 1 - distances[i] # Convert distance to similarity score
                })
                
            return formatted_results
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    def delete(self, doc_id: str) -> str:
        if not self.initialized:
             return "MemoryBank not initialized."
        try:
            self.collection.delete(ids=[doc_id])
            return f"Memory {doc_id} deleted."
        except Exception as e:
            return f"Error deleting memory: {e}"
