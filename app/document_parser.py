import os
import fitz  # PyMuPDF
import docx
import logging

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    text = ""
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text() + "\n"
    except Exception as e:
        logger.error(f"Failed to extract text from PDF {file_path}: {e}")
    return text

def extract_text_from_docx(file_path: str) -> str:
    """Extract text from a Word document (.docx)."""
    text = ""
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        logger.error(f"Failed to extract text from DOCX {file_path}: {e}")
    return text

def extract_text_from_txt(file_path: str) -> str:
    """Extract text from a plain text file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to extract text from TXT {file_path}: {e}")
        return ""

def parse_document(file_path: str) -> str:
    """
    Parse a document based on its file extension and return the extracted text.
    Supported extensions: .pdf, .docx, .txt
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    try:
        if ext == ".pdf":
            return extract_text_from_pdf(file_path)
        elif ext == ".docx":
            return extract_text_from_docx(file_path)
        elif ext == ".txt":
            return extract_text_from_txt(file_path)
        else:
            logger.warning(f"Unsupported file extension: {ext}")
            return ""
    except Exception as e:
        logger.exception(f"Error parsing document {file_path}: {e}")
        return ""
