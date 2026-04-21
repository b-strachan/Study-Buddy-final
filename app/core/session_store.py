from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from cachetools import TTLCache

SESSION_COOKIE_NAME = os.getenv('FLOATING_AI_SESSION_COOKIE_NAME', 'floating_ai_session_id')
SESSION_TTL_SECONDS = int(os.getenv('FLOATING_AI_SESSION_TTL_SECONDS', '7200'))
SESSION_CLEANUP_INTERVAL_SECONDS = int(os.getenv('FLOATING_AI_SESSION_CLEANUP_INTERVAL_SECONDS', '60'))
SESSION_COOKIE_SAMESITE = os.getenv('FLOATING_AI_SESSION_COOKIE_SAMESITE', 'none')
SESSION_COOKIE_SECURE = os.getenv('FLOATING_AI_SESSION_COOKIE_SECURE', 'true').lower() == 'true'
COURSE_CACHE_TTL_SECONDS = int(os.getenv('COURSE_CACHE_TTL_SECONDS', '7200'))
COURSE_CACHE_MAX_SIZE = int(os.getenv('COURSE_CACHE_MAX_SIZE', '128'))
COURSE_CACHE_CLEANUP_INTERVAL_SECONDS = int(os.getenv('COURSE_CACHE_CLEANUP_INTERVAL_SECONDS', '60'))


@dataclass
class InMemorySession:
    session_id: str
    user_context: dict[str, Any]
    chat_history: list[dict[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=time.time)

    def refresh(self) -> None:
        self.updated_at = time.time()


@dataclass
class CourseVectorIndex:
    course_id: str
    chunks: list[dict[str, Any]] = field(default_factory=list)
    embeddings: Any = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_access_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        now = time.time()
        self.last_access_at = now
        self.updated_at = now


_SESSION_STORE: dict[str, InMemorySession] = {}
_COURSE_VECTOR_CACHE: TTLCache[str, CourseVectorIndex] = TTLCache(
    maxsize=COURSE_CACHE_MAX_SIZE,
    ttl=COURSE_CACHE_TTL_SECONDS,
)
_SESSION_LOCK = threading.RLock()
_COURSE_CACHE_LOCK = threading.RLock()
_COURSE_BUILD_LOCKS: dict[str, threading.Lock] = {}
_CLEANUP_STARTED = False


def _is_expired(session: InMemorySession) -> bool:
    return time.time() >= session.expires_at


def _cleanup_expired_sessions() -> None:
    with _SESSION_LOCK:
        expired_session_ids = [session_id for session_id, session in _SESSION_STORE.items() if _is_expired(session)]
        for session_id in expired_session_ids:
            _SESSION_STORE.pop(session_id, None)


def _cleanup_expired_course_indexes() -> None:
    with _COURSE_CACHE_LOCK:
        _COURSE_VECTOR_CACHE.expire()


def _cleanup_loop() -> None:
    while True:
        time.sleep(min(SESSION_CLEANUP_INTERVAL_SECONDS, COURSE_CACHE_CLEANUP_INTERVAL_SECONDS))
        _cleanup_expired_sessions()
        _cleanup_expired_course_indexes()


def ensure_cleanup_thread() -> None:
    global _CLEANUP_STARTED

    if _CLEANUP_STARTED:
        return

    with _SESSION_LOCK:
        if _CLEANUP_STARTED:
            return

        thread = threading.Thread(target=_cleanup_loop, daemon=True)
        thread.start()
        _CLEANUP_STARTED = True


def create_session(user_context: dict[str, Any]) -> InMemorySession:
    ensure_cleanup_thread()

    session = InMemorySession(
        session_id=uuid.uuid4().hex,
        user_context=user_context,
        chat_history=[]
    )
    now = time.time()
    session.created_at = now
    session.updated_at = now
    session.expires_at = now + SESSION_TTL_SECONDS

    with _SESSION_LOCK:
        _SESSION_STORE[session.session_id] = session

    return session


def get_session(session_id: Optional[str]) -> Optional[InMemorySession]:
    if not session_id:
        return None

    with _SESSION_LOCK:
        session = _SESSION_STORE.get(session_id)
        if session is None:
            return None

        if _is_expired(session):
            _SESSION_STORE.pop(session_id, None)
            return None

        session.refresh()
        return session


def destroy_session(session_id: Optional[str]) -> None:
    if not session_id:
        return

    with _SESSION_LOCK:
        _SESSION_STORE.pop(session_id, None)


def _get_course_build_lock(course_id: str) -> threading.Lock:
    with _COURSE_CACHE_LOCK:
        course_lock = _COURSE_BUILD_LOCKS.get(course_id)
        if course_lock is None:
            course_lock = threading.Lock()
            _COURSE_BUILD_LOCKS[course_id] = course_lock
        return course_lock


def _refresh_course_cache_entry(course_id: str, course_index: CourseVectorIndex) -> CourseVectorIndex:
    course_index.touch()
    _COURSE_VECTOR_CACHE[course_id] = course_index
    return course_index


def put_course_index(course_index: CourseVectorIndex) -> CourseVectorIndex:
    ensure_cleanup_thread()

    if not course_index.course_id:
        raise ValueError('course_index.course_id is required')

    with _COURSE_CACHE_LOCK:
        return _refresh_course_cache_entry(course_index.course_id, course_index)


def get_course_index(course_id: Optional[str]) -> Optional[CourseVectorIndex]:
    if not course_id:
        return None

    ensure_cleanup_thread()

    with _COURSE_CACHE_LOCK:
        course_index = _COURSE_VECTOR_CACHE.get(course_id)
        if course_index is None:
            return None

        return _refresh_course_cache_entry(course_id, course_index)


def destroy_course_index(course_id: Optional[str]) -> None:
    if not course_id:
        return

    with _COURSE_CACHE_LOCK:
        _COURSE_VECTOR_CACHE.pop(course_id, None)
        _COURSE_BUILD_LOCKS.pop(course_id, None)


def get_or_build_course_index(course_id: str, builder: Callable[[], CourseVectorIndex]) -> CourseVectorIndex:
    cached_index = get_course_index(course_id)
    if cached_index is not None:
        return cached_index

    course_lock = _get_course_build_lock(course_id)
    with course_lock:
        cached_index = get_course_index(course_id)
        if cached_index is not None:
            return cached_index

        built_index = builder()
        if built_index.course_id != course_id:
            built_index.course_id = course_id

        return put_course_index(built_index)


def append_chat_message(session_id: str, role: str, content: str) -> Optional[InMemorySession]:
    session = get_session(session_id)
    if session is None:
        return None

    session.chat_history.append({"role": role, "content": content})
    session.refresh()
    return session


def get_session_id_from_cookie(request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE_NAME)


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        expires=SESSION_TTL_SECONDS,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path='/'
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path='/')