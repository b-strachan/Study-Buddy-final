from __future__ import annotations

import io
import json
import logging
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import docx
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

MOODLE_BASE_URL = os.getenv("MOODLE_BASE_URL", "").rstrip("/")
MOODLE_API_TOKEN = os.getenv("MOODLE_API_TOKEN", "")
MOODLE_REQUEST_TIMEOUT_SECONDS = int(os.getenv("MOODLE_REQUEST_TIMEOUT_SECONDS", "30"))
MOODLE_DEFAULT_VISIBILITY = os.getenv("MOODLE_DEFAULT_VISIBILITY", "student")


@dataclass(frozen=True)
class MoodleCourseMaterial:
    course_id: str
    source: str
    module_name: str
    moodle_url: str
    text: str
    visibility: str = MOODLE_DEFAULT_VISIBILITY
    section_name: str | None = None
    filename: str | None = None
    mimetype: str | None = None


class MoodleAPIError(RuntimeError):
    pass


def _clean_text(text: str) -> str:
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    return text.strip()


def _resolve_moodle_url(file_url: str, token: str | None = None) -> str:
    if not token:
        return file_url

    parsed = urlparse(file_url)
    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query_pairs.get("token") == token:
        return file_url

    query_pairs["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query_pairs)))


def _request_json(url: str) -> Any:
    request = Request(url)
    try:
        with urlopen(request, timeout=MOODLE_REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except HTTPError as exc:
        raise MoodleAPIError(f"Moodle API request failed with HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise MoodleAPIError(f"Failed to reach Moodle API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise MoodleAPIError("Moodle API returned invalid JSON") from exc


def _download_bytes(url: str) -> bytes:
    request = Request(url)
    try:
        with urlopen(request, timeout=MOODLE_REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()
    except HTTPError as exc:
        raise MoodleAPIError(f"Failed to download Moodle content from {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise MoodleAPIError(f"Failed to download Moodle content from {url}: {exc.reason}") from exc


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        raw_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return _clean_text(raw_text)
    except Exception as exc:
        raise MoodleAPIError(f"Failed to process PDF file in memory: {exc}") from exc


def _extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        document = docx.Document(io.BytesIO(file_bytes))
        raw_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return _clean_text(raw_text)
    except Exception as exc:
        raise MoodleAPIError(f"Failed to process DOCX file in memory: {exc}") from exc


def _extract_text_from_html(file_bytes: bytes) -> str:
    try:
        soup = BeautifulSoup(file_bytes, "html.parser")
        raw_text = soup.get_text(separator=" ", strip=True)
        return _clean_text(raw_text)
    except Exception as exc:
        raise MoodleAPIError(f"Failed to process HTML file in memory: {exc}") from exc


def _extract_text_from_txt(file_bytes: bytes) -> str:
    try:
        return _clean_text(file_bytes.decode("utf-8"))
    except UnicodeDecodeError:
        return _clean_text(file_bytes.decode("utf-8", errors="ignore"))


def extract_text_from_bytes(file_bytes: bytes, file_name: str, mimetype: str | None = None) -> str:
    extension = pathlib.Path(file_name).suffix.lower()
    mimetype = (mimetype or "").lower()

    if extension == ".pdf" or mimetype == "application/pdf":
        return _extract_text_from_pdf(file_bytes)
    if extension == ".docx" or mimetype in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        return _extract_text_from_docx(file_bytes)
    if extension in {".html", ".htm"} or "html" in mimetype:
        return _extract_text_from_html(file_bytes)
    if extension == ".txt" or mimetype.startswith("text/"):
        return _extract_text_from_txt(file_bytes)

    raise MoodleAPIError(f"Unsupported Moodle file type: {file_name} ({mimetype or 'unknown mimetype'})")


def _get_setting_value(value: str | None, fallback: str) -> str:
    if value:
        return value.rstrip("/")
    return fallback.rstrip("/")


def _get_moodle_api_params(course_id: str, base_url: str, token: str) -> str:
    params = {
        "wstoken": token,
        "wsfunction": "core_course_get_contents",
        "moodlewsrestformat": "json",
        "courseid": course_id,
    }
    return f"{base_url}/webservice/rest/server.php?{urlencode(params)}"


def fetch_course_contents(course_id: str, base_url: str | None = None, token: str | None = None) -> list[dict[str, Any]]:
    resolved_base_url = _get_setting_value(base_url, MOODLE_BASE_URL)
    resolved_token = token or MOODLE_API_TOKEN

    if not resolved_base_url:
        raise MoodleAPIError("MOODLE_BASE_URL is not configured")
    if not resolved_token:
        raise MoodleAPIError("MOODLE_API_TOKEN is not configured")

    api_url = _get_moodle_api_params(course_id=course_id, base_url=resolved_base_url, token=resolved_token)
    payload = _request_json(api_url)

    if isinstance(payload, dict) and payload.get("exception"):
        message = payload.get("message") or payload.get("errorcode") or "Unknown Moodle API error"
        raise MoodleAPIError(f"Moodle API error: {message}")

    if not isinstance(payload, list):
        raise MoodleAPIError("Unexpected Moodle API response shape")

    return payload


def _iter_visible_file_entries(course_contents: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for section in course_contents:
        modules = section.get("modules", []) if isinstance(section, dict) else []
        section_name = section.get("name") if isinstance(section, dict) else None

        for module in modules:
            if module.get("uservisible") is False:
                continue

            module_name = module.get("name") or section_name or module.get("modname") or "Untitled module"
            module_contents = module.get("contents", []) or []

            for item in module_contents:
                if item.get("uservisible") is False:
                    continue
                if item.get("type") != "file":
                    continue
                if not item.get("fileurl"):
                    continue

                yield {
                    "section_name": section_name,
                    "module_name": module_name,
                    "module": module,
                    "item": item,
                }


def fetch_course_materials(course_id: str, base_url: str | None = None, token: str | None = None) -> list[dict[str, Any]]:
    course_contents = fetch_course_contents(course_id=course_id, base_url=base_url, token=token)
    resolved_token = token or MOODLE_API_TOKEN

    materials: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for entry in _iter_visible_file_entries(course_contents):
        module = entry["module"]
        item = entry["item"]
        module_name = entry["module_name"]
        section_name = entry["section_name"]
        file_url = item["fileurl"]
        moodle_url = _resolve_moodle_url(file_url, resolved_token)

        if moodle_url in seen_urls:
            continue
        seen_urls.add(moodle_url)

        file_name = item.get("filename") or module_name or "moodle_file"
        mimetype = item.get("mimetype")

        try:
            file_bytes = _download_bytes(moodle_url)
            text = extract_text_from_bytes(file_bytes, file_name=file_name, mimetype=mimetype)
        except MoodleAPIError as exc:
            logger.warning("Skipping Moodle file %s: %s", moodle_url, exc)
            continue

        if not text:
            continue

        materials.append(
            {
                "course_id": course_id,
                "source": file_name,
                "module_name": module_name,
                "moodle_url": moodle_url,
                "text": text,
                "visibility": MOODLE_DEFAULT_VISIBILITY,
                "section_name": section_name,
                "filename": item.get("filename"),
                "mimetype": mimetype,
                "module_id": module.get("id"),
            }
        )

    return materials
