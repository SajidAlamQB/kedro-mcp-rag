"""Kedro RAG System"""

import httpx
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Callable, Optional
import re
import logging
import os
import json
from datetime import datetime

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

    def add_slack_data(self, slack_messages: List[Dict], channel_name: str):
        """Add Slack messages to the knowledge base"""
        logger.info(f"Adding {len(slack_messages)} Slack messages from #{channel_name}")
        
        embedding_function = self.create_embedding_function()
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for i, message in enumerate(slack_messages):
            content = message.get('content', '')
            if not content.strip():
                continue
                
            # Create unique ID for slack message
            message_id = f"slack_{channel_name}_{i}_{int(datetime.now().timestamp())}"
            
            # Get embedding
            embedding = embedding_function(content)
            
            # Prepare metadata
            metadata = {
                "source": "slack",
                "channel": channel_name,
                "message_type": message.get('metadata', {}).get('message_type', 'message'),
                "user": message.get('metadata', {}).get('user', 'Unknown'),
                "timestamp": message.get('metadata', {}).get('timestamp', 'Unknown')
            }
            
            ids.append(message_id)
            embeddings.append(embedding)
            documents.append(content)
            metadatas.append(metadata)
        
        if ids:  # Only add if we have valid messages
            self.collection.add(
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(ids)} Slack messages to knowledge base")
        else:
            logger.warning("No valid Slack messages to add")

    async def fetch_and_store_slack_data(self, channel_id: str, days_back: int = 30):
        """Fetch Slack data and add to knowledge base"""
        try:
            # Import here to avoid dependency issues if slack-sdk not installed
            from slack_integration import SlackIntegration
            
            slack = SlackIntegration()
            
            # Get channel info
            channel_info = slack.client.conversations_info(channel=channel_id)
            channel_name = channel_info["channel"]["name"]
            
            # Fetch messages
            messages = slack.get_channel_messages(channel_id, days_back)
            formatted_messages = slack.format_messages_for_rag(messages, channel_name, filter_questions=True)
            
            # Add to knowledge base
            self.add_slack_data(formatted_messages, channel_name)
            
            return {
                "channel_name": channel_name,
                "messages_added": len(formatted_messages),
                "total_messages_fetched": len(messages)
            }
            
        except ImportError:
            logger.error("slack_integration module not available. Install slack-sdk first.")
            return {"error": "Slack integration not available"}
        except Exception as e:
            logger.error(f"Error fetching Slack data: {e}")
            return {"error": str(e)}

    def search(self, query: str, source_filter: Optional[str] = None, top_k: int = 5) -> List[Dict]:
        """Search with optional source filtering"""
        embedding_function = self.create_embedding_function()
        query_embedding = embedding_function(query)
        
        # Build where clause for filtering
        where_clause = None
        if source_filter:
            where_clause = {"source": source_filter}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause
        )
        
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    "content": doc,
                    "source": results['metadatas'][0][i].get('source', 'unknown') if results['metadatas'] else 'unknown',
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "relevance_score": 1 - results['distances'][0][i] if results['distances'] else 0
                })
        
        return formatted_results
