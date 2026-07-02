"""Paperless-ngx MCP Server.

Provides MCP resources, tools, and prompts for interacting with a
Paperless-ngx document management system via the streamable HTTP transport.

Configuration is loaded from the path specified by the PAPERLESS_MCP_CONFIG
environment variable, defaulting to ~/.config/paperless-mcp/config.toml.

Example config.toml:
    [paperless]
    server_url = "http://localhost:8000"
    token = "your-api-token"
    inbox_tag_id = 1
"""

from __future__ import annotations

import tomllib
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "paperless-mcp" / "config.toml"
CONFIG_PATH = Path(os.environ.get("PAPERLESS_MCP_CONFIG", _DEFAULT_CONFIG_PATH))
OPENAPI_PATH = Path(__file__).parent / "doc" / "openapi.json"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load and validate configuration from the TOML config file.

    Returns a dict with keys: server_url, token, inbox_tag_id.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required keys are missing.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_PATH}\n"
            "Create it with the following content:\n"
            "  [paperless]\n"
            '  server_url = "http://localhost:8000"\n'
            '  token = "your-api-token"\n'
            "  inbox_tag_id = 1\n"
            "\n"
            "Override the path with: PAPERLESS_MCP_CONFIG=/path/to/config.toml"
        )
    with CONFIG_PATH.open("rb") as fh:
        data = tomllib.load(fh)

    section = data.get("paperless", {})
    required_keys = ("server_url", "token", "inbox_tag_id")
    missing = [k for k in required_keys if k not in section]
    if missing:
        raise ValueError(
            f"Missing required keys in [paperless] section of {CONFIG_PATH}: {missing}"
        )
    return {
        "server_url": str(section["server_url"]).rstrip("/"),
        "token": str(section["token"]),
        "inbox_tag_id": int(section["inbox_tag_id"]),
    }


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------


def _make_client(cfg: dict[str, Any]) -> httpx.AsyncClient:
    """Return a pre-configured async HTTP client for the Paperless-ngx API."""
    return httpx.AsyncClient(
        base_url=cfg["server_url"],
        headers={
            "Authorization": f"Token {cfg['token']}",
            "Accept": "application/json",
        },
        timeout=30.0,
    )


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Perform a GET request and return the parsed JSON response body."""
    response = await client.get(path, params=params)
    response.raise_for_status()
    return response.json()


async def _post(
    client: httpx.AsyncClient,
    path: str,
    data: dict[str, Any],
) -> Any:
    """Perform a POST request with a JSON body and return the parsed response."""
    response = await client.post(path, json=data)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

config = load_config()

mcp = FastMCP(
    name="paperless-mcp",
    instructions=(
        "MCP server for Paperless-ngx document management. "
        "Use read-only tools to inspect documents, tags, correspondents, document types, "
        "and existing workflows. Use write tools to create new tags, correspondents, "
        "document types, and sorting workflows. "
        "Use prompts to get an overview of inbox documents, inspect a specific document "
        "for rule creation, or get a guided walkthrough for creating a sorting rule."
    ),
    host="0.0.0.0",
    port=8000,
)

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("paperless://openapi")
def get_openapi_spec() -> str:
    """Full OpenAPI specification for the Paperless-ngx REST API."""
    return OPENAPI_PATH.read_text(encoding="utf-8")


@mcp.resource("paperless://server")
def get_server_url() -> str:
    """Configured Paperless-ngx server base URL."""
    return config["server_url"]


@mcp.resource("paperless://token")
def get_auth_token() -> str:
    """API token used to authenticate with the Paperless-ngx server."""
    return config["token"]


# ---------------------------------------------------------------------------
# Tools — read-only queries
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_documents(
    page: int = 1,
    page_size: int = 25,
    tags_id_all: str | None = None,
    correspondent_id: int | None = None,
    document_type_id: int | None = None,
    query: str | None = None,
    ordering: str = "-created",
) -> dict[str, Any]:
    """List documents from Paperless-ngx with optional filters.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 25, max 100).
        tags_id_all: Comma-separated tag IDs; only documents with ALL these tags.
        correspondent_id: Filter by correspondent ID.
        document_type_id: Filter by document type ID.
        query: Full-text search query string.
        ordering: Sort field (e.g. '-created', 'title'). Default is newest first.
    """
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "ordering": ordering,
    }
    if tags_id_all:
        params["tags__id__all"] = tags_id_all
    if correspondent_id is not None:
        params["correspondent__id"] = correspondent_id
    if document_type_id is not None:
        params["document_type__id"] = document_type_id
    if query:
        params["query"] = query

    async with _make_client(config) as client:
        return await _get(client, "/api/documents/", params)


@mcp.tool()
async def get_document(document_id: int) -> dict[str, Any]:
    """Retrieve a single document with all its metadata.

    Args:
        document_id: The unique integer ID of the document.
    """
    async with _make_client(config) as client:
        return await _get(client, f"/api/documents/{document_id}/")


@mcp.tool()
async def get_document_content(document_id: int) -> dict[str, Any]:
    """Retrieve a document's extracted text content and key metadata for analysis.

    Returns id, title, content (full text), correspondent, document_type, tags,
    created date, and original_filename.

    Args:
        document_id: The unique integer ID of the document.
    """
    async with _make_client(config) as client:
        doc = await _get(client, f"/api/documents/{document_id}/")
    return {
        "id": doc["id"],
        "title": doc["title"],
        "content": doc.get("content", ""),
        "correspondent": doc.get("correspondent"),
        "document_type": doc.get("document_type"),
        "tags": doc.get("tags", []),
        "created": doc.get("created"),
        "original_filename": doc.get("original_filename"),
    }


@mcp.tool()
async def get_document_suggestions(document_id: int) -> dict[str, Any]:
    """Get AI-generated metadata suggestions for a document.

    Returns suggested correspondent, document_types, tags, and storage_paths.

    Args:
        document_id: The unique integer ID of the document.
    """
    async with _make_client(config) as client:
        return await _get(client, f"/api/documents/{document_id}/suggestions/")


@mcp.tool()
async def list_tags(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    """List all tags defined in Paperless-ngx.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 100).
    """
    async with _make_client(config) as client:
        return await _get(client, "/api/tags/", {"page": page, "page_size": page_size})


@mcp.tool()
async def list_correspondents(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    """List all correspondents (senders/recipients) in Paperless-ngx.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 100).
    """
    async with _make_client(config) as client:
        return await _get(
            client, "/api/correspondents/", {"page": page, "page_size": page_size}
        )


@mcp.tool()
async def list_document_types(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    """List all document types defined in Paperless-ngx.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 100).
    """
    async with _make_client(config) as client:
        return await _get(
            client, "/api/document_types/", {"page": page, "page_size": page_size}
        )


@mcp.tool()
async def list_workflows(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    """List all sorting and automation workflows in Paperless-ngx.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 100).
    """
    async with _make_client(config) as client:
        return await _get(
            client, "/api/workflows/", {"page": page, "page_size": page_size}
        )


@mcp.tool()
async def list_workflow_triggers(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    """List all workflow triggers.

    Triggers define when a workflow is activated, e.g. on document consumption
    matching certain filename patterns or tag criteria.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 100).
    """
    async with _make_client(config) as client:
        return await _get(
            client, "/api/workflow_triggers/", {"page": page, "page_size": page_size}
        )


@mcp.tool()
async def list_workflow_actions(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    """List all workflow actions.

    Actions define what happens when a workflow is triggered, e.g. assign a
    correspondent, document type, or set of tags.

    Args:
        page: Page number (default 1).
        page_size: Results per page (default 100).
    """
    async with _make_client(config) as client:
        return await _get(
            client, "/api/workflow_actions/", {"page": page, "page_size": page_size}
        )


# ---------------------------------------------------------------------------
# Tools — write operations (metadata and workflow creation)
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_tag(
    name: str,
    color: str = "#a6cee3",
    is_inbox_tag: bool = False,
    matching_algorithm: int = 0,
    match: str = "",
    is_insensitive: bool = True,
) -> dict[str, Any]:
    """Create a new tag in Paperless-ngx.

    Args:
        name: Display name for the tag.
        color: Hex color code (default light blue #a6cee3).
        is_inbox_tag: If True, documents with this tag appear in the inbox view.
        matching_algorithm: 0=None, 1=Any word, 2=All words, 3=Exact, 4=Regex,
            5=Fuzzy, 6=Auto.
        match: String or pattern for automatic document matching.
        is_insensitive: Whether matching is case-insensitive (default True).
    """
    async with _make_client(config) as client:
        return await _post(
            client,
            "/api/tags/",
            {
                "name": name,
                "color": color,
                "is_inbox_tag": is_inbox_tag,
                "matching_algorithm": matching_algorithm,
                "match": match,
                "is_insensitive": is_insensitive,
            },
        )


@mcp.tool()
async def create_correspondent(
    name: str,
    matching_algorithm: int = 0,
    match: str = "",
    is_insensitive: bool = True,
) -> dict[str, Any]:
    """Create a new correspondent in Paperless-ngx.

    Args:
        name: Display name for the correspondent.
        matching_algorithm: 0=None, 1=Any word, 2=All words, 3=Exact, 4=Regex,
            5=Fuzzy, 6=Auto.
        match: String or pattern for automatic document matching.
        is_insensitive: Whether matching is case-insensitive (default True).
    """
    async with _make_client(config) as client:
        return await _post(
            client,
            "/api/correspondents/",
            {
                "name": name,
                "matching_algorithm": matching_algorithm,
                "match": match,
                "is_insensitive": is_insensitive,
            },
        )


@mcp.tool()
async def create_document_type(
    name: str,
    matching_algorithm: int = 0,
    match: str = "",
    is_insensitive: bool = True,
) -> dict[str, Any]:
    """Create a new document type in Paperless-ngx.

    Args:
        name: Display name for the document type.
        matching_algorithm: 0=None, 1=Any word, 2=All words, 3=Exact, 4=Regex,
            5=Fuzzy, 6=Auto.
        match: String or pattern for automatic document matching.
        is_insensitive: Whether matching is case-insensitive (default True).
    """
    async with _make_client(config) as client:
        return await _post(
            client,
            "/api/document_types/",
            {
                "name": name,
                "matching_algorithm": matching_algorithm,
                "match": match,
                "is_insensitive": is_insensitive,
            },
        )


@mcp.tool()
async def create_workflow_trigger(
    trigger_type: int,
    sources: list[int] | None = None,
    filter_filename: str = "",
    filter_path: str = "",
    filter_has_tags: list[int] | None = None,
    filter_has_all_tags: list[int] | None = None,
    filter_has_not_tags: list[int] | None = None,
    filter_has_correspondent: int | None = None,
    filter_has_document_type: int | None = None,
    matching_algorithm: int = 0,
    match: str = "",
    is_insensitive: bool = True,
) -> dict[str, Any]:
    """Create a workflow trigger that defines when a workflow is activated.

    Args:
        trigger_type: 1=Consumption Started, 2=Document Added,
            3=Document Updated, 4=Scheduled.
        sources: Source IDs (1=Consume folder, 2=API upload, 3=Mail fetch).
            Defaults to all sources.
        filter_filename: Glob pattern to match the original filename (e.g. '*invoice*').
        filter_path: Glob pattern to match the storage path.
        filter_has_tags: Tag IDs; document must have at least one of these tags.
        filter_has_all_tags: Tag IDs; document must have ALL of these tags.
        filter_has_not_tags: Tag IDs; document must NOT have any of these tags.
        filter_has_correspondent: Correspondent ID the document must have.
        filter_has_document_type: Document type ID the document must have.
        matching_algorithm: 0=None, 1=Any word, 2=All words, 3=Exact, 4=Regex,
            5=Fuzzy.
        match: Content match string or pattern.
        is_insensitive: Whether content matching is case-insensitive.
    """
    data: dict[str, Any] = {
        "type": trigger_type,
        "sources": sources or [1, 2, 3],
        "filter_filename": filter_filename,
        "filter_path": filter_path,
        "filter_has_tags": filter_has_tags or [],
        "filter_has_all_tags": filter_has_all_tags or [],
        "filter_has_not_tags": filter_has_not_tags or [],
        "matching_algorithm": matching_algorithm,
        "match": match,
        "is_insensitive": is_insensitive,
    }
    if filter_has_correspondent is not None:
        data["filter_has_correspondent"] = filter_has_correspondent
    if filter_has_document_type is not None:
        data["filter_has_document_type"] = filter_has_document_type

    async with _make_client(config) as client:
        return await _post(client, "/api/workflow_triggers/", data)


@mcp.tool()
async def create_workflow_action(
    action_type: int = 1,
    assign_title: str = "",
    assign_tags: list[int] | None = None,
    assign_correspondent: int | None = None,
    assign_document_type: int | None = None,
    assign_storage_path: int | None = None,
    remove_all_tags: bool = False,
    remove_tags: list[int] | None = None,
    remove_all_correspondents: bool = False,
    remove_correspondents: list[int] | None = None,
    remove_all_document_types: bool = False,
    remove_document_types: list[int] | None = None,
    remove_all_storage_paths: bool = False,
    remove_storage_paths: list[int] | None = None,
) -> dict[str, Any]:
    """Create a workflow action that defines what happens when a workflow fires.

    Args:
        action_type: 1=Assignment, 2=Removal, 3=Email, 4=Webhook. Default 1.
        assign_title: Title to assign (supports placeholders like {correspondent}).
        assign_tags: List of tag IDs to assign to the document.
        assign_correspondent: Correspondent ID to assign.
        assign_document_type: Document type ID to assign.
        assign_storage_path: Storage path ID to assign.
        remove_all_tags: Remove all existing tags before assigning.
        remove_tags: Specific tag IDs to remove.
        remove_all_correspondents: Remove the existing correspondent.
        remove_correspondents: Specific correspondent IDs to remove.
        remove_all_document_types: Remove the existing document type.
        remove_document_types: Specific document type IDs to remove.
        remove_all_storage_paths: Remove the existing storage path.
        remove_storage_paths: Specific storage path IDs to remove.
    """
    data: dict[str, Any] = {
        "type": action_type,
        "assign_title": assign_title,
        "assign_tags": assign_tags or [],
        "remove_all_tags": remove_all_tags,
        "remove_tags": remove_tags or [],
        "remove_all_correspondents": remove_all_correspondents,
        "remove_correspondents": remove_correspondents or [],
        "remove_all_document_types": remove_all_document_types,
        "remove_document_types": remove_document_types or [],
        "remove_all_storage_paths": remove_all_storage_paths,
        "remove_storage_paths": remove_storage_paths or [],
    }
    if assign_correspondent is not None:
        data["assign_correspondent"] = assign_correspondent
    if assign_document_type is not None:
        data["assign_document_type"] = assign_document_type
    if assign_storage_path is not None:
        data["assign_storage_path"] = assign_storage_path

    async with _make_client(config) as client:
        return await _post(client, "/api/workflow_actions/", data)


@mcp.tool()
async def create_workflow(
    name: str,
    trigger_ids: list[int],
    action_ids: list[int],
    order: int = 100,
    enabled: bool = True,
) -> dict[str, Any]:
    """Create a complete sorting workflow in Paperless-ngx.

    Triggers and actions must already exist (create them first with
    create_workflow_trigger and create_workflow_action).

    Args:
        name: Descriptive display name for the workflow.
        trigger_ids: List of existing WorkflowTrigger IDs to attach.
        action_ids: List of existing WorkflowAction IDs to attach.
        order: Execution order; lower numbers run first (default 100).
        enabled: Whether the workflow is active immediately (default True).
    """
    async with _make_client(config) as client:
        return await _post(
            client,
            "/api/workflows/",
            {
                "name": name,
                "order": order,
                "enabled": enabled,
                "triggers": trigger_ids,
                "actions": action_ids,
            },
        )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
async def get_inbox_documents() -> str:
    """Return a formatted summary of all documents currently in the inbox.

    Uses the configured inbox_tag_id to filter documents.
    """
    inbox_tag_id = config["inbox_tag_id"]
    async with _make_client(config) as client:
        result = await _get(
            client,
            "/api/documents/",
            {
                "tags__id__all": str(inbox_tag_id),
                "page_size": 50,
                "ordering": "-created",
            },
        )

    docs = result.get("results", [])
    total = result.get("count", 0)

    lines = [f"# Inbox Documents ({total} total, showing {len(docs)})\n"]
    for doc in docs:
        lines.append(f"## [{doc['id']}] {doc['title']}")
        lines.append(f"- **Created**: {doc.get('created', 'unknown')}")
        lines.append(f"- **Original filename**: {doc.get('original_filename', 'unknown')}")
        lines.append(f"- **Correspondent**: {doc.get('correspondent') or 'not set'}")
        lines.append(f"- **Document type**: {doc.get('document_type') or 'not set'}")
        tag_ids = doc.get("tags", [])
        lines.append(f"- **Tag IDs**: {tag_ids if tag_ids else 'none'}")
        lines.append("")

    return "\n".join(lines)


@mcp.prompt()
async def get_document_data_for_rule_creation(document_id: int) -> str:
    """Return detailed data for a document to assist with sorting rule creation.

    Fetches the document content, AI suggestions, and the full list of available
    tags, correspondents, and document types so the LLM can propose a rule.

    Args:
        document_id: The ID of the document to inspect.
    """
    async with _make_client(config) as client:
        doc = await _get(client, f"/api/documents/{document_id}/")
        suggestions = await _get(client, f"/api/documents/{document_id}/suggestions/")
        tags_result = await _get(client, "/api/tags/", {"page_size": 200})
        correspondents_result = await _get(
            client, "/api/correspondents/", {"page_size": 200}
        )
        doc_types_result = await _get(
            client, "/api/document_types/", {"page_size": 200}
        )

    tags_by_id: dict[int, str] = {
        t["id"]: t["name"] for t in tags_result.get("results", [])
    }
    corr_by_id: dict[int, str] = {
        c["id"]: c["name"] for c in correspondents_result.get("results", [])
    }
    dt_by_id: dict[int, str] = {
        d["id"]: d["name"] for d in doc_types_result.get("results", [])
    }

    doc_tag_names = [tags_by_id.get(t, f"#{t}") for t in doc.get("tags", [])]
    corr_name = corr_by_id.get(doc.get("correspondent"), "not set")
    dt_name = dt_by_id.get(doc.get("document_type"), "not set")

    content_preview = (doc.get("content") or "")[:2000]

    lines = [
        f"# Document {document_id}: {doc['title']}",
        "",
        "## Current Metadata",
        f"- **Correspondent**: {corr_name}",
        f"- **Document type**: {dt_name}",
        f"- **Tags**: {', '.join(doc_tag_names) or 'none'}",
        f"- **Created**: {doc.get('created', 'unknown')}",
        f"- **Original filename**: {doc.get('original_filename', 'unknown')}",
        "",
        "## Extracted Content (first 2000 chars)",
        content_preview or "(no content extracted)",
        "",
        "## AI Suggestions",
        f"- **Suggested correspondent**: {suggestions.get('correspondent')}",
        f"- **Suggested document types**: {suggestions.get('document_types', [])}",
        f"- **Suggested tags**: {suggestions.get('tags', [])}",
        "",
        f"## Available Tags ({len(tags_by_id)} total)",
        "Format: ID:Name",
        ", ".join(f"{k}:{v}" for k, v in sorted(tags_by_id.items())),
        "",
        f"## Available Correspondents ({len(corr_by_id)} total)",
        ", ".join(f"{k}:{v}" for k, v in sorted(corr_by_id.items())),
        "",
        f"## Available Document Types ({len(dt_by_id)} total)",
        ", ".join(f"{k}:{v}" for k, v in sorted(dt_by_id.items())),
    ]
    return "\n".join(lines)


@mcp.prompt()
async def create_sorting_rule(document_id: int | None = None) -> str:
    """Provide a guided walkthrough for creating a Paperless-ngx sorting workflow.

    Optionally accepts a document ID to base the rule on a specific document.

    Args:
        document_id: Optional document ID to use as the basis for the new rule.
    """
    inbox_tag_id = config["inbox_tag_id"]

    lines = [
        "# Create a Sorting Rule (Workflow)",
        "",
        "I will help you create a Paperless-ngx workflow to automatically sort documents.",
        "",
        "A complete workflow requires three steps:",
        "  1. Create a **WorkflowTrigger** — the condition that activates the rule",
        "  2. Create a **WorkflowAction** — what to do when the trigger fires",
        "  3. Create the **Workflow** — linking trigger and action together",
        "",
    ]

    if document_id is not None:
        lines += [
            f"## Reference Document: {document_id}",
            "",
            "Call `get_document_data_for_rule_creation` with this document ID to see its",
            "full content, metadata, and AI suggestions before proceeding.",
            "",
        ]

    lines += [
        "## Step 1 — Identify the Pattern",
        "",
        "What distinguishes this type of document? Choose one or more criteria:",
        "- **Filename pattern** — e.g. `*invoice*`, `Swisscom*`",
        "- **Content keywords** — specific words or phrases in the extracted text",
        "- **Sender/correspondent** — already detected by Paperless-ngx",
        "- **Currently in inbox** — filter on `filter_has_all_tags=[inbox_tag_id]`",
        "",
        "## Step 2 — Create Missing Metadata (if needed)",
        "",
        "If the correspondent, document type, or tags do not yet exist, create them:",
        "- `create_correspondent(name='...')` — for a new sender or recipient",
        "- `create_document_type(name='...')` — for a new document category",
        "- `create_tag(name='...')` — for a new tag",
        "",
        "## Step 3 — Create the Trigger",
        "",
        "Call `create_workflow_trigger` with the appropriate parameters:",
        "- `trigger_type=1` — Consumption Started (catches newly ingested documents)",
        "- `trigger_type=2` — Document Added (after full processing is complete)",
        "- `filter_filename='*pattern*'` — match by original filename",
        "- `filter_has_all_tags=[...]` — only process documents with all these tags",
        "- `matching_algorithm=4, match='regex'` — match by document content",
        "",
        "## Step 4 — Create the Action",
        "",
        "Call `create_workflow_action` with the assignment details:",
        "- `action_type=1` — Assignment action",
        "- `assign_correspondent=<id>` — set the correspondent",
        "- `assign_document_type=<id>` — set the document type",
        "- `assign_tags=[<id>, ...]` — add tags",
        "- `remove_tags=[inbox_tag_id]` — remove the inbox tag after sorting",
        "",
        "## Step 5 — Create the Workflow",
        "",
        "Call `create_workflow` with the IDs returned in steps 3 and 4:",
        "- `name='...'` — a descriptive name",
        "- `trigger_ids=[<trigger_id>]`",
        "- `action_ids=[<action_id>]`",
        "",
        f"**Configured inbox tag ID**: {inbox_tag_id}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Paperless-ngx MCP server using the streamable HTTP transport."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
