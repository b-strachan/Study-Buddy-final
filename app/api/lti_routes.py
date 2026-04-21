import os
import logging
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

# Import base classes from PyLTI1p3
from pylti1p3.tool_config import ToolConfJsonFile
from pylti1p3.oidc_login import OIDCLogin
from pylti1p3.message_launch import MessageLaunch
from pylti1p3.request import Request as LTIRequest
from pylti1p3.cookie import CookieService
from pylti1p3.redirect import Redirect
from pylti1p3.session import SessionService

from app.core.session_store import (
    create_session,
    destroy_session,
    get_session,
    get_session_id_from_cookie,
    clear_session_cookie,
    set_session_cookie,
)
from app.services.rag_engine import ensure_course_materials_cached

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/lti",
    tags=["LTI 1.3 Integration"]
)


# --- The Custom FastAPI Adapter ---
class FastAPIRequest(LTIRequest):
    """Bridges FastAPI's Request object to PyLTI1p3's expected format."""

    def __init__(self, request: Request, params: dict = None):
        self._request = request
        self._params = params or {}
        self._cookies = request.cookies
        self._request_is_secure = request.url.scheme in ['https', 'wss']

    @property
    def session(self):
        return self._request.session

    def get_param(self, key):
        return self._params.get(key)

    def get_cookie(self, key):
        return self._cookies.get(key)

    def get_method(self):
        return self._request.method

    def get_url(self):
        return str(self._request.url)

    def is_secure(self) -> bool:
        return self._request_is_secure


class FastAPICookieService(CookieService):
    def __init__(self, request: FastAPIRequest):
        self._request = request
        self._cookie_data_to_set: dict[str, dict[str, object]] = {}

    def _get_key(self, key: str) -> str:
        return f"{self._cookie_prefix}-{key}"

    def get_cookie(self, name: str):
        return self._request.get_cookie(self._get_key(name))

    def set_cookie(self, name: str, value, exp: int = 3600):
        self._cookie_data_to_set[self._get_key(name)] = {"value": value, "exp": exp}

    def update_response(self, response: RedirectResponse) -> None:
        for key, cookie_data in self._cookie_data_to_set.items():
            cookie_kwargs = {
                "key": key,
                "value": cookie_data["value"],
                "max_age": cookie_data["exp"],
                "secure": True,
                "path": "/",
                "httponly": True,
                "samesite": "None",
            }

            response.set_cookie(**cookie_kwargs)


class FastAPISessionService(SessionService):
    pass


class FastAPIRedirect(Redirect[RedirectResponse]):
    def __init__(self, location: str, cookie_service: FastAPICookieService | None = None):
        self._location = location
        self._cookie_service = cookie_service

    def do_redirect(self) -> RedirectResponse:
        response = RedirectResponse(url=self._location)
        if self._cookie_service:
            self._cookie_service.update_response(response)
        return response

    def do_js_redirect(self) -> RedirectResponse:
        # FastAPI flow can use standard HTTP redirects.
        return self.do_redirect()

    def set_redirect_url(self, location: str):
        self._location = location

    def get_redirect_url(self) -> str:
        return self._location


class FastAPYOIDCLogin(OIDCLogin):
    def __init__(
        self,
        request: FastAPIRequest,
        tool_config,
        session_service: FastAPISessionService | None = None,
        cookie_service: FastAPICookieService | None = None,
        launch_data_storage=None,
    ):
        cookie_service = cookie_service if cookie_service else FastAPICookieService(request)
        session_service = session_service if session_service else FastAPISessionService(request)
        super().__init__(request, tool_config, session_service, cookie_service, launch_data_storage)

    def get_redirect(self, url: str) -> FastAPIRedirect:
        return FastAPIRedirect(url, self._cookie_service)


class FastAPIMessageLaunch(MessageLaunch):
    def __init__(
        self,
        request: FastAPIRequest,
        tool_config,
        session_service: FastAPISessionService | None = None,
        cookie_service: FastAPICookieService | None = None,
        launch_data_storage=None,
        requests_session=None,
    ):
        cookie_service = cookie_service if cookie_service else FastAPICookieService(request)
        session_service = session_service if session_service else FastAPISessionService(request)
        super().__init__(
            request,
            tool_config,
            session_service,
            cookie_service,
            launch_data_storage,
            requests_session,
        )

    def _get_request_param(self, key):
        return self._request.get_param(key)


# ----------------------------------

def get_tool_conf():
    config_path = Path(__file__).resolve().parents[2] / "lti_config.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Missing LTI config file at {config_path}")

    return ToolConfJsonFile(str(config_path))


def _extract_user_context(launch_data: dict) -> dict:
    roles = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/roles", [])
    context_claim = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/context", {})

    is_teacher = any(
        "Instructor" in role or "TeachingAssistant" in role or "Administrator" in role
        for role in roles
    )

    return {
        "user_id": launch_data.get("sub"),
        "name": launch_data.get("name") or "LTI User",
        "email": launch_data.get("email"),
        "roles": roles,
        "role": "teacher" if is_teacher else "student",
        "course_id": context_claim.get("id"),
        "iss": launch_data.get("iss"),
        "deployment_id": launch_data.get("https://purl.imsglobal.org/spec/lti/claim/deployment_id")
    }


@router.get("/jwks.json")
async def get_jwks():
    tool_conf = get_tool_conf()
    return tool_conf.get_jwks()


@router.post("/login")
@router.get("/login")
async def lti_login(request: Request):
    try:
        tool_conf = get_tool_conf()

        # Safely extract parameters whether it's a GET or POST request
        if request.method == 'POST':
            form_data = await request.form()
            params = dict(form_data)
        else:
            params = dict(request.query_params)

        # Wrap the FastAPI request in our custom adapter
        req = FastAPIRequest(request, params=params)
        cookie_service = FastAPICookieService(req)
        session_service = FastAPISessionService(req)

        # Initialize the OIDC Login process using the base class
        oidc_login = FastAPYOIDCLogin(
            request=req,
            tool_config=tool_conf,
            session_service=session_service,
            cookie_service=cookie_service,
        )

        target_link_uri = req.get_param('target_link_uri')
        if not target_link_uri:
            raise HTTPException(status_code=400, detail="Missing target_link_uri in request")

        missing_required = [
            key for key in ("iss", "login_hint", "client_id")
            if not req.get_param(key)
        ]
        if missing_required:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required LTI login parameters: {', '.join(missing_required)}"
            )

        # Extract the secure URL Moodle needs us to bounce back to
        # Fire the student back to Moodle to grab their JWT payload
        return oidc_login.redirect(target_link_uri)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LTI Login Error")
        raise HTTPException(status_code=500, detail=f"Failed to initiate LTI login handshake: {str(e)}")


@router.post("/launch")
async def lti_launch(request: Request):
    try:
        form_data = await request.form()
        params = dict(form_data)
        req = FastAPIRequest(request, params=params)
        cookie_service = FastAPICookieService(req)
        session_service = FastAPISessionService(req)
        tool_conf = get_tool_conf()

        # Validates JWT signature, nonce, issuer, audience, and deployment claims.
        launch_data = FastAPIMessageLaunch(
            req,
            tool_conf,
            session_service=session_service,
            cookie_service=cookie_service,
        ).get_launch_data()
        user_ctx = _extract_user_context(launch_data)

        if not user_ctx.get("user_id") or not user_ctx.get("course_id"):
            raise HTTPException(status_code=400, detail="Invalid launch payload: missing user or course context")

        old_session_id = get_session_id_from_cookie(request)
        if old_session_id:
            destroy_session(old_session_id)

        session = create_session(user_ctx)

        ensure_course_materials_cached(user_ctx["course_id"])

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        response = RedirectResponse(url=f"{frontend_url}?lti=1")
        set_session_cookie(response, session.session_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LTI Launch Error")
        raise HTTPException(status_code=401, detail=f"LTI launch validation failed: {str(e)}")


@router.get("/me")
async def lti_me(request: Request):
    session = get_session(get_session_id_from_cookie(request))
    user = session.user_context if session else None
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@router.post("/logout")
async def lti_logout(request: Request):
    session_id = get_session_id_from_cookie(request)
    if session_id:
        destroy_session(session_id)

    response = RedirectResponse(url=os.getenv("FRONTEND_URL", "http://localhost:5173"), status_code=303)
    clear_session_cookie(response)
    return response