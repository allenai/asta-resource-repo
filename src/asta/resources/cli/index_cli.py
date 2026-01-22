#!/usr/bin/env python3
"""
Command-line interface for managing the local document metadata index.
"""

import argparse
import asyncio
import json
import sys

from ..config import load_config
from ..model import DocumentMetadata
from ..exceptions import ValidationError, DocumentServiceError


def format_document(doc: DocumentMetadata, verbose: bool = False) -> str:
    """Format a document for display"""
    if verbose:
        return f"""URI: {doc.uri}
Name: {doc.name}
URL: {doc.url}
Summary: {doc.summary}
MIME Type: {doc.mime_type}
Tags: {', '.join(doc.tags) if doc.tags else '(none)'}
Created: {doc.created_at.isoformat() if doc.created_at else 'N/A'}
Modified: {doc.modified_at.isoformat() if doc.modified_at else 'N/A'}
Extra: {json.dumps(doc.extra, indent=2) if doc.extra else '(none)'}
"""
    else:
        tags_str = f"[{', '.join(doc.tags)}]" if doc.tags else ""
        return f"{doc.uri}: {doc.name} {tags_str}"


async def cmd_list(args: argparse.Namespace):
    """List all documents"""
    config = load_config()
    store = config.storage.document_store()

    async with store:
        documents = await store.list_docs()

        # Filter by tags if specified
        if args.tags:
            filter_tags = set(args.tags.split(","))
            documents = [
                doc
                for doc in documents
                if doc.tags and any(tag in filter_tags for tag in doc.tags)
            ]

        if args.json:
            # JSON output
            output = [doc.model_dump(mode="json") for doc in documents]
            print(json.dumps(output, indent=2, default=str))
        else:
            # Human-readable output
            if not documents:
                print("No documents in index.")
            else:
                print(f"Found {len(documents)} document(s):\n")
                for doc in documents:
                    print(format_document(doc, verbose=args.verbose))
                    if args.verbose and doc != documents[-1]:
                        print("-" * 60)


async def cmd_add(args: argparse.Namespace):
    """Add a new document"""
    config = load_config()
    store = config.storage.document_store()

    # Parse tags
    tags = []
    if args.tags:
        tags = [tag.strip() for tag in args.tags.split(",")]

    # Parse extra metadata
    extra = {}
    if args.extra:
        try:
            extra = json.loads(args.extra)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --extra: {e}", file=sys.stderr)
            sys.exit(1)

    # Create document metadata
    doc = DocumentMetadata(
        uri="",  # Will be generated
        name=args.name,
        url=args.url,
        summary=args.summary,
        mime_type=args.mime_type,
        tags=tags,
        extra=extra if extra else None,
    )

    try:
        async with store:
            uri = await store.store(doc)

            if args.json:
                doc.uri = uri
                print(json.dumps(doc.model_dump(mode="json"), indent=2, default=str))
            else:
                print(f"✓ Document added: {uri}")
                print(f"  Name: {args.name}")
                print(f"  URL: {args.url}")
                if tags:
                    print(f"  Tags: {', '.join(tags)}")

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_get(args: argparse.Namespace):
    """Get a document by URI"""
    config = load_config()
    store = config.storage.document_store()

    try:
        async with store:
            doc = await store.get(args.uri)

            if doc is None:
                print(f"Document not found: {args.uri}", file=sys.stderr)
                sys.exit(1)

            if args.json:
                print(json.dumps(doc.model_dump(mode="json"), indent=2, default=str))
            else:
                print(format_document(doc, verbose=True))

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_search(args: argparse.Namespace):
    """Search documents"""
    config = load_config()
    store = config.storage.document_store()

    try:
        async with store:
            hits = await store.search(args.query, limit=args.limit)

            if args.json:
                output = [hit.model_dump(mode="json") for hit in hits]
                print(json.dumps(output, indent=2, default=str))
            else:
                if not hits:
                    print(f"No matches found for: {args.query}")
                else:
                    print(f"Found {len(hits)} match(es) for '{args.query}':\n")
                    for hit in hits:
                        print(format_document(hit.result, verbose=args.verbose))
                        if args.verbose and hit != hits[-1]:
                            print("-" * 60)

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_remove(args: argparse.Namespace):
    """Remove a document by URI"""
    config = load_config()
    store = config.storage.document_store()

    try:
        async with store:
            deleted = await store.delete(args.uri)

            if deleted:
                if args.json:
                    print(json.dumps({"status": "deleted", "uri": args.uri}))
                else:
                    print(f"✓ Document removed: {args.uri}")
            else:
                if args.json:
                    print(json.dumps({"status": "not_found", "uri": args.uri}))
                else:
                    print(f"Document not found: {args.uri}", file=sys.stderr)
                    sys.exit(1)

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_show(args: argparse.Namespace):
    """Show index information"""
    config = load_config()
    store = config.storage.document_store()

    async with store:
        documents = await store.list_docs()

        if args.json:
            info = {
                "index_path": str(getattr(store, "index_path", "N/A")),
                "namespace": getattr(store, "namespace", "N/A"),
                "resource_type": getattr(store, "resource_type", "N/A"),
                "total_documents": len(documents),
            }
            print(json.dumps(info, indent=2))
        else:
            print("Document Index Information")
            print("=" * 60)
            print(f"Index path: {getattr(store, 'index_path', 'N/A')}")
            print(f"Namespace: {getattr(store, 'namespace', 'N/A')}")
            print(f"Resource type: {getattr(store, 'resource_type', 'N/A')}")
            print(f"Total documents: {len(documents)}")


def main():
    """Main entry point for asta-index CLI"""
    parser = argparse.ArgumentParser(
        description="Manage the local document metadata index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all documents
  asta-index list

  # List documents with specific tags
  asta-index list --tags="ai,research"

  # Add a document
  asta-index add https://arxiv.org/pdf/1706.03762.pdf \\
    --name="Attention Is All You Need" \\
    --summary="Transformer architecture paper" \\
    --tags="ai,research,transformers" \\
    --mime-type="application/pdf"

  # Search documents
  asta-index search "transformer"

  # Get specific document
  asta-index get asta://local-index/document/UUID

  # Remove document
  asta-index remove asta://local-index/document/UUID

  # Show index information
  asta-index show
""",
    )

    # Global options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--index-path",
        help="Override index file path (default: from config)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list command
    list_parser = subparsers.add_parser("list", help="List all documents")
    list_parser.add_argument(
        "--tags",
        help="Filter by tags (comma-separated)",
    )
    list_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed information",
    )
    list_parser.set_defaults(func=cmd_list)

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new document")
    add_parser.add_argument("url", help="URL where document is located")
    add_parser.add_argument("--name", required=True, help="Document name/title")
    add_parser.add_argument(
        "--summary", required=True, help="Document summary description"
    )
    add_parser.add_argument(
        "--mime-type",
        default="application/pdf",
        help="MIME type (default: application/pdf)",
    )
    add_parser.add_argument(
        "--tags",
        help="Tags (comma-separated)",
    )
    add_parser.add_argument(
        "--extra",
        help="Extra metadata as JSON string",
    )
    add_parser.set_defaults(func=cmd_add)

    # get command
    get_parser = subparsers.add_parser("get", help="Get document by URI")
    get_parser.add_argument("uri", help="Document URI")
    get_parser.set_defaults(func=cmd_get)

    # search command
    search_parser = subparsers.add_parser("search", help="Search documents")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum results (default: 10)",
    )
    search_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed information",
    )
    search_parser.set_defaults(func=cmd_search)

    # remove command
    remove_parser = subparsers.add_parser("remove", help="Remove document by URI")
    remove_parser.add_argument("uri", help="Document URI to remove")
    remove_parser.set_defaults(func=cmd_remove)

    # show command
    show_parser = subparsers.add_parser("show", help="Show index information")
    show_parser.set_defaults(func=cmd_show)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Override index path if specified
    if args.index_path:
        import os

        os.environ["INDEX_PATH"] = args.index_path

    # Run the command
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
