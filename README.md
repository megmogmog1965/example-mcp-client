# example-mcp-client

## Getting Started

You need to install `uv` to run this project.

```bash
brew install uv
```

Create a `.env` file with your API key.

```bash
echo "ANTHROPIC_API_KEY=<your key here>" > .env
```

Create a virtual environment and install the dependencies.

```bash
uv venv
source .venv/bin/activate
uv sync
```

## Usage

Run the client with arguments for the server.

```bash
source .venv/bin/activate
uv run client.py npx -y @modelcontextprotocol/server-filesystem "/Users/{username}/Desktop/"
```
