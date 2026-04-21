# Library Imports
import io
import re
import logging
import pathlib
import fitz
import docx
from bs4 import BeautifulSoup

# Initialize logger for this module
logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """
    Cleans the extracted text by removing common artifactws.
    """
    # fix hyphenated words broken across lines
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    # remove standalone newlines
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # remove multiple spaces
    text = re.sub(r' +', ' ', text)
    # remove page numbers and simple headers/footers
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    return text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text from PDF"""
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            raw_text = "".join(page.get_text() for page in document)
            return clean_text(raw_text)
    except Exception as e:
        logger.error(f"Error reading PDF: {e}")
        raise ValueError(f"Failed to process PDF file: {str(e)}")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extracts text from DOCX"""
    try:
        document = docx.Document(io.BytesIO(file_bytes))
        raw_text = "\n".join([para.text for para in document.paragraphs])
        return clean_text(raw_text)
    except Exception as e:
        logger.error(f"Error reading DOCX: {e}")
        raise ValueError(f"Failed to process DOCX file: {str(e)}")


def extract_text_from_html(file_bytes: bytes) -> str:
    """Extracts text from HTML"""
    try:
        soup = BeautifulSoup(file_bytes, 'html.parser')
        raw_text = soup.get_text(separator=" ", strip=True)
        return clean_text(raw_text)
    except Exception as e:
        logger.error(f"Error reading HTML: {e}")
        raise ValueError(f"Failed to process HTML file: {str(e)}")


def process_document(file_bytes: bytes, file_name: str) -> str:
    """
    Main router function.
    Extracts text from file bytes based on the file extension.
    """
    file_extension = pathlib.Path(file_name).suffix.lower()

    if file_extension == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif file_extension == ".docx":
        return extract_text_from_docx(file_bytes)
    elif file_extension == ".html":
        return extract_text_from_html(file_bytes)
    elif file_extension == ".txt":
        try:
            raw_text = file_bytes.decode('utf-8')
            return clean_text(raw_text)
        except Exception as e:
            logger.error(f"Error decoding TXT file {file_name}: {e}")
            raise ValueError(f"Failed to process TXT file. Ensure it is UTF-8 encoded.")
    else:
        error_msg = f"Unsupported file type: {file_extension} for file {file_name}"
        logger.warning(error_msg)
        raise ValueError(error_msg)