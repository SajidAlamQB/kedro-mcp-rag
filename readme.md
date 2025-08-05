<img width="1005" height="738" alt="image" src="https://github.com/user-attachments/assets/5fdcdbfe-c59a-4c38-9383-08cd47ab5f6e" /># Kedro RAG MCP

## Prerequisites

- Python 3.8+
- Claude Desktop app (Get from website)

## Step 1: Clone and Set Up the Project

```bash
# Clone your repository
git clone https://github.com/your-username/kedro-mcp-rag.git
cd kedro-mcp-rag

# Create a virtual environment (using conda) 
conda create -n kedro-rag python=3.12 -y
conda activate kedro-rag

# Or using venv
python -m venv venv
source venv/bin/activate
```

## Step 2: Install Dependencies

```bash
# Install the RAG system dependencies
pip install -r requirements.txt
```

## Step 3: Set Up Kedro Documentation with llms.txt

### 3.1 Clone Kedro Repository (if not already done)

### 3.2 Update mkdocs.yml Configuration (if not already done)

The Kedro `mkdocs.yml` should have the llmstxt plugin configured:

```yaml
plugins:
  # ... other plugins ...
  - llmstxt:
      markdown_description: |
        Kedro is an open-source Python framework for creating reproducible, maintainable, and modular data science code. 
        # ... rest of description ...
      full_output: llms-full.txt
      sections:
        # ... sections configuration ...
```

### 3.3 Serve the Documentation

```bash
# In the kedro directory
make serve-docs
```

This will:
- Start the documentation server at `http://127.0.0.1:8000`
- Generate the `llms-full.txt` file at `http://127.0.0.1:8000/en/stable/llms-full.txt`

**Important**: Keep this server running while using the RAG system!

## Step 4: Configure Claude Desktop

### 4.1 Locate Claude Desktop Config

The config file location varies by OS:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

### 4.2 Update the Configuration

Edit `claude_desktop_config.json` and add your MCP server configuration:

```json
{
  "mcpServers": {
    "kedro-assistant": {
      "command": "/path/to/your/python",
      "args": ["/path/to/kedro-mcp-rag/kedro_mcp.py"],
      "env": {
        "PYTHONPATH": "/path/to/kedro-mcp-rag/"
      }
    }
  }
}
```

Replace the paths with your actual paths. For example:
- **macOS with Anaconda**:
  ```json
  {
    "mcpServers": {
      "kedro-assistant": {
        "command": "/Users/YourName/anaconda3/envs/kedro-rag/bin/python",
        "args": ["/Users/YourName/GitHub/kedro-mcp-rag/kedro_mcp.py"],
        "env": {
          "PYTHONPATH": "/Users/YourName/GitHub/kedro-mcp-rag/"
        }
      }
    }
  }
  ```

To find the correct Python path:
```bash
# With conda environment activated
which python  # macOS/Linux

# Or
conda info --envs  # Shows all conda environments
```

## Step 5: Test the Setup


### 5.1 Restart Claude Desktop

1. Completely quit Claude Desktop
2. Restart Claude Desktop
3. The MCP tools should now be available
4. Ask it a kedro related question and it will use the tools to build knowledge DB at `/tmp/kedro_knowledge_db` if it doesn't already exist.

