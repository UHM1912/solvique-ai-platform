import json
import re
from pathlib import Path

from src.rag_tool_utils.markdown_convertor import convert_document_to_markdown


BASE_DIR = Path(__file__).resolve().parents[2]
SOURCE_DIR = BASE_DIR / "data" / "rag_sources"
OUTPUT_DIR = Path(__file__).resolve().parent / "chunks"

CHUNK_SIZE = 600
OVERLAP = 80


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    lines = []
    buffer = []

    def flush_buffer() -> None:
        if buffer:
            lines.append(re.sub(r"\s+", " ", " ".join(buffer)).strip())
            buffer.clear()

    for line in text.splitlines():
        stripped = line.strip()

        if (
            not stripped
            or re.match(r"^#{1,6}\s+", stripped)
            or re.match(r"^[-*+]\s+", stripped)
            or re.match(r"^\d+\.\s+", stripped)
            or is_table_line(stripped)
        ):
            flush_buffer()
            if stripped:
                lines.append(stripped)
        else:
            buffer.append(stripped)

    flush_buffer()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def split_by_headings(markdown: str) -> list[dict]:
    sections = []
    heading = "unknown"
    lines = []

    def flush() -> None:
        if lines:
            content = "\n".join(lines).strip()
            if content:
                sections.append({"heading": heading, "content": content})
            lines.clear()

    for line in markdown.splitlines():
        match = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if match:
            flush()
            heading = match.group(1).strip()
        else:
            lines.append(line)

    flush()
    return sections


def split_blocks(text: str) -> list[str]:
    blocks = []
    current = []
    in_table = False

    def flush() -> None:
        if current:
            blocks.append("\n".join(current).strip())
            current.clear()

    for line in text.splitlines():
        stripped = line.strip()

        if is_table_line(stripped):
            if not in_table:
                flush()
                in_table = True
            current.append(stripped)
            continue

        if in_table:
            flush()
            in_table = False

        if not stripped:
            flush()
        else:
            current.append(stripped)

    flush()
    return [block for block in blocks if block]


def split_table(table: str) -> list[str]:
    rows = table.splitlines()
    if len(rows) <= 2 or len(table) <= CHUNK_SIZE:
        return [table]

    header = rows[:2]
    chunks = []
    current = header.copy()

    for row in rows[2:]:
        candidate = "\n".join(current + [row])
        if len(candidate) <= CHUNK_SIZE:
            current.append(row)
        else:
            chunks.append("\n".join(current))
            current = header + [row]

    if len(current) > len(header):
        chunks.append("\n".join(current))

    return chunks


def split_text(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence.strip()
        if len(candidate) <= CHUNK_SIZE:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence.strip()

    if current:
        chunks.append(current)

    if len(chunks) == 1 and len(chunks[0]) > CHUNK_SIZE:
        step = CHUNK_SIZE - OVERLAP
        return [text[i : i + CHUNK_SIZE].strip() for i in range(0, len(text), step)]

    return chunks


def split_content(content: str) -> list[str]:
    chunks = []

    for block in split_blocks(content):
        if any(is_table_line(line) for line in block.splitlines()):
            chunks.extend(split_table(block))
        elif len(block) > CHUNK_SIZE:
            chunks.extend(split_text(block))
        elif chunks and len(chunks[-1]) + len(block) + 2 <= CHUNK_SIZE:
            chunks[-1] = f"{chunks[-1]}\n\n{block}"
        else:
            chunks.append(block)

    return chunks


def chunk_document(file_path: Path) -> list[dict]:
    markdown = normalize_markdown(convert_document_to_markdown(file_path))
    sections = split_by_headings(markdown)
    chunks = []

    for section in sections:
        for content in split_content(section["content"]):
            chunks.append(
                {
                    "filename": file_path.name,
                    "filetype": file_path.suffix.lower().lstrip("."),
                    "chunk_no": len(chunks) + 1,
                    "total_chunks": 0,
                    "heading": section["heading"],
                    "content": content,
                }
            )

    total_chunks = len(chunks)
    for chunk in chunks:
        chunk["total_chunks"] = total_chunks

    return chunks


def save_chunks(chunks: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for old_file in OUTPUT_DIR.glob("*.json"):
        old_file.unlink()

    for index, chunk in enumerate(chunks, start=1):
        output_file = OUTPUT_DIR / f"chunk_{index:03d}.json"
        output_file.write_text(
            json.dumps(chunk, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def chunk_all_documents() -> list[dict]:
    all_chunks = []

    for file_path in sorted(SOURCE_DIR.iterdir()):
        if not file_path.is_file():
            continue

        print(f"Chunking: {file_path.name}")
        all_chunks.extend(chunk_document(file_path))

    save_chunks(all_chunks)
    print(f"Saved {len(all_chunks)} chunks to: {OUTPUT_DIR}")
    return all_chunks


if __name__ == "__main__":
    chunk_all_documents()
