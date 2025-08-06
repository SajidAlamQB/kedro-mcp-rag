# Slack Integration Setup Guide

This guide will help you connect your MCP server to Slack API to fetch and store channel messages in your RAG knowledge base.

## Prerequisites

1. **Install Slack SDK:**
   ```bash
   cd /Users/Huong_Nguyen/dev/kedro-mcp-rag
   /opt/anaconda3/bin/pip install slack-sdk
   ```

## Step 1: Create a Slack App

1. **Go to Slack API:** https://api.slack.com/apps
2. **Create New App:**
   - Click "Create New App" → "From scratch"
   - App Name: "Kedro Knowledge Collector"
   - Select your workspace

## Step 2: Configure App Permissions

1. **Go to "OAuth & Permissions"**
2. **Add Bot Token Scopes:**
   ```
   channels:read       # View basic channel info
   channels:history    # Read message history from public channels
   groups:read         # View private channel info  
   groups:history      # Read message history from private channels
   users:read          # Read user information
   ```

3. **Install App to Workspace:**
   - Click "Install to Workspace"
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`)

## Step 3: Set Environment Variable

Create a `.env` file or set the environment variable:

```bash
# Option 1: Create .env file
echo "SLACK_BOT_TOKEN=xoxb-your-token-here" > .env

# Option 2: Export directly
export SLACK_BOT_TOKEN="xoxb-your-token-here"
```

## Step 4: Invite Bot to Channels

1. Go to the Slack channels you want to collect data from
2. Type: `/invite @Kedro Knowledge Collector`
3. The bot needs to be in the channel to read its history

## Step 5: Use MCP Tools

Once your Claude Desktop MCP server is running, you can use these new tools:

### List Available Channels
```
Please list my Slack channels
```

### Add Channel Data to Knowledge Base
```
Please fetch the last 30 days of messages from our #kedro-support channel and add them to the knowledge base
```

### Search with Source Filtering
```
Search for "pipeline error" but only show results from Slack discussions
```

## Example Usage

1. **Discover channels:**
   - The MCP server will show you all channels your bot has access to

2. **Collect support data:**
   - Import messages from channels like `#kedro-help`, `#data-engineering`, etc.
   - The system automatically filters for question-like messages

3. **Enhanced search:**
   - Search both documentation and real user discussions
   - Get context from actual user problems and solutions

## Security Notes

- **Bot Token Security:** Keep your bot token secure and don't commit it to version control
- **Channel Access:** The bot can only read channels it's invited to
- **Data Privacy:** Consider your organization's data policy before importing sensitive channels

## Troubleshooting

### Common Issues:

1. **"Slack integration not available"**
   ```bash
   /opt/anaconda3/bin/pip install slack-sdk
   ```

2. **"Invalid token"**
   - Check your `SLACK_BOT_TOKEN` environment variable
   - Ensure the token starts with `xoxb-`

3. **"Bot not in channel"**
   - Invite the bot to the channel: `/invite @your-bot-name`

4. **"No messages found"**
   - Check if there are messages in the time range
   - Verify bot has `channels:history` or `groups:history` permission

## Environment Variables

```bash
# Required
SLACK_BOT_TOKEN=xoxb-your-bot-token-here

# Optional - for your existing PYTHONPATH
PYTHONPATH=/Users/Huong_Nguyen/dev/kedro-mcp-rag/
```

After setup, your MCP server will be able to fetch Slack channel data and integrate it with your Kedro documentation for enhanced AI assistance!
