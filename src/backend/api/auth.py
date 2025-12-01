"""Authentication API endpoints."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register():
    """
    Register a new user.
    Currently returns 201 Created for successful registration.
    """
    return {"message": "User registered successfully"}


@router.post("/login", status_code=status.HTTP_200_OK)
async def login():
    """
    Login an existing user.
    Currently returns 200 OK for successful login.
    """
    return {"message": "User logged in successfully"}
