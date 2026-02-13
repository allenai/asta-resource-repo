#!/usr/bin/env python3
"""
Command-line interface for managing the local document metadata index.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ..config import load_config
from ..model import DocumentMetadata
from ..exceptions import ValidationError, DocumentServiceError
from ..document_store.local_index import LocalIndexDocumentStore


def format_document(doc: DocumentMetadata, verbose: bool = False) -> str:
    """Format a document for display"""
    if verbose:
        return f"""UUID: {doc.uuid}
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
        return f"{doc.uuid}: {doc.name} {tags_str}"


async def cmd_list(args: argparse.Namespace):
    """List all documents"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

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
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

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
        uuid="",  # Will be generated
        name=args.name,
        url=args.url,
        summary=args.summary,
        mime_type=args.mime_type,
        tags=tags,
        extra=extra if extra else None,
    )

    try:
        async with store:
            uuid = await store.store(doc)

            if args.json:
                doc.uuid = uuid
                print(json.dumps(doc.model_dump(mode="json"), indent=2, default=str))
            else:
                print(f"✓ Document added: {uuid}")
                print(f"  Name: {args.name}")
                print(f"  URL: {args.url}")
                if tags:
                    print(f"  Tags: {', '.join(tags)}")

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_get(args: argparse.Namespace):
    """Get a document by UUID"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    try:
        async with store:
            doc = await store.get(args.uuid)

            if doc is None:
                print(f"Document not found: {args.uuid}", file=sys.stderr)
                sys.exit(1)

            if args.json:
                print(json.dumps(doc.model_dump(mode="json"), indent=2, default=str))
            else:
                print(format_document(doc, verbose=True))

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_search(args: argparse.Namespace):
    """Search documents with multi-field queries"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    # Collect field queries
    field_queries = {}
    if args.name:
        field_queries["name"] = args.name
    if args.tags:
        field_queries["tags"] = args.tags
    if args.summary:
        field_queries["summary"] = args.summary
    if args.extra:
        field_queries["extra"] = args.extra

    if not field_queries:
        print(
            "Error: At least one field query is required (--name, --tags, --summary, or --extra)",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        async with store:
            hits = await store.multi_field_search(
                field_queries=field_queries,
                limit=args.limit,
                combine_mode="union" if args.union else "intersection",
            )

            if args.json:
                output = [hit.model_dump(mode="json") for hit in hits]
                print(json.dumps(output, indent=2, default=str))
            else:
                if not hits:
                    query_desc = ", ".join(f"{k}={v}" for k, v in field_queries.items())
                    print(f"No matches found for: {query_desc}")
                else:
                    # Show query information
                    query_desc = ", ".join(
                        f"{k}='{v}'" for k, v in field_queries.items()
                    )
                    mode = "union" if args.union else "intersection"
                    print(
                        f"Found {len(hits)} match(es) for {query_desc} (mode: {mode}):\n"
                    )

                    for hit in hits:
                        # Show score if requested
                        if hasattr(args, "show_scores") and args.show_scores:
                            print(f"Score: {hit.score:.4f}")

                        print(format_document(hit.result, verbose=args.verbose))

                        if args.verbose and hit != hits[-1]:
                            print("-" * 60)

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_update(args: argparse.Namespace):
    """Update a document's metadata"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    # Parse tags if provided
    tags = None
    if args.tags:
        tags = [tag.strip() for tag in args.tags.split(",")]

    # Parse extra metadata if provided
    extra = None
    if args.extra:
        try:
            extra = json.loads(args.extra)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --extra: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        async with store:
            # Update document
            updated_doc = await store.update(
                uuid=args.uuid,
                name=args.name,
                url=args.url,
                summary=args.summary,
                mime_type=args.mime_type,
                tags=tags,
                extra=extra,
            )

            if args.json:
                print(
                    json.dumps(
                        updated_doc.model_dump(mode="json"), indent=2, default=str
                    )
                )
            else:
                print(f"✓ Document updated: {args.uuid}")
                print(f"  Name: {updated_doc.name}")
                print(f"  URL: {updated_doc.url}")
                if updated_doc.tags:
                    print(f"  Tags: {', '.join(updated_doc.tags)}")
                print(f"  Modified: {updated_doc.modified_at.isoformat()}")

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_remove(args: argparse.Namespace):
    """Remove a document by UUID"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    try:
        async with store:
            deleted = await store.delete(args.uuid)

            if deleted:
                if args.json:
                    print(json.dumps({"status": "deleted", "uuid": args.uuid}))
                else:
                    print(f"✓ Document removed: {args.uuid}")
            else:
                if args.json:
                    print(json.dumps({"status": "not_found", "uuid": args.uuid}))
                else:
                    print(f"Document not found: {args.uuid}", file=sys.stderr)
                    sys.exit(1)

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_add_tags(args: argparse.Namespace):
    """Add tags to a document"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    # Parse tags
    if not args.tags:
        print("Error: --tags is required", file=sys.stderr)
        sys.exit(1)

    tags = [tag.strip() for tag in args.tags.split(",")]

    try:
        async with store:
            updated_doc = await store.add_tags(args.uuid, tags)

            if args.json:
                print(
                    json.dumps(
                        updated_doc.model_dump(mode="json"), indent=2, default=str
                    )
                )
            else:
                print(f"✓ Tags added to document: {args.uuid}")
                print(f"  Added: {', '.join(tags)}")
                print(f"  Current tags: {', '.join(updated_doc.tags)}")
                print(f"  Modified: {updated_doc.modified_at.isoformat()}")

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_remove_tags(args: argparse.Namespace):
    """Remove tags from a document"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    # Parse tags
    if not args.tags:
        print("Error: --tags is required", file=sys.stderr)
        sys.exit(1)

    tags = [tag.strip() for tag in args.tags.split(",")]

    try:
        async with store:
            updated_doc = await store.remove_tags(args.uuid, tags)

            if args.json:
                print(
                    json.dumps(
                        updated_doc.model_dump(mode="json"), indent=2, default=str
                    )
                )
            else:
                print(f"✓ Tags removed from document: {args.uuid}")
                print(f"  Removed: {', '.join(tags)}")
                print(
                    f"  Current tags: {', '.join(updated_doc.tags) if updated_doc.tags else '(none)'}"
                )
                print(f"  Modified: {updated_doc.modified_at.isoformat()}")

    except (ValidationError, DocumentServiceError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def cmd_show(args: argparse.Namespace):
    """Show index information"""
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    async with store:
        documents = await store.list_docs()

        if args.json:
            info = {
                "total_documents": len(documents),
            }
            print(json.dumps(info, indent=2))
        else:
            print("Document Index Information")
            print("=" * 60)
            print(f"Total documents: {len(documents)}")


# ============================================================================
# Cache Management Functions
# ============================================================================


def get_cache_dir() -> Path:
    """Get the cache directory path."""
    return Path(".asta/documents/cache")


def compute_url_hash(url: str) -> str:
    """Compute SHA256 hash of URL for cache key."""
    return hashlib.sha256(url.encode()).hexdigest()


def parse_cache_date(date_str: str) -> datetime:
    """Parse ISO 8601 date string from cache metadata."""
    if date_str.endswith("Z"):
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return datetime.fromisoformat(date_str)


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


async def cmd_cache_list(args: argparse.Namespace):
    """List all items in the cache."""
    cache_dir = get_cache_dir()

    if not cache_dir.exists():
        print("Cache directory does not exist.")
        return

    items = []
    for item_dir in cache_dir.iterdir():
        if not item_dir.is_dir():
            continue

        metadata_file = item_dir / "metadata.yaml"
        content_file = item_dir / "content"

        if not metadata_file.exists():
            continue

        with open(metadata_file, "r") as f:
            metadata = yaml.safe_load(f)

        content_size = content_file.stat().st_size if content_file.exists() else 0
        fetch_date = parse_cache_date(metadata.get("fetch_date", ""))
        age_days = (datetime.now(timezone.utc) - fetch_date).days

        items.append(
            {
                "hash": item_dir.name,
                "url": metadata.get("url", "Unknown"),
                "content_type": metadata.get("content_type", "Unknown"),
                "fetch_date": fetch_date,
                "age_days": age_days,
                "size_bytes": content_size,
                "document_uuid": metadata.get("document_uuid", "N/A"),
            }
        )

    if not items:
        print("Cache is empty.")
        return

    if args.json:
        print(json.dumps(items, indent=2, default=str))
        return

    # Sort by fetch date (newest first)
    items.sort(key=lambda x: x["fetch_date"], reverse=True)

    print(f"{'Hash':<16} {'Age (days)':<12} {'Size':<12} {'URL':<50}")
    print("-" * 100)

    for item in items:
        size_str = format_size(item["size_bytes"])
        url_short = item["url"][:47] + "..." if len(item["url"]) > 50 else item["url"]
        print(
            f"{item['hash'][:16]:<16} {item['age_days']:<12} {size_str:<12} {url_short:<50}"
        )

    total_size = sum(item["size_bytes"] for item in items)
    print(f"\nTotal: {len(items)} items, {format_size(total_size)}")


async def cmd_cache_stats(args: argparse.Namespace):
    """Show cache statistics."""
    cache_dir = get_cache_dir()

    if not cache_dir.exists():
        print("Cache directory does not exist.")
        return

    total_items = 0
    total_size = 0
    content_types = {}
    age_buckets = {
        "0-1 days": 0,
        "1-3 days": 0,
        "3-7 days": 0,
        "7-14 days": 0,
        "14-30 days": 0,
        "30+ days": 0,
    }

    for item_dir in cache_dir.iterdir():
        if not item_dir.is_dir():
            continue

        metadata_file = item_dir / "metadata.yaml"
        content_file = item_dir / "content"

        if not metadata_file.exists():
            continue

        total_items += 1

        with open(metadata_file, "r") as f:
            metadata = yaml.safe_load(f)

        if content_file.exists():
            total_size += content_file.stat().st_size

        content_type = metadata.get("content_type", "Unknown")
        content_types[content_type] = content_types.get(content_type, 0) + 1

        fetch_date = parse_cache_date(metadata.get("fetch_date", ""))
        age_days = (datetime.now(timezone.utc) - fetch_date).days

        if age_days <= 1:
            age_buckets["0-1 days"] += 1
        elif age_days <= 3:
            age_buckets["1-3 days"] += 1
        elif age_days <= 7:
            age_buckets["3-7 days"] += 1
        elif age_days <= 14:
            age_buckets["7-14 days"] += 1
        elif age_days <= 30:
            age_buckets["14-30 days"] += 1
        else:
            age_buckets["30+ days"] += 1

    if args.json:
        output = {
            "total_items": total_items,
            "total_size_bytes": total_size,
            "total_size": format_size(total_size),
            "content_types": content_types,
            "age_distribution": age_buckets,
        }
        print(json.dumps(output, indent=2))
        return

    print("Cache Statistics")
    print("=" * 50)
    print(f"Total items: {total_items}")
    print(f"Total size: {format_size(total_size)}")
    print()

    print("Content Types:")
    for content_type, count in sorted(content_types.items()):
        print(f"  {content_type}: {count}")
    print()

    print("Age Distribution:")
    for bucket, count in age_buckets.items():
        print(f"  {bucket}: {count}")


async def cmd_cache_clean(args: argparse.Namespace):
    """Remove cache items older than max_age_days."""
    cache_dir = get_cache_dir()

    if not cache_dir.exists():
        print("Cache directory does not exist.")
        return

    removed_count = 0
    removed_size = 0
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days)

    for item_dir in cache_dir.iterdir():
        if not item_dir.is_dir():
            continue

        metadata_file = item_dir / "metadata.yaml"
        content_file = item_dir / "content"

        if not metadata_file.exists():
            continue

        with open(metadata_file, "r") as f:
            metadata = yaml.safe_load(f)

        fetch_date = parse_cache_date(metadata.get("fetch_date", ""))

        if fetch_date < cutoff_date:
            size = content_file.stat().st_size if content_file.exists() else 0
            url = metadata.get("url", "Unknown")

            if not args.quiet:
                prefix = "[DRY RUN] " if args.dry_run else ""
                url_short = url[:50] + "..." if len(url) > 50 else url
                print(f"{prefix}Removing: {item_dir.name} ({url_short})")

            if not args.dry_run:
                import shutil

                shutil.rmtree(item_dir)

            removed_count += 1
            removed_size += size

    action = "Would remove" if args.dry_run else "Removed"
    print(f"\n{action} {removed_count} items, {format_size(removed_size)}")


async def cmd_cache_clear(args: argparse.Namespace):
    """Remove all cache items."""
    cache_dir = get_cache_dir()

    if not cache_dir.exists():
        print("Cache directory does not exist.")
        return

    if not args.yes:
        response = input("Are you sure you want to clear the entire cache? [y/N]: ")
        if response.lower() != "y":
            print("Cancelled.")
            return

    import shutil

    shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("Cache cleared.")


async def cmd_cache_info(args: argparse.Namespace):
    """Show detailed information for a specific cached item."""
    cache_dir = get_cache_dir() / args.hash

    if not cache_dir.exists():
        print(f"Cache item not found: {args.hash}", file=sys.stderr)
        sys.exit(1)

    metadata_file = cache_dir / "metadata.yaml"
    content_file = cache_dir / "content"

    if not metadata_file.exists():
        print(f"Metadata file not found for: {args.hash}", file=sys.stderr)
        sys.exit(1)

    with open(metadata_file, "r") as f:
        metadata = yaml.safe_load(f)

    fetch_date = parse_cache_date(metadata.get("fetch_date", ""))
    age_days = (datetime.now(timezone.utc) - fetch_date).days

    if args.json:
        output = {
            "hash": args.hash,
            "url": metadata.get("url", "Unknown"),
            "document_uuid": metadata.get("document_uuid", "N/A"),
            "content_type": metadata.get("content_type", "Unknown"),
            "fetch_date": metadata.get("fetch_date", "Unknown"),
            "age_days": age_days,
            "is_stale": age_days > 7,
        }
        if content_file.exists():
            output["file_size"] = content_file.stat().st_size
            output["file_size_formatted"] = format_size(content_file.stat().st_size)
            output["content_path"] = str(content_file)
        print(json.dumps(output, indent=2))
        return

    print("Cache Item Details")
    print("=" * 70)
    print(f"Hash: {args.hash}")
    print(f"URL: {metadata.get('url', 'Unknown')}")
    print(f"Document UUID: {metadata.get('document_uuid', 'N/A')}")
    print(f"Content Type: {metadata.get('content_type', 'Unknown')}")
    print(f"Fetch Date: {metadata.get('fetch_date', 'Unknown')}")

    if "extraction_method" in metadata:
        print(f"Extraction Method: {metadata['extraction_method']}")

    if content_file.exists():
        size = content_file.stat().st_size
        print(f"File Size: {format_size(size)}")
        print(f"Content Path: {content_file}")
    else:
        print("Content file not found")

    print(f"Age: {age_days} days")

    if age_days > 7:
        print("⚠️  Cache is stale (> 7 days old)")


async def cmd_fetch(args: argparse.Namespace):
    """Fetch content from URL with caching."""
    # Get document metadata
    config = load_config(overrides=getattr(args, "config_overrides", None))
    store = LocalIndexDocumentStore.from_config(config)

    async with store:
        doc = await store.get(args.uuid)

        if doc is None:
            print(f"Error: Document not found: {args.uuid}", file=sys.stderr)
            sys.exit(1)

        url = doc.url
        mime_type = doc.mime_type

        # Check cache
        url_hash = compute_url_hash(url)
        cache_dir = get_cache_dir() / url_hash
        content_file = cache_dir / "content"
        metadata_file = cache_dir / "metadata.yaml"

        use_cache = False
        if content_file.exists() and metadata_file.exists() and not args.force:
            with open(metadata_file, "r") as f:
                cache_metadata = yaml.safe_load(f)
            fetch_date = parse_cache_date(cache_metadata.get("fetch_date", ""))
            age_days = (datetime.now(timezone.utc) - fetch_date).days

            if age_days < args.max_age:
                use_cache = True
                if not args.quiet:
                    print(
                        f"Using cached content (age: {age_days} days)", file=sys.stderr
                    )

        if use_cache:
            # Read from cache
            with open(content_file, "rb") as f:
                content = f.read()
        else:
            # Fetch from URL
            if not args.quiet:
                print(f"Fetching: {url}", file=sys.stderr)

            try:
                result = subprocess.run(
                    ["curl", "-L", "-f", "-s", url], capture_output=True, check=True
                )
                content = result.stdout

                # Save to cache
                cache_dir.mkdir(parents=True, exist_ok=True)
                with open(content_file, "wb") as f:
                    f.write(content)

                cache_metadata = {
                    "url": url,
                    "fetch_date": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "content_type": mime_type,
                    "document_uuid": args.uuid,
                    "file_size": len(content),
                }
                with open(metadata_file, "w") as f:
                    yaml.dump(cache_metadata, f)

                if not args.quiet:
                    print(f"Cached at: {content_file}", file=sys.stderr)

            except subprocess.CalledProcessError as e:
                print(f"Error fetching content: {e}", file=sys.stderr)
                sys.exit(1)

        # Output
        if args.output:
            with open(args.output, "wb") as f:
                f.write(content)
            if not args.quiet:
                print(f"Saved to: {args.output}", file=sys.stderr)
        else:
            sys.stdout.buffer.write(content)


def main():
    """Main entry point for asta-documents CLI"""
    # Create a parent parser with shared arguments for subcommands
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    parser = argparse.ArgumentParser(
        description="Manage the local document metadata index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all documents
  asta-documents list

  # List documents with specific tags
  asta-documents list --tags="ai,research"

  # Add a document
  asta-documents add https://arxiv.org/pdf/1706.03762.pdf \\
    --name="Attention Is All You Need" \\
    --summary="Transformer architecture paper" \\
    --tags="ai,research,transformers" \\
    --mime-type="application/pdf"

  # Search documents by single field
  asta-documents search --summary="transformer architecture"
  asta-documents search --name="Attention"
  asta-documents search --tags="ai,nlp"
  asta-documents search --extra=".year > 2020"

  # Search multiple fields (default: intersection)
  asta-documents search --summary="transformers" --tags="ai"

  # Search multiple fields with union
  asta-documents search --summary="transformers" --name="BERT" --union

  # Get specific document
  asta-documents get 6MNxGbWGRC

  # Update document metadata
  asta-documents update 6MNxGbWGRC \\
    --name="New Title" \\
    --tags="ai,updated"

  # Remove document
  asta-documents remove 6MNxGbWGRC

  # Add tags to a document
  asta-documents add-tags 6MNxGbWGRC --tags="ai,updated"

  # Remove tags from a document
  asta-documents remove-tags 6MNxGbWGRC --tags="old,deprecated"

  # Show index information
  asta-documents show

  # Fetch document content (with caching)
  asta-documents fetch 6MNxGbWGRC -o document.pdf

  # Cache management
  asta-documents cache list            # List cached items
  asta-documents cache stats           # Show statistics
  asta-documents cache clean --days 7  # Remove old items
  asta-documents cache clear           # Remove all cache
  asta-documents cache info <hash>     # Show item details
""",
    )

    # Global options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format (can appear anywhere in command)",
    )
    parser.add_argument(
        "--index-path",
        help="Override index file path (default: from config)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list command
    list_parser = subparsers.add_parser(
        "list", help="List all documents", parents=[parent_parser]
    )
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
    add_parser = subparsers.add_parser(
        "add", help="Add a new document", parents=[parent_parser]
    )
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
    get_parser = subparsers.add_parser(
        "get", help="Get document by UUID", parents=[parent_parser]
    )
    get_parser.add_argument("uuid", help="Document UUID (10-character alphanumeric ID)")
    get_parser.set_defaults(func=cmd_get)

    # search command
    search_parser = subparsers.add_parser(
        "search", help="Search documents", parents=[parent_parser]
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum results (default: 10)",
    )

    # Field-specific queries (can be combined)
    search_parser.add_argument(
        "--name",
        type=str,
        help="Query for document names",
    )
    search_parser.add_argument(
        "--tags",
        type=str,
        help="Query for tags (comma-separated)",
    )
    search_parser.add_argument(
        "--summary",
        type=str,
        help="Query for summaries",
    )
    search_parser.add_argument(
        "--extra",
        type=str,
        help="Query for extra metadata (JSONPath syntax)",
    )

    # Combine mode
    search_parser.add_argument(
        "--union",
        action="store_true",
        help="Return union of results (default: intersection)",
    )

    search_parser.add_argument(
        "--show-scores",
        action="store_true",
        help="Show relevance scores for each result",
    )
    search_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed information",
    )
    search_parser.set_defaults(func=cmd_search)

    # update command
    update_parser = subparsers.add_parser(
        "update", help="Update document metadata", parents=[parent_parser]
    )
    update_parser.add_argument(
        "uuid", help="Document UUID (10-character alphanumeric ID)"
    )
    update_parser.add_argument("--name", help="New document name")
    update_parser.add_argument("--url", help="New document URL")
    update_parser.add_argument("--summary", help="New document summary")
    update_parser.add_argument("--mime-type", help="New MIME type")
    update_parser.add_argument(
        "--tags", help="New tags (comma-separated, replaces existing)"
    )
    update_parser.add_argument(
        "--extra", help="New extra metadata as JSON string (replaces existing)"
    )
    update_parser.set_defaults(func=cmd_update)

    # remove command
    remove_parser = subparsers.add_parser(
        "remove", help="Remove document by UUID", parents=[parent_parser]
    )
    remove_parser.add_argument(
        "uuid", help="Document UUID (10-character alphanumeric ID)"
    )
    remove_parser.set_defaults(func=cmd_remove)

    # add-tags command
    add_tags_parser = subparsers.add_parser(
        "add-tags", help="Add tags to a document", parents=[parent_parser]
    )
    add_tags_parser.add_argument(
        "uuid", help="Document UUID (10-character alphanumeric ID)"
    )
    add_tags_parser.add_argument(
        "--tags", required=True, help="Tags to add (comma-separated)"
    )
    add_tags_parser.set_defaults(func=cmd_add_tags)

    # remove-tags command
    remove_tags_parser = subparsers.add_parser(
        "remove-tags", help="Remove tags from a document", parents=[parent_parser]
    )
    remove_tags_parser.add_argument(
        "uuid", help="Document UUID (10-character alphanumeric ID)"
    )
    remove_tags_parser.add_argument(
        "--tags", required=True, help="Tags to remove (comma-separated)"
    )
    remove_tags_parser.set_defaults(func=cmd_remove_tags)

    # show command
    show_parser = subparsers.add_parser(
        "show", help="Show index information", parents=[parent_parser]
    )
    show_parser.set_defaults(func=cmd_show)

    # fetch command
    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch document content with caching"
    )
    fetch_parser.add_argument(
        "uuid", help="Document UUID (10-character alphanumeric ID)"
    )
    fetch_parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    fetch_parser.add_argument(
        "--force", action="store_true", help="Force refresh, ignore cache"
    )
    fetch_parser.add_argument(
        "--max-age",
        type=int,
        default=7,
        help="Maximum cache age in days (default: 7)",
    )
    fetch_parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress progress messages"
    )
    fetch_parser.set_defaults(func=cmd_fetch)

    # cache commands
    cache_parser = subparsers.add_parser("cache", help="Manage content cache")
    cache_subparsers = cache_parser.add_subparsers(
        dest="cache_command", help="Cache command"
    )

    # cache list
    cache_list_parser = cache_subparsers.add_parser(
        "list", help="List cached items", parents=[parent_parser]
    )
    cache_list_parser.set_defaults(func=cmd_cache_list)

    # cache stats
    cache_stats_parser = cache_subparsers.add_parser(
        "stats", help="Show cache statistics", parents=[parent_parser]
    )
    cache_stats_parser.set_defaults(func=cmd_cache_stats)

    # cache clean
    cache_clean_parser = cache_subparsers.add_parser(
        "clean", help="Remove old cache items"
    )
    cache_clean_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Remove items older than N days (default: 7)",
    )
    cache_clean_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be removed"
    )
    cache_clean_parser.add_argument(
        "--quiet", "-q", action="store_true", help="Only show summary"
    )
    cache_clean_parser.set_defaults(func=cmd_cache_clean)

    # cache clear
    cache_clear_parser = cache_subparsers.add_parser(
        "clear", help="Remove all cache items"
    )
    cache_clear_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation"
    )
    cache_clear_parser.set_defaults(func=cmd_cache_clear)

    # cache info
    cache_info_parser = cache_subparsers.add_parser(
        "info", help="Show cached item details", parents=[parent_parser]
    )
    cache_info_parser.add_argument("hash", help="Cache hash (directory name)")
    cache_info_parser.set_defaults(func=cmd_cache_info)

    # Parse arguments
    args = parser.parse_args()

    # Handle --json appearing anywhere in command line
    # If --json appears before the subcommand, the subparser's default value (False)
    # overwrites the main parser's value (True), so we need to check sys.argv directly
    if "--json" in sys.argv:
        args.json = True

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle cache subcommand
    if args.command == "cache":
        if not hasattr(args, "cache_command") or args.cache_command is None:
            cache_parser.print_help()
            sys.exit(1)

    # Build config overrides from command-line arguments
    config_overrides = {}
    if hasattr(args, "index_path") and args.index_path:
        config_overrides["index_path"] = args.index_path

    # Attach overrides to args so commands can access them
    args.config_overrides = config_overrides if config_overrides else None

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
