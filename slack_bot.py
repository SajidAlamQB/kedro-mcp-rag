"""
Slack Bot Integration for Kedro RAG Assistant

This bot connects to Slack and uses the Kedro RAG system to answer questions.
"""

import os
import asyncio
import logging
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from kedro_rag import KedroRAG
import tempfile

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Slack app
app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))

# Global RAG instance
rag_system = None

async def get_rag():
    """Initialize or get existing RAG system"""
    global rag_system
    if rag_system is None:
        try:
            # Use the same directory as your MCP server
            persist_directory = os.path.join(os.path.dirname(__file__), "kedro_knowledge_db")
            os.makedirs(persist_directory, exist_ok=True)
            
            logger.info(f"Initializing RAG system at {persist_directory}")
            rag_system = KedroRAG(persist_directory=persist_directory)
            
            # Check if we need to build knowledge base
            collection_count = rag_system.collection.count()
            if collection_count == 0:
                logger.info("Building knowledge base from scratch...")
                await rag_system.build_knowledge_base()
                logger.info(f"Knowledge base built with {rag_system.collection.count()} chunks")
            else:
                logger.info(f"Using existing knowledge base with {collection_count} chunks")
                
        except Exception as e:
            logger.error(f"Failed to initialize RAG system: {e}")
            raise
    
    return rag_system

@app.event("app_mention")
async def handle_mention(event, say):
    """Handle when the bot is mentioned in a channel"""
    try:
        # Get the user's question (remove the bot mention)
        text = event['text']
        # Remove the bot mention from the text
        words = text.split()
        if words and words[0].startswith('<@'):
            question = ' '.join(words[1:])
        else:
            question = text
            
        if not question.strip():
            await say("Hi! Ask me anything about Kedro and I'll help you find the answer!")
            return
            
        logger.info(f"Received question: {question}")
        
        # Get RAG system and search for answer
        rag = await get_rag()
        
        # Search for relevant information
        results = rag.search(question, top_k=3)
        
        if not results:
            await say("I couldn't find relevant information to answer your question. Could you try rephrasing it?")
            return
            
        # Format the response
        answer_parts = []
        answer_parts.append(f"**Answer to: {question}**\n")
        
        for i, result in enumerate(results, 1):
            content = result['content'][:500] + "..." if len(result['content']) > 500 else result['content']
            source = result.get('source', 'Unknown')
            answer_parts.append(f"**{i}.** {content}")
            if source != 'Unknown':
                answer_parts.append(f"   *Source: {source}*")
            answer_parts.append("")
            
        response = "\n".join(answer_parts)
        
        await say(response)
        logger.info("Response sent successfully")
        
    except Exception as e:
        logger.error(f"Error handling mention: {e}")
        await say("Sorry, I encountered an error while processing your request. Please try again.")

@app.event("message")
async def handle_message(event, say):
    """Handle direct messages to the bot"""
    # Only respond to direct messages (not channel messages)
    if event.get('channel_type') == 'im':
        question = event['text']
        
        if not question.strip():
            await say("Hi! Ask me anything about Kedro and I'll help you find the answer!")
            return
            
        try:
            logger.info(f"Received DM: {question}")
            
            # Get RAG system and search for answer
            rag = await get_rag()
            
            # Search for relevant information
            results = rag.search(question, top_k=3)
            
            if not results:
                await say("I couldn't find relevant information to answer your question. Could you try rephrasing it?")
                return
                
            # Format the response
            answer_parts = []
            answer_parts.append(f"**Answer to: {question}**\n")
            
            for i, result in enumerate(results, 1):
                content = result['content'][:500] + "..." if len(result['content']) > 500 else result['content']
                source = result.get('source', 'Unknown')
                answer_parts.append(f"**{i}.** {content}")
                if source != 'Unknown':
                    answer_parts.append(f"   *Source: {source}*")
                answer_parts.append("")
                
            response = "\n".join(answer_parts)
            
            await say(response)
            logger.info("DM response sent successfully")
            
        except Exception as e:
            logger.error(f"Error handling DM: {e}")
            await say("Sorry, I encountered an error while processing your request. Please try again.")

@app.command("/kedro")
async def handle_kedro_command(ack, respond, command):
    """Handle the /kedro slash command"""
    await ack()
    
    question = command['text']
    
    if not question.strip():
        await respond("Please provide a question. Example: `/kedro how do I create a pipeline?`")
        return
        
    try:
        logger.info(f"Received slash command: {question}")
        
        # Get RAG system and search for answer
        rag = await get_rag()
        
        # Search for relevant information
        results = rag.search(question, top_k=3)
        
        if not results:
            await respond("I couldn't find relevant information to answer your question. Could you try rephrasing it?")
            return
            
        # Format the response
        answer_parts = []
        answer_parts.append(f"**Answer to: {question}**\n")
        
        for i, result in enumerate(results, 1):
            content = result['content'][:500] + "..." if len(result['content']) > 500 else result['content']
            source = result.get('source', 'Unknown')
            answer_parts.append(f"**{i}.** {content}")
            if source != 'Unknown':
                answer_parts.append(f"   *Source: {source}*")
            answer_parts.append("")
            
        response = "\n".join(answer_parts)
        
        await respond(response)
        logger.info("Slash command response sent successfully")
        
    except Exception as e:
        logger.error(f"Error handling slash command: {e}")
        await respond("Sorry, I encountered an error while processing your request. Please try again.")

async def main():
    """Main function to start the bot"""
    try:
        # Initialize the RAG system
        await get_rag()
        
        # Start the socket mode handler
        handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        await handler.start_async()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
