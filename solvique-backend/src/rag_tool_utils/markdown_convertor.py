from pathlib import Path

from markitdown import MarkItDown

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "word",
    ".doc": "word",
    ".pptx": "ppt",
    ".ppt": "ppt",
    ".xlsx": "excel",
    ".xls": "excel",
}


def get_filetype(file_path: Path) -> str:
    extension = file_path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension}")

    return SUPPORTED_EXTENSIONS[extension]


def convert_document_to_markdown(file_path: Path) -> str:
    converter = MarkItDown(enable_plugins=False)
    result = converter.convert(str(file_path))
    return result.text_content or ""
