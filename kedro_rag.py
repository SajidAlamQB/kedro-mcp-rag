"""Kedro RAG System """

import asyncio
import httpx
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional, Callable
import re
from langchain.agents import tool
from langchain_openai import ChatOpenAI
import logging

logger = logging.getLogger(__name__)


class KedroRAG:
    """Kedro Rag"""

    def __init__(self, persist_directory: str = "./kedro_knowledge_db"):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.client = chromadb.PersistentClient(path=persist_directory)

        try:
            self.collection = self.client.get_collection("kedro_knowledge")
            logger.info(f"Loaded existing knowledge base")
        except:
            self.collection = self.client.create_collection("kedro_knowledge")
            logger.info("Created new knowledge base")

    def format_documentation(self, content: str) -> Dict[str, str]:
        """Format documentation content into chunks"""
        chunks = {}

        # Split by sections (similar to dialog processing)
        sections = re.split(r'\n#{1,3}\s+', content)

        for i, section in enumerate(sections):
            if section.strip():
                # Create chunk ID similar to dialog_name
                chunk_id = f"kedro_doc_chunk_{i}"
                chunks[chunk_id] = section.strip()
                logger.info(f"Formatted chunk {chunk_id}")

        return chunks

    def create_embedding_function(self) -> Callable:
        """Creates embedding function"""

        def embedding_function(texts: List[str]) -> List:
            if isinstance(texts, str):
                texts = [texts]
            embeddings = self.embedder.encode(texts)
            return embeddings.tolist()

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

        for chunk_id, chunk_text in formatted_chunks.items():
            embedding = embedding_function(chunk_text)

            self.collection.add(
                embeddings=[embedding],
                documents=[chunk_text],
                metadatas=[{"chunk_id": chunk_id, "source": "kedro_docs"}],
                ids=[chunk_id]
            )

        logger.info(f"Added {len(formatted_chunks)} chunks to knowledge base")

    def create_retrieval_tool(self) -> Callable:
        """Create retrieval tool"""
        embedding_function = self.create_embedding_function()

        @tool
        def search_kedro_knowledge(query: str) -> str:
            """Search Kedro documentation for relevant information"""
            query_embedding = embedding_function(query)

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=3
            )

            if results['documents'] and results['documents'][0]:
                # Combine multiple results
                contexts = results['documents'][0]
                return "\n\n".join(contexts)
            else:
                return "No relevant context found in Kedro documentation"

        return search_kedro_knowledge


# Adapted nodes for MCP integration
class KedroMCPNodes:
    """Adapted from agent_rag nodes for MCP server use"""

    def __init__(self, rag_system: KedroRAG):
        self.rag = rag_system
        self.tool = self.rag.create_retrieval_tool()

    async def search_kedro_docs(self, query: str) -> Dict:
        """Adapted from invoke_agent - but returns structured data for MCP"""
        # Direct search using embeddings
        embedding_function = self.rag.create_embedding_function()
        query_embedding = embedding_function(query)

        results = self.rag.collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )

        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "relevance_score": 1 - results['distances'][0][i]
                })

        return {
            "query": query,
            "results": formatted_results,
            "total_results": len(formatted_results)
        }

    async def answer_kedro_question(self, question: str, openai_api_key: str) -> Dict:
        """Adapted from user_interaction_loop - single Q&A instead of loop"""
        # Initialize LLM (from init_llm node)
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.0,
            openai_api_key=openai_api_key
        )

        # Get context using the tool
        context = self.tool.invoke(question)

        # Create prompt (adapted from create_chat_prompt)
        prompt = f"""You are a helpful assistant who answers questions about the Kedro framework.

Based on the following context from Kedro documentation, answer the user's question.

Context:
{context}

Question: {question}

Answer:"""

        # Get LLM response
        response = llm.invoke(prompt)

        return {
            "question": question,
            "context": context,
            "answer": response.content,
            "model": "gpt-3.5-turbo"
        }


# Integration with MCP server
async def integrate_with_mcp(mcp_server):
    """Add RAG capabilities to existing MCP server"""
    # Initialize RAG (similar to pipeline initialization)
    rag_system = KedroRAG()

    # Build knowledge base if needed
    if rag_system.collection.count() == 0:
        await rag_system.build_knowledge_base()

    # Create nodes adapter
    nodes = KedroMCPNodes(rag_system)

    # Add tools to MCP server
    @mcp_server.tool()
    async def search_kedro_docs(query: str):
        """Search Kedro documentation (adapted from agent tools)"""
        return await nodes.search_kedro_docs(query)

    @mcp_server.tool()
    async def answer_kedro_question(question: str, api_key: str):
        """Get AI-powered answer (adapted from agent executor)"""
        return await nodes.answer_kedro_question(question, api_key)

    return rag_system


# Standalone testing (adapted from the original test approach)
async def test_adapted_rag():
    """Test the adapted RAG system"""
    rag = KedroRAG()

    # Build knowledge base
    await rag.build_knowledge_base()

    # Test search
    nodes = KedroMCPNodes(rag)

    test_queries = [
        "How to create a custom dataset in Kedro?",
        "What is a Kedro node?",
        "Pipeline configuration"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        results = await nodes.search_kedro_docs(query)
        print(f"Found {results['total_results']} results")
        if results['results']:
            print(f"Top result: {results['results'][0]['content'][:200]}...")


if __name__ == "__main__":
    asyncio.run(test_adapted_rag())
