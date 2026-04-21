import logging
import os
from fastapi import FastAPI, UploadFile as DefaultUploadFile, File, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, WithJsonSchema
from typing import List, Dict, Any, Optional, Annotated
from fastapi import Request
from starlette.middleware.sessions import SessionMiddleware
# custom modules
from app.utils.document_processor import process_document
from app.services.rag_engine import add_documents_to_course, search_course_knowledge_base
from app.services.llm_client import generate_response_stream
from app.services.llm_client import run_bouncer_check

from app.core.session_store import (
    append_chat_message,
    get_session,
    get_session_id_from_cookie,
)

# LTI router
from app.api.lti import router as lti_router

# --- Swagger UI Bug Fix ---
# Forces Swagger to render a "Choose Files" button instead of a text array
UploadFile = Annotated[DefaultUploadFile, WithJsonSchema({"type": "string", "format": "binary"})]

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# initialize fastapi app 
app = FastAPI(
    title="Study Buddy API",
    description="Scalable, multi-tenant AI backend for educational institutions.",
    version="1.0.0"
)

# Attach the LTI endpoints to the main application
app.include_router(lti_router)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173", "http://localhost:8000", "https://dill-revivable-uneven.ngrok-free.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enable session cookies for the LTI 1.3 cryptographic handshake
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-only-change-me"),
    same_site=os.getenv("SESSION_COOKIE_SAMESITE", "none"),
    https_only=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
)


def get_lti_user(request: Request) -> Optional[Dict[str, Any]]:
    session = get_session(get_session_id_from_cookie(request))
    return session.user_context if session else None


# --- Pydantic Models for Request Validation ---
class ChatRequest(BaseModel):
    student_id: Optional[str] = None
    course_id: Optional[str] = None
    query: str
    model_name: Optional[str] = "ollama/llama3"  # Defaulting to your local pilot setup
    api_base: Optional[str] = "http://host.docker.internal:11434"  # Adjust to your local server IP


# --- API Endpoints ---

@app.get("/health")
async def health_check():
    """Simple health check to verify the API is running."""
    return {"status": "healthy"}


@app.post("/api/v1/teacher/upload")
async def upload_course_materials(
    request: Request,
    files: Annotated[List[UploadFile], File(...)],
    course_id: Annotated[Optional[str], Form()] = None,
    visibility: Annotated[str, Form()] = "student"
):
    """
    Accepts document uploads from teachers, extracts the text, and stores
    it in the vector database tagged with the specific course_id.
    """
    processed_documents = []
    failed_files = []
    lti_user = get_lti_user(request)

    if lti_user:
        if lti_user.get("role") != "teacher":
            raise HTTPException(status_code=403, detail="Only teachers can upload course materials")
        effective_course_id = lti_user.get("course_id")
    else:
        effective_course_id = course_id

    if not effective_course_id:
        raise HTTPException(status_code=400, detail="Missing course_id")

    if visibility not in {"student", "teacher"}:
        raise HTTPException(status_code=400, detail="visibility must be either 'student' or 'teacher'")

    for file in files:
        try:
            # Read the raw bytes from the uploaded file
            file_bytes = await file.read()

            # Extract clean text using our document processor
            extracted_text = process_document(file_bytes, file.filename)

            if extracted_text:
                processed_documents.append({
                    "text": extracted_text,
                    "source": file.filename
                })
            else:
                failed_files.append(file.filename)

        except ValueError as e:
            logger.error(f"Failed to process {file.filename}: {e}")
            failed_files.append(file.filename)

    if not processed_documents:
        raise HTTPException(
            status_code=400,
            detail=f"Could not extract text from any of the uploaded files. Failed: {failed_files}"
        )

    # Add the extracted text to the vector database, strictly isolated by course_id
    vectors_added = add_documents_to_course(processed_documents, effective_course_id, visibility=visibility)

    return {
        "status": "success",
        "course_id": effective_course_id,
        "visibility": visibility,
        "vectors_added": vectors_added,
        "failed_files": failed_files
    }


@app.post("/api/v1/chat")
async def chat_with_study_buddy(request: ChatRequest, http_request: Request):
    """
    Takes a student's question, checks it for academic integrity, retrieves context,
    and streams the response using only the in-memory session store.
    """
    try:
        session_id = get_session_id_from_cookie(http_request)
        session = get_session(session_id)

        if session is None:
            raise HTTPException(status_code=401, detail="Missing or expired session. Please relaunch the LTI tool.")

        lti_user = session.user_context
        effective_course_id = lti_user.get("course_id")
        effective_role = lti_user.get("role", "student")

        if not effective_course_id:
            raise HTTPException(status_code=400, detail="Missing course context in session")

        # --- 1. THE BOUNCER CHECK ---
        is_safe = run_bouncer_check(
            query=request.query,
            model_name=request.model_name,
            api_base=request.api_base
        )

        if not is_safe:
            # If rejected, create a fake generator that yields a canned refusal
            def canned_refusal():
                yield "I cannot fulfill this request as it violates academic integrity guidelines. I am here to help you study and understand the material. How else can I assist you with this topic?"

            append_chat_message(session.session_id, "user", request.query)
            full_refusal = "".join(list(canned_refusal()))
            append_chat_message(session.session_id, "assistant", full_refusal)
            return StreamingResponse(iter([full_refusal]), media_type="text/event-stream")

        # --- 2. MAIN PIPELINE (Only runs if the Bouncer passes) ---

        formatted_history = list(session.chat_history)

        # Retrieve Context
        retrieved_context = search_course_knowledge_base(
            query=request.query,
            course_id=effective_course_id,
            top_k=4,
            visibility="student" if effective_role == "student" else "teacher"
        )

        session_context = {
            **lti_user,
            "chat_history": formatted_history,
        }
        append_chat_message(session.session_id, "user", request.query)

        def stream_and_store():
            assistant_response = ""
            for chunk in generate_response_stream(
                query=request.query,
                retrieved_context=retrieved_context,
                chat_history=session_context.get("chat_history", []),
                model_name=request.model_name,
                api_base=request.api_base
            ):
                assistant_response += chunk
                yield chunk

            append_chat_message(session.session_id, "assistant", assistant_response)

        return StreamingResponse(stream_and_store(), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while processing the chat.")