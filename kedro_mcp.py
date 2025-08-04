"""Kedro RAG MCP Server"""

from typing import Dict
from mcp.server.fastmcp import FastMCP
from kedro_rag import KedroRAG
import os
import sys
import tempfile
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

mcp = FastMCP("kedro-assistant")

# Global RAG instance
rag_system = None


async def get_rag():
    """Initialise or get existing RAG system"""
    global rag_system
    if rag_system is None:
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), "kedro_knowledge_db")
            os.makedirs(temp_dir, exist_ok=True)

            logger.info(f"Initialising RAG system at {temp_dir}")
            rag_system = KedroRAG(persist_directory=temp_dir)

            # Check if we need to build knowledge base
            collection_count = rag_system.collection.count()
            if collection_count == 0:
                logger.info("Building knowledge base from scratch...")
                await rag_system.build_knowledge_base()
                logger.info(f"Knowledge base built with {rag_system.collection.count()} chunks")
            else:
                logger.info(f"Using existing knowledge base with {collection_count} chunks")

        except Exception as e:
            logger.error(f"Failed to initialise RAG system: {e}")
            raise

    return rag_system


@mcp.tool()
async def search_kedro_docs(query: str, num_results: int = 5) -> Dict:
    """
    Search Kedro documentation using vector similarity.

    This tool retrieves relevant snippets from Kedro documentation
    based on semantic similarity to your query.

    Args:
        query: Your search query about Kedro
        num_results: Number of results to return (default: 5)

    Returns:
        Dict with search results including content, relevance scores, and metadata
    """
    try:
        rag = await get_rag()
        return await rag.search_docs(query, num_results)

    except Exception as e:
        logger.error(f"Error in search_kedro_docs: {e}")
        return {
            "error": f"Search failed: {str(e)}",
            "query": query,
            "results": [],
            "total_results": 0
        }


@mcp.tool()
async def get_kedro_context(topic: str, num_chunks: int = 3) -> Dict:
    """
    Get relevant context about a Kedro topic.

    Similar to search but returns a single combined context string
    that's ready to use for answering questions.

    Args:
        topic: The Kedro topic to get context for
        num_chunks: Number of documentation chunks to combine (default: 3)

    Returns:
        Dict with the combined context
    """
    try:
        rag = await get_rag()
        context = await rag.get_context(topic, num_chunks)

        return {
            "topic": topic,
            "context": context,
            "source": "kedro_documentation",
            "num_chunks": num_chunks
        }

    except Exception as e:
        logger.error(f"Error in get_kedro_context: {e}")
        return {
            "error": f"Failed to get context: {str(e)}",
            "topic": topic,
            "context": "",
            "source": "error"
        }


@mcp.tool()
async def kedro_knowledge_stats() -> Dict:
    """
    Get statistics about the Kedro knowledge base.

    Useful for debugging and understanding what documentation
    has been indexed.

    Returns:
        Dict with knowledge base statistics
    """
    try:
        rag = await get_rag()

        # Get some sample chunks
        sample_results = await rag.search_docs("kedro", num_results=3)

        sample_chunks = []
        if sample_results['results']:
            sample_chunks = [
                {
                    "chunk_id": r['chunk_id'],
                    "preview": r['content'][:100] + "..."
                }
                for r in sample_results['results']
            ]

        return {
            "total_chunks": rag.collection.count(),
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dimensions": 384,
            "persist_directory": rag.client._settings.persist_directory,
            "sample_chunks": sample_chunks,
            "status": "operational"
        }

    except Exception as e:
        logger.error(f"Error in kedro_knowledge_stats: {e}")
        return {
            "error": f"Failed to get stats: {str(e)}",
            "status": "error"
        }


@mcp.tool()
async def rebuild_kedro_knowledge() -> Dict:
    """
    Force rebuild the knowledge base from scratch.

    Use this when the Kedro documentation has been updated
    or if you want to refresh the indexed content.

    Returns:
        Dict with rebuild status
    """
    global rag_system

    try:
        logger.info("Force rebuilding knowledge base...")

        # Clear existing instance
        rag_system = None

        # Reinitialise
        rag = await get_rag()

        # Clear existing collection
        rag.client.delete_collection("kedro_knowledge")
        rag.collection = rag.client.create_collection("kedro_knowledge")

        # Rebuild
        await rag.build_knowledge_base()

        return {
            "status": "success",
            "message": f"Knowledge base rebuilt with {rag.collection.count()} chunks",
            "chunks": rag.collection.count()
        }

    except Exception as e:
        logger.error(f"Error rebuilding knowledge base: {e}")
        return {
            "status": "error",
            "message": f"Failed to rebuild: {str(e)}"
        }


if __name__ == "__main__":
    # Run MCP server
    mcp.run(transport='stdio')
