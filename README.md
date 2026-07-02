# paperless-mcp

MCP server for [Paperless-ngx](https://docs.paperless-ngx.com/) using the **streamable HTTP** transport protocol.

## Features

### Resources
| URI | Description |
|---|---|
| `paperless://openapi` | Full OpenAPI spec for the Paperless-ngx REST API |
| `paperless://server` | Configured server base URL |
| `paperless://token` | API auth token |

### Tools (read-only)
- `list_documents` — list documents with filters (tag, correspondent, document type, full-text query)
- `get_document` — retrieve a single document with all metadata
- `get_document_content` — retrieve extracted text content of a document
- `get_document_suggestions` — AI-generated metadata suggestions for a document
- `list_tags` — list all tags
- `list_correspondents` — list all correspondents
- `list_document_types` — list all document types
- `list_workflows` — list all sorting workflows
- `list_workflow_triggers` — list all workflow triggers
- `list_workflow_actions` — list all workflow actions

### Tools (write — metadata and workflow creation)
- `create_tag` — create a new tag
- `create_correspondent` — create a new correspondent
- `create_document_type` — create a new document type
- `create_workflow_trigger` — create a workflow trigger (conditions)
- `create_workflow_action` — create a workflow action (assignments)
- `create_workflow` — create a complete workflow linking triggers and actions

### Prompts
- `get_inbox_documents` — formatted overview of all inbox documents
- `get_document_data_for_rule_creation(document_id)` — detailed document data to help design a sorting rule
- `create_sorting_rule(document_id?)` — guided walkthrough for creating a sorting workflow

## Configuration

Create `~/.config/paperless-mcp/config.toml`:

```toml
[paperless]
server_url = "http://your-paperless-server:8000"
token = "your-api-token"
inbox_tag_id = 1  # ID of the tag used for the inbox view
```

Override the config path with the `PAPERLESS_MCP_CONFIG` environment variable.

## Running

```bash
# Install dependencies
uv sync

# Start the server (listens on 0.0.0.0:8000/mcp)
uv run paperless-mcp
```

The MCP endpoint is available at `http://localhost:8000/mcp` (streamable HTTP).

## Getting an API token

In Paperless-ngx, go to **Settings → Profile** and generate an API token, or use:

```bash
curl -X POST http://your-server/api/token/ \
  -d '{"username": "your-user", "password": "your-password"}' \
  -H "Content-Type: application/json"
```
