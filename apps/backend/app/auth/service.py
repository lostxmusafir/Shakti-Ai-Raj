import logging
from typing import Optional
from app.core.config import settings
from app.core.exceptions import UnauthorizedError, AppException
from app.db.repository import BaseRepository
from app.models.user import User
from app.auth.security import hash_password, verify_password, create_access_token

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.user_repo = BaseRepository("users", User)

    async def ensure_seed_admin(self):
        """Seed super administrator if not present."""
        existing = await self.user_repo.find_one({"email": settings.SEED_ADMIN_EMAIL})
        if not existing:
            logger.info(f"Seeding default super administrator: {settings.SEED_ADMIN_EMAIL}")
            admin_user = User(
                email=settings.SEED_ADMIN_EMAIL,
                name=settings.SEED_ADMIN_NAME,
                hashed_password=hash_password(settings.SEED_ADMIN_PASSWORD),
                role="super_admin",
                unit_id="global",
                status="active"
            )
            await self.user_repo.create(admin_user)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.find_one({"email": email.lower().strip()})
        if not user:
            raise UnauthorizedError("Incorrect email or password.")
        if not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Incorrect email or password.")
        if user.status != "active":
            raise AppException("ACCOUNT_DISABLED", "Your account has been deactivated.", status_code=403)
        return user

    async def register(self, email: str, password: str, name: str, role: str = "employee", unit_id: str = "default_unit") -> User:
        existing = await self.user_repo.find_one({"email": email.lower().strip()})
        if existing:
            raise AppException("USER_EXISTS", "A user with this email already exists.", status_code=400)
        
        user = User(
            email=email.lower().strip(),
            name=name.strip(),
            hashed_password=hash_password(password),
            role=role,
            unit_id=unit_id,
            status="active"
        )
        return await self.user_repo.create(user)

    def create_token_for_user(self, user: User) -> str:
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "unit_id": user.unit_id
        }
        return create_access_token(payload)

auth_service = AuthService()
