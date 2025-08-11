#!/usr/bin/env python3
"""
Setup script for Slack integration with Kedro RAG MCP server.
"""

import os
import sys
from pathlib import Path

def setup_slack_env():
    """Set up Slack environment variables."""
    print("🔧 Setting up Slack Integration for Kedro RAG")
    print("=" * 50)
    
    # Get the bot token
    bot_token = input("\n📝 Enter your Slack Bot Token (starts with xoxb-): ").strip()
    
    if not bot_token.startswith('xoxb-'):
        print("❌ Invalid token format. Bot tokens should start with 'xoxb-'")
        return False
    
    # Create .env file
    env_file = Path(__file__).parent / '.env'
    
    with open(env_file, 'w') as f:
        f.write(f"SLACK_BOT_TOKEN={bot_token}\n")
    
    print(f"\n✅ Environment file created: {env_file}")
    
    # Also set for current session
    os.environ['SLACK_BOT_TOKEN'] = bot_token
    
    print("\n🎉 Slack integration configured!")
    print("\nNext steps:")
    print("1. Restart your MCP server")
    print("2. Invite the bot to channels you want to search")
    print("3. Test with: python test_slack_integration.py")
    
    return True

if __name__ == "__main__":
    if setup_slack_env():
        print("\n✨ Setup complete!")
    else:
        print("\n❌ Setup failed!")
        sys.exit(1)
