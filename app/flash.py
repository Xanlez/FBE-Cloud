from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette import status


def set_flash(
    request: Request,
    *,
    success: str | None = None,
    error: str | None = None,
) -> None:
    if success is not None:
        request.session["flash_success"] = success
    if error is not None:
        request.session["flash_error"] = error


def apply_flash(
    request: Request,
    error: str | None = None,
    success: str | None = None,
) -> tuple[str | None, str | None]:
    flash_error = request.session.pop("flash_error", None)
    flash_success = request.session.pop("flash_success", None)
    return error or flash_error, success or flash_success


def redirect_with_flash(
    url: str,
    request: Request,
    *,
    success: str | None = None,
    error: str | None = None,
    status_code: int = status.HTTP_303_SEE_OTHER,
) -> RedirectResponse:
    set_flash(request, success=success, error=error)
    return RedirectResponse(url=url, status_code=status_code)
