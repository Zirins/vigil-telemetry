from fastapi.responses import JSONResponse

from app.schemas.schemas import ErrorResponse


def error_response(message: str, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content=ErrorResponse(message=message, code=code).model_dump(),
    )
