"""
RAG Chunk Generator — Markdown → JSON
Reads a structured metadata markdown file and produces one JSON chunk per table.

Configure INPUT_FILE and OUTPUT_DIR below, then run:
    python md_to_chunks.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────


def parse_kv_lines(lines: list[str]) -> dict:
    """
    Parse lines of the form:  - key: value
    Returns a dict of {key: value}.
    """
    result = {}
    for line in lines:
        line = line.strip().lstrip("-").strip()
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def parse_bool(value: str) -> bool | str:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def parse_primary_key(raw: str):
    """Return string if single PK, list if composite, None if 'none'."""
    raw = raw.strip()
    if raw.lower() in ("none", ""):
        return None
    parts = [p.strip() for p in raw.split(",")]
    return parts[0] if len(parts) == 1 else parts


def parse_foreign_keys(raw: str) -> list[str]:
    """Return list of FK column names, empty list if 'none'."""
    raw = raw.strip()
    if raw.lower() == "none":
        return []
    return [p.strip() for p in raw.split(",")]


def parse_column_values(raw: str) -> list:
    """Split comma-separated values; cast to int if all values are numeric."""
    values = [v.strip() for v in raw.split(",") if v.strip()]
    if all(v.lstrip("-").isdigit() for v in values):
        return [int(v) for v in values]
    return values


# ── Section Splitters ──────────────────────────────────────────────────────


def split_tables(text: str) -> list[str]:
    """Split the full document into per-table blocks on '# TABLE:' headings."""
    return re.split(r"(?=^# TABLE:)", text, flags=re.MULTILINE)


def split_columns(columns_block: str) -> list[str]:
    """Split a COLUMNS block into individual column sections on '### <name>' headings."""
    return re.split(r"(?=^### )", columns_block, flags=re.MULTILINE)


def split_relationships(rel_block: str) -> list[dict]:
    """Parse each relationship line into a dict."""
    relationships = []
    for line in rel_block.splitlines():
        line = line.strip().lstrip("-").strip()
        if not line:
            continue
        parts = {}
        for segment in line.split("|"):
            segment = segment.strip()
            if ":" in segment:
                k, _, v = segment.partition(":")
                parts[k.strip()] = v.strip()
        if parts:
            relationships.append(parts)
    return relationships


# ── Column Parser ──────────────────────────────────────────────────────────


def parse_column(col_block: str) -> dict:
    """Parse a single ### column_name block into a column dict."""
    lines = col_block.strip().splitlines()

    # First line is the column name heading
    col_name = lines[0].lstrip("#").strip()
    col = {"column_name": col_name}

    # Parse key-value lines below the heading
    kv = parse_kv_lines(lines[1:])

    col["data_type"] = kv.get("data_type", "")
    col["column_type"] = kv.get("column_type", "")
    col["nullable"] = parse_bool(kv.get("nullable", "true"))

    if "column_values" in kv:
        col["column_values"] = parse_column_values(kv["column_values"])

    for optional in ("value_range", "date_range", "null_note"):
        if optional in kv:
            col[optional] = kv[optional]

    col["description"] = kv.get("description", "")

    return col


# ── Table Parser ───────────────────────────────────────────────────────────


def parse_table_block(block: str, chunk_number: int) -> dict:
    """Parse a full '# TABLE: <name>' block into a chunk dict."""

    # ── Table name from heading
    name_match = re.match(r"# TABLE:\s*(\w+)", block)
    if not name_match:
        return {}
    table_name = name_match.group(1).strip()

    # ── Split block into sections: top-level KV, RELATIONSHIPS, COLUMNS
    rel_section = re.search(
        r"^## RELATIONSHIPS\n(.*?)(?=^## |\Z)", block, flags=re.DOTALL | re.MULTILINE
    )
    col_section = re.search(
        r"^## COLUMNS\n(.*?)(?=^## |\Z)", block, flags=re.DOTALL | re.MULTILINE
    )

    # Top-level KV lines (between heading and first ## section)
    top_end = min(
        rel_section.start() if rel_section else len(block),
        col_section.start() if col_section else len(block),
    )
    top_block = block[:top_end]
    top_kv = parse_kv_lines(
        [l for l in top_block.splitlines() if l.strip().startswith("-")]
    )

    # ── Metadata (all top_kv except reserved keys)
    reserved = {"purpose", "primary_key", "foreign_keys", "row_count"}
    metadata = {
        k: (int(v) if v.isdigit() else v)
        for k, v in top_kv.items()
        if k not in reserved
    }
    if "row_count" in top_kv:
        metadata["row_count"] = int(top_kv["row_count"])

    # ── Relationships
    relationships = []
    if rel_section:
        relationships = split_relationships(rel_section.group(1))

    # ── Columns
    columns = []
    if col_section:
        raw_cols = split_columns(col_section.group(1))
        for raw_col in raw_cols:
            raw_col = raw_col.strip()
            if raw_col.startswith("###"):
                col = parse_column(raw_col)
                if col.get("column_name"):
                    columns.append(col)

    # ── Primary key
    pk_raw = top_kv.get("primary_key", "none")
    primary_key = parse_primary_key(pk_raw)

    # ── Foreign key column names
    fk_raw = top_kv.get("foreign_keys", "none")
    foreign_key_columns = parse_foreign_keys(fk_raw)

    return {
        "chunk_number": chunk_number,
        "title": f"Table: {table_name}",
        "database": "",  # filled in by caller
        "table_name": table_name,
        "purpose": top_kv.get("purpose", ""),
        "primary_key": primary_key,
        "foreign_key_columns": foreign_key_columns,
        "columns": columns,
        "relationships": relationships,
        "metadata": metadata,
    }


# ── Database Metadata Parser ───────────────────────────────────────────────


def parse_db_metadata(text: str) -> dict:
    """Parse the # DATABASE METADATA section."""
    section = re.search(
        r"^# DATABASE METADATA\n(.*?)(?=^# |\Z)", text, flags=re.DOTALL | re.MULTILINE
    )
    if not section:
        return {}
    return parse_kv_lines(
        [l for l in section.group(1).splitlines() if l.strip().startswith("-")]
    )


# ── Main ───────────────────────────────────────────────────────────────────


def generate_chunks(md_path: str, output_dir: str) -> None:
    text = Path(md_path).read_text(encoding="utf-8")
    out = Path(output_dir)

    # Wipe and recreate output folder
    if out.exists():
        for f in out.glob("*.json"):
            f.unlink()
    out.mkdir(parents=True, exist_ok=True)

    db_meta = parse_db_metadata(text)
    database = db_meta.get("database", "Unknown Database")
    platform = db_meta.get("platform", "")
    schema = db_meta.get("schema", "public")
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    table_blocks = [b for b in split_tables(text) if b.strip().startswith("# TABLE:")]

    print(f"\n📄 Input  : {md_path}")
    print(f"📦 Tables : {len(table_blocks)} found")
    print(f"💾 Output : {out}/")
    print("── Chunks ─────────────────────────────────────────────────")

    chunks = []
    for i, block in enumerate(table_blocks, start=1):
        chunk = parse_table_block(block, chunk_number=i)
        if not chunk:
            continue

        # Inject db-level fields
        chunk["database"] = database
        chunk["schema"] = schema
        chunk["platform"] = platform
        chunk["generated_at"] = generated

        # Add platform/schema into metadata too
        chunk["metadata"]["platform"] = platform
        chunk["metadata"]["schema"] = schema

        chunks.append(chunk)

        filename = f"{i:02d}_{chunk['table_name']}.json"
        filepath = out / filename
        filepath.write_text(
            json.dumps(chunk, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        pk_str = str(chunk["primary_key"]) if chunk["primary_key"] else "none"
        n_cols = len(chunk["columns"])
        n_rels = len(chunk["relationships"])
        print(f"  [{i:02d}] {filename:<35}  {n_cols} cols  {n_rels} rels  PK: {pk_str}")

    # Manifest
    manifest = {
        "database": database,
        "platform": platform,
        "schema": schema,
        "source_file": Path(md_path).name,
        "generated_at": generated,
        "total_chunks": len(chunks),
        "files": [
            {
                "chunk_number": c["chunk_number"],
                "filename": f"{c['chunk_number']:02d}_{c['table_name']}.json",
                "table_name": c["table_name"],
                "column_count": len(c["columns"]),
                "row_count": c["metadata"].get("row_count"),
                "primary_key": c["primary_key"],
            }
            for c in chunks
        ],
    }
    manifest_path = out / "00_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n📋 Manifest : {manifest_path}")
    print(f"✅ Done — {len(chunks)} chunk files + manifest written to '{out}/'")


# ── CONFIG ────────────────────────────────────────────────────────────────
# Edit these two paths before running the script.

INPUT_FILE = "brazilian_ecommerce_metadata.md"  # path to your metadata markdown file
OUTPUT_DIR = "rag_chunks"  # folder where JSON chunks will be written

# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    generate_chunks(INPUT_FILE, OUTPUT_DIR)
