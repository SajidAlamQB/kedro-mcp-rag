"""
RAG approach with MCP server
"""

from typing import Dict
from mcp.server.fastmcp import FastMCP
from kedro_rag import KedroRAG, KedroMCPNodes
import os
import sys
import tempfile

mcp = FastMCP("kedro-assistant")

# Global RAG instance
rag_system = None
nodes_adapter = None


async def get_rag():
    """Initialise or get existing RAG system"""
    global rag_system, nodes_adapter
    if rag_system is None:

        temp_dir = os.path.join(tempfile.gettempdir(), "kedro_knowledge_db")
        rag_system = KedroRAG(persist_directory=temp_dir)

        # Check if we need to build knowledge base
        if rag_system.collection.count() == 0:
            await rag_system.build_knowledge_base()
        else:
            print(f"Using existing knowledge base with {rag_system.collection.count()} chunks", file=sys.stderr)

        nodes_adapter = KedroMCPNodes(rag_system)

    return rag_system, nodes_adapter


@mcp.tool()
async def search_kedro_docs(query: str, num_results: int = 5) -> Dict:
    """
    Search Kedro documentation using RAG (adapted from colleague's implementation).

    This is similar to the vector store search in the original chatbot,
    but optimized for Kedro docs instead of Slack messages.
    """
    _, nodes = await get_rag()
    return await nodes.search_kedro_docs(query)


@mcp.tool()
async def answer_kedro_question(question: str) -> Dict:
    """
    Get an AI-powered answer using RAG + LLM.

    Note: Requires OPENAI_API_KEY environment variable.
    """
    _, nodes = await get_rag()

    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "error": "Please set OPENAI_API_KEY environment variable",
            "question": question
        }

    try:
        return await nodes.answer_kedro_question(question, api_key)
    except Exception as e:
        return {
            "error": str(e),
            "question": question
        }


@mcp.tool()
async def get_kedro_context(topic: str) -> Dict:
    """
    Get relevant context about a Kedro topic (similar to get_context_from_vector_store).

    This is a simpler version that just returns the context without LLM processing.
    """
    rag, _ = await get_rag()
    tool = rag.create_retrieval_tool()

    context = tool.invoke(topic)

    return {
        "topic": topic,
        "context": context,
        "source": "kedro_documentation"
    }


@mcp.tool()
async def kedro_rag_stats() -> Dict:
    """
    Get statistics about the knowledge base (useful for debugging).
    """
    rag, _ = await get_rag()

    # Get some sample chunks to show what's indexed
    sample_results = rag.collection.query(
        query_embeddings=[rag.embedder.encode("kedro").tolist()],
        n_results=3
    )

    return {
        "total_chunks": rag.collection.count(),
        "embedding_model": "all-MiniLM-L6-v2",
        "sample_chunks": [
            doc[:100] + "..." for doc in sample_results['documents'][0]
        ] if sample_results['documents'] else []
    }


# Main entry point - removed async to simplify
if __name__ == "__main__":
    # Print to stderr so it doesn't interfere with MCP protocol
    print("Starting Kedro MCP Server with RAG...", file=sys.stderr)
    print("Based on colleague's Kedro RAG chatbot implementation", file=sys.stderr)

    # Run MCP server directly
    mcp.run(transport='stdio')
