import json
import re
from pathlib import Path

from src.rag_tool_utils.markdown_convertor import convert_document_to_markdown

BASE_DIR = Path(__file__).resolve().parents[2]
SOURCE_DIR = BASE_DIR / "data" / "sql_rag_sources"
OUTPUT_DIR = Path(__file__).resolve().parent / "internal_doc_chunks"

CHUNK_SIZE = 600
OVERLAP = 80


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


def split_text(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= CHUNK_SIZE:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(paragraph) <= CHUNK_SIZE:
            current = paragraph
            continue

        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= CHUNK_SIZE:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence

        if current:
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)

    if len(chunks) == 1 and len(chunks[0]) > CHUNK_SIZE:
        step = CHUNK_SIZE - OVERLAP
        return [text[i : i + CHUNK_SIZE].strip() for i in range(0, len(text), step)]

    return chunks


def chunk_document(file_path: Path) -> list[dict]:
    markdown = normalize_markdown(convert_document_to_markdown(file_path))
    sections = split_by_headings(markdown)
    chunks = []

    for section in sections:
        for content in split_text(section["content"]):
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
        all_chunks.extend(chunk_document(file_path))

    save_chunks(all_chunks)
    return all_chunks


if __name__ == "__main__":
    chunks = chunk_all_documents()
    print(f"Saved {len(chunks)} chunks to {OUTPUT_DIR}")
