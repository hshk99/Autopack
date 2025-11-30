"""
Custom middleware for request processing and authentication.
"""
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import time
import logging


logger = logging.getLogger(__name__)


async def log_requests_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware to log all incoming requests and their processing time.
    
    Args:
        request: Incoming HTTP request
        call_next: Next middleware or route handler
        
    Returns:
        HTTP response
    """
    start_time = time.time()
    
    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Calculate processing time
    process_time = time.time() - start_time
    
    # Add custom header with processing time
    response.headers["X-Process-Time"] = str(process_time)
    
    # Log response
    logger.info(
        f"Response: {request.method} {request.url.path} "
        f"Status: {response.status_code} Time: {process_time:.3f}s"
    )
    
    return response


async def error_handling_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware for global error handling."""
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
