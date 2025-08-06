"""
Slack API Integration for Kedro RAG System

This module fetches messages and conversations from Slack channels
to build a knowledge base of user questions and solutions.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time

logger = logging.getLogger(__name__)


class SlackIntegration:
    """Handles Slack API integration for fetching channel data"""
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize Slack client
        
        Args:
            token: Slack Bot User OAuth Token (xoxb-...) or User OAuth Token (xoxp-...)
        """
        self.token = token or os.getenv("SLACK_BOT_TOKEN")
        if not self.token:
            raise ValueError("Slack token not provided. Set SLACK_BOT_TOKEN environment variable.")
        
        self.client = WebClient(token=self.token)
        self._validate_token()
    
    def _validate_token(self):
        """Validate the Slack token"""
        try:
            response = self.client.auth_test()
            self.bot_user_id = response.get("user_id")
            self.team_name = response.get("team")
            logger.info(f"Connected to Slack team: {self.team_name}")
        except SlackApiError as e:
            logger.error(f"Invalid Slack token: {e.response['error']}")
            raise
    
    def get_channels(self, types: str = "public_channel,private_channel") -> List[Dict[str, Any]]:
        """
        Get list of channels the bot has access to
        
        Args:
            types: Channel types to fetch (public_channel, private_channel, mpim, im)
        
        Returns:
            List of channel information dictionaries
        """
        try:
            channels = []
            cursor = None
            
            while True:
                response = self.client.conversations_list(
                    types=types,
                    cursor=cursor,
                    limit=200
                )
                
                channels.extend(response["channels"])
                
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            
            logger.info(f"Found {len(channels)} channels")
            return channels
            
        except SlackApiError as e:
            logger.error(f"Error fetching channels: {e.response['error']}")
            return []
    
    def get_channel_messages(
        self, 
        channel_id: str, 
        days_back: int = 30,
        include_threads: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetch messages from a specific channel
        
        Args:
            channel_id: Slack channel ID
            days_back: Number of days to look back for messages
            include_threads: Whether to include thread replies
        
        Returns:
            List of message dictionaries
        """
        try:
            # Calculate timestamp for N days ago
            oldest_timestamp = (datetime.now() - timedelta(days=days_back)).timestamp()
            
            messages = []
            cursor = None
            
            while True:
                response = self.client.conversations_history(
                    channel=channel_id,
                    oldest=oldest_timestamp,
                    cursor=cursor,
                    limit=200
                )
                
                batch_messages = response["messages"]
                messages.extend(batch_messages)
                
                # Fetch thread replies if requested
                if include_threads:
                    for message in batch_messages:
                        if message.get("thread_ts") and message.get("reply_count", 0) > 0:
                            thread_messages = self._get_thread_replies(channel_id, message["thread_ts"])
                            messages.extend(thread_messages)
                
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                
                # Rate limiting
                time.sleep(1)
            
            logger.info(f"Fetched {len(messages)} messages from channel {channel_id}")
            return messages
            
        except SlackApiError as e:
            logger.error(f"Error fetching messages from {channel_id}: {e.response['error']}")
            return []
    
    def _get_thread_replies(self, channel_id: str, thread_ts: str) -> List[Dict[str, Any]]:
        """Fetch replies to a thread"""
        try:
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            # Exclude the parent message (first in the list)
            return response["messages"][1:] if len(response["messages"]) > 1 else []
        except SlackApiError as e:
            logger.error(f"Error fetching thread replies: {e.response['error']}")
            return []
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information"""
        try:
            response = self.client.users_info(user=user_id)
            return response["user"]
        except SlackApiError as e:
            logger.error(f"Error fetching user info for {user_id}: {e.response['error']}")
            return {"id": user_id, "name": "Unknown User"}
    
    def format_messages_for_rag(
        self, 
        messages: List[Dict[str, Any]], 
        channel_name: str,
        filter_questions: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Format Slack messages for RAG system ingestion
        
        Args:
            messages: Raw Slack messages
            channel_name: Name of the channel
            filter_questions: Whether to filter for question-like messages
        
        Returns:
            Formatted messages for RAG system
        """
        formatted_messages = []
        user_cache = {}
        
        for message in messages:
            # Skip bot messages and system messages
            if message.get("subtype") in ["bot_message", "channel_join", "channel_leave"]:
                continue
            
            text = message.get("text", "").strip()
            if not text:
                continue
            
            # Filter for questions if requested
            if filter_questions and not self._is_question(text):
                continue
            
            # Get user info
            user_id = message.get("user", "")
            if user_id and user_id not in user_cache:
                user_cache[user_id] = self.get_user_info(user_id)
            
            user_name = user_cache.get(user_id, {}).get("real_name", "Unknown User")
            
            # Format timestamp
            ts = message.get("ts", "")
            try:
                timestamp = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                timestamp = "Unknown time"
            
            # Create formatted message
            formatted_message = {
                "content": text,
                "source": f"Slack #{channel_name}",
                "metadata": {
                    "channel": channel_name,
                    "user": user_name,
                    "timestamp": timestamp,
                    "message_type": "question" if self._is_question(text) else "message",
                    "thread_ts": message.get("thread_ts"),
                    "reply_count": message.get("reply_count", 0)
                }
            }
            
            formatted_messages.append(formatted_message)
        
        logger.info(f"Formatted {len(formatted_messages)} messages from #{channel_name}")
        return formatted_messages
    
    def _is_question(self, text: str) -> bool:
        """Check if a message appears to be a question"""
        question_indicators = [
            "?", "how do", "how to", "what is", "what are", "where is", "where are",
            "when is", "when do", "why", "which", "can i", "could i", "should i",
            "help", "issue", "problem", "error", "trouble", "stuck", "failing"
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)
    
    def export_channel_data(self, channel_id: str, output_file: str, days_back: int = 30):
        """Export channel data to JSON file"""
        try:
            # Get channel info
            channel_info = self.client.conversations_info(channel=channel_id)
            channel_name = channel_info["channel"]["name"]
            
            # Get messages
            messages = self.get_channel_messages(channel_id, days_back)
            formatted_messages = self.format_messages_for_rag(messages, channel_name)
            
            # Export to file
            export_data = {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "export_date": datetime.now().isoformat(),
                "days_back": days_back,
                "message_count": len(formatted_messages),
                "messages": formatted_messages
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(formatted_messages)} messages to {output_file}")
            return export_data
            
        except SlackApiError as e:
            logger.error(f"Error exporting channel data: {e.response['error']}")
            return None


def main():
    """Example usage of SlackIntegration"""
    # This is for testing purposes
    slack = SlackIntegration()
    
    # List channels
    channels = slack.get_channels()
    print("Available channels:")
    for channel in channels[:10]:  # Show first 10
        print(f"  - {channel['name']} ({channel['id']})")
    
    # Example: Export data from a specific channel
    if channels:
        channel_id = channels[0]['id']
        channel_name = channels[0]['name']
        output_file = f"slack_export_{channel_name}.json"
        
        print(f"\nExporting data from #{channel_name}...")
        slack.export_channel_data(channel_id, output_file, days_back=7)
        print(f"Data exported to {output_file}")


if __name__ == "__main__":
    main()
