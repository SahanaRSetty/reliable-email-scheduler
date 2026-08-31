from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url=(
        "https://accounts.google.com/.well-known/openid-configuration"
    ),
    client_kwargs={
        "scope": "openid email profile",
    },
)


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = settings.GOOGLE_REDIRECT_URI

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
    )


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Google authentication failed: {exc}",
        )

    user_info = token.get("userinfo")

    if not user_info:
        raise HTTPException(
            status_code=400,
            detail="Google did not return user information",
        )

    google_id = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name")
    avatar_url = user_info.get("picture")

    if not google_id or not email:
        raise HTTPException(
            status_code=400,
            detail="Google account information is incomplete",
        )

    user = db.execute(
        select(User).where(User.google_id == google_id)
    ).scalar_one_or_none()

    if user is None:
        user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

    if user is None:
        user = User(
            google_id=google_id,
            name=name or email.split("@")[0],
            email=email,
            avatar_url=avatar_url,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    else:
        user.google_id = google_id
        user.name = name or user.name
        user.avatar_url = avatar_url

        db.commit()
        db.refresh(user)

    request.session["user_id"] = user.id

    return RedirectResponse(
        url="http://localhost:5173/dashboard"
    )


@router.get("/me")
def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    user = db.get(User, user_id)

    if user is None:
        request.session.clear()

        raise HTTPException(
            status_code=401,
            detail="User no longer exists",
        )

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
    }


@router.post("/logout")
def logout(request: Request):
    request.session.clear()

    return {
        "message": "Logged out successfully",
    }