"""Kedro RAG MCP Server"""

from typing import Dict
from mcp.server.fastmcp import FastMCP
from kedro_rag import KedroRAG
import os
import sys
import tempfile
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Add multiprocessing settings for better macOS compatibility
import multiprocessing
multiprocessing.set_start_method('spawn', force=True)

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
            try:
                collection_count = rag_system.collection.count()
                if collection_count == 0:
                    logger.info("Building knowledge base from scratch...")
                    await rag_system.build_knowledge_base()
                    logger.info(f"Knowledge base built with {rag_system.collection.count()} chunks")
                else:
                    logger.info(f"Using existing knowledge base with {collection_count} chunks")
            except Exception as kb_error:
                logger.warning(f"Could not build knowledge base: {kb_error}")
                logger.info("Continuing with empty knowledge base")

        except Exception as e:
            logger.error(f"Failed to initialise RAG system: {e}")
            # Create a minimal fallback system
            rag_system = None
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


@mcp.tool()
async def add_slack_channel_data(channel_id: str, days_back: int = 30) -> Dict:
    """
    Fetch messages from a Slack channel and add them to the knowledge base.
    
    This tool connects to Slack API and fetches user messages, questions,
    and discussions from a specified channel to enhance the RAG system
    with real user interactions and solutions.
    
    Args:
        channel_id: Slack channel ID (e.g., "C1234567890")
        days_back: Number of days to look back for messages (default: 30)
        
    Returns:
        Dict with status and details about imported messages
        
    Note:
        Requires SLACK_BOT_TOKEN environment variable to be set.
        The bot must have access to read the specified channel.
    """
    try:
        rag = await get_rag()
        result = await rag.fetch_and_store_slack_data(channel_id, days_back)
        
        if "error" in result:
            return {
                "status": "error",
                "message": result["error"]
            }
        
        return {
            "status": "success",
            "message": f"Added {result['messages_added']} messages from #{result['channel_name']}",
            "channel_name": result["channel_name"],
            "messages_added": result["messages_added"],
            "total_messages_fetched": result["total_messages_fetched"]
        }
        
    except Exception as e:
        logger.error(f"Error adding Slack channel data: {e}")
        return {
            "status": "error",
            "message": f"Failed to add Slack data: {str(e)}"
        }


@mcp.tool()
async def list_slack_channels() -> Dict:
    """
    List available Slack channels that the bot has access to.
    
    This tool helps you discover which channels you can fetch data from.
    Only returns channels where the bot has been invited or has access.
    
    Returns:
        Dict with list of channels and their IDs
        
    Note:
        Requires SLACK_BOT_TOKEN environment variable to be set.
    """
    try:
        # Import here to avoid dependency issues if slack-sdk not installed
        from slack_integration import SlackIntegration
        
        slack = SlackIntegration()
        channels = slack.get_channels()
        
        # Format channel list
        channel_list = []
        for channel in channels:
            channel_list.append({
                "id": channel["id"],
                "name": channel["name"],
                "is_private": channel.get("is_private", False),
                "member_count": channel.get("num_members", 0)
            })
        
        return {
            "status": "success",
            "channels": channel_list,
            "total_channels": len(channel_list)
        }
        
    except ImportError:
        return {
            "status": "error",
            "message": "Slack integration not available. Install slack-sdk first: pip install slack-sdk"
        }
    except Exception as e:
        logger.error(f"Error listing Slack channels: {e}")
        return {
            "status": "error",
            "message": f"Failed to list channels: {str(e)}"
        }


@mcp.tool()
async def search_with_source_filter(query: str, source: str = None, top_k: int = 5) -> Dict:
    """
    Search the knowledge base with optional source filtering.
    
    This enhanced search allows you to filter results by source type,
    such as 'kedro_docs' for documentation or 'slack' for user discussions.
    
    Args:
        query: Search query
        source: Filter by source type ('kedro_docs', 'slack', or None for all)
        top_k: Number of results to return (default: 5)
        
    Returns:
        Dict with search results including source information
    """
    try:
        rag = await get_rag()
        results = rag.search(query, source_filter=source, top_k=top_k)
        
        return {
            "status": "success",
            "query": query,
            "source_filter": source,
            "results": results,
            "total_results": len(results)
        }
        
    except Exception as e:
        logger.error(f"Error searching with source filter: {e}")
        return {
            "status": "error",
            "message": f"Search failed: {str(e)}"
        }


if __name__ == "__main__":
    import asyncio
    
    try:
        logger.info("Starting Kedro RAG MCP server...")
        # Run the MCP server
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server failed: {e}")
        sys.exit(1)
