"""Kedro RAG System"""

import httpx
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Callable
import re
import logging

logger = logging.getLogger(__name__)


class KedroRAG:
    def __init__(self, persist_directory: str = "./kedro_knowledge_db"):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.client = chromadb.PersistentClient(path=persist_directory)

        try:
            self.collection = self.client.get_collection("kedro_knowledge")
            logger.info(f"Loaded existing knowledge base with {self.collection.count()} chunks")
        except:
            self.collection = self.client.create_collection("kedro_knowledge")
            logger.info("Created new knowledge base")

    def format_documentation(self, content: str) -> Dict[str, str]:
        """Format documentation content into chunks"""
        chunks = {}

        # Split by sections (headers)
        sections = re.split(r'\n#{1,3}\s+', content)

        for i, section in enumerate(sections):
            if section.strip():
                # Extract section title if possible
                lines = section.strip().split('\n')
                title = lines[0][:50] if lines else f"Section {i}"

                chunk_id = f"kedro_doc_chunk_{i}"
                chunks[chunk_id] = section.strip()
                logger.info(f"Formatted chunk {chunk_id}: {title}...")

        return chunks

    def create_embedding_function(self) -> Callable:
        """Creates embedding function"""

        def embedding_function(texts: List[str]) -> List:
            if isinstance(texts, str):
                texts = [texts]

            # encode returns numpy array or list of arrays
            embeddings = self.embedder.encode(texts)

            # If single text, return the embedding vector directly
            if len(texts) == 1:
                return embeddings[0].tolist()
            else:
                # For multiple texts, return list of embedding vectors
                return [emb.tolist() for emb in embeddings]

        return embedding_function

    async def build_knowledge_base(self):
        """Build knowledge base from Kedro docs"""
        logger.info("Building Kedro knowledge base...")

        # Fetch llms.txt
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get("http://127.0.0.1:8000/en/stable/llms-full.txt")
            content = response.text

        # Format into chunks
        formatted_chunks = self.format_documentation(content)

        # Create embeddings
        embedding_function = self.create_embedding_function()

        # Prepare batch data for ChromaDB
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for chunk_id, chunk_text in formatted_chunks.items():
            # Get single embedding vector for this chunk
            embedding = embedding_function(chunk_text)

            ids.append(chunk_id)
            embeddings.append(embedding)
            documents.append(chunk_text)
            metadatas.append({"chunk_id": chunk_id, "source": "kedro_docs"})

        self.collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

        logger.info(f"Added {len(formatted_chunks)} chunks to knowledge base")

    async def search_docs(self, query: str, num_results: int = 5) -> Dict:
        """Search Kedro documentation with structured results"""
        embedding_function = self.create_embedding_function()
        query_embedding = embedding_function(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=num_results
        )

        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    "content": doc,
                    "chunk_id": results['ids'][0][i] if results['ids'] else f"chunk_{i}",
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "relevance_score": 1 - results['distances'][0][i] if results['distances'] else 0
                })

        return {
            "query": query,
            "results": formatted_results,
            "total_results": len(formatted_results)
        }

    async def get_context(self, topic: str, num_results: int = 3) -> str:
        """Get relevant context as a single string"""
        search_results = await self.search_docs(topic, num_results)

        if search_results['results']:
            contexts = [result['content'] for result in search_results['results']]
            return "\n\n---\n\n".join(contexts)
        else:
            return "No relevant context found in Kedro documentation"
