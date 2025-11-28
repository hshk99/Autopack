"""
Error handling middleware
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.exceptions import FileOrganizerException
import logging
import traceback

logger = logging.getLogger(__name__)


async def error_handler_middleware(request: Request, call_next):
    """Global error handler middleware"""
    try:
        response = await call_next(request)
        return response

    except FileOrganizerException as e:
        logger.error(f"FileOrganizer error: {e.message}")
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.__class__.__name__,
                "message": e.message,
                "status_code": e.status_code
            }
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred. Please try again.",
                "status_code": 500
            }
        )
