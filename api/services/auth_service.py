"""
Authentication service - Supabase integration
Handles user registration, login, and JWT validation
"""

from typing import Optional, Tuple
import jwt
import httpx
from datetime import datetime, timedelta
from api.config import get_settings

settings = get_settings()


class AuthService:
    """
    Supabase authentication service
    Handles registration, login, and token validation
    """

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.supabase_key = settings.SUPABASE_KEY
        self.jwt_secret = settings.SUPABASE_JWT_SECRET
        self.headers = {
            "apikey": self.supabase_key,
            "Content-Type": "application/json",
        }

    async def register(
        self,
        email: str,
        password: str,
        shop_name: str
    ) -> Tuple[str, str, str]:
        """
        Register a new barber

        Args:
            email: User email
            password: User password
            shop_name: Shop name

        Returns:
            (access_token, barber_id, shop_name)
        """
        async with httpx.AsyncClient() as client:
            # Register with Supabase Auth
            response = await client.post(
                f"{self.supabase_url}/auth/v1/signup",
                headers=self.headers,
                json={
                    "email": email,
                    "password": password,
                    "data": {
                        "shop_name": shop_name,
                    }
                }
            )

            if response.status_code != 200:
                error_data = response.json()
                raise Exception(error_data.get("msg", "Registration failed"))

            data = response.json()
            access_token = data["access_token"]
            user_id = data["user"]["id"]

            # Create barber record
            barber_id = f"barber_{user_id[:16]}"

            # Insert into barbers table
            await client.post(
                f"{self.supabase_url}/rest/v1/barbers",
                headers={
                    **self.headers,
                    "Authorization": f"Bearer {access_token}",
                    "Prefer": "return=minimal"
                },
                json={
                    "id": user_id,
                    "barber_id": barber_id,
                    "shop_name": shop_name,
                }
            )

            return (access_token, barber_id, shop_name)

    async def login(
        self,
        email: str,
        password: str
    ) -> Tuple[str, str, str]:
        """
        Login existing barber

        Args:
            email: User email
            password: User password

        Returns:
            (access_token, barber_id, shop_name)
        """
        async with httpx.AsyncClient() as client:
            # Login with Supabase Auth
            response = await client.post(
                f"{self.supabase_url}/auth/v1/token?grant_type=password",
                headers=self.headers,
                json={
                    "email": email,
                    "password": password,
                }
            )

            if response.status_code != 200:
                error_data = response.json()
                raise Exception(error_data.get("msg", "Login failed"))

            data = response.json()
            access_token = data["access_token"]
            user_id = data["user"]["id"]

            # Get barber record
            barber_response = await client.get(
                f"{self.supabase_url}/rest/v1/barbers?id=eq.{user_id}",
                headers={
                    **self.headers,
                    "Authorization": f"Bearer {access_token}",
                }
            )

            if barber_response.status_code != 200:
                raise Exception("Failed to fetch barber details")

            barbers = barber_response.json()
            if not barbers:
                raise Exception("Barber record not found")

            barber = barbers[0]
            return (access_token, barber["barber_id"], barber["shop_name"])

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify JWT token and extract user info

        Args:
            token: JWT access token

        Returns:
            User payload if valid, None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            return payload
        except jwt.InvalidTokenError:
            return None

    def get_barber_id_from_token(self, token: str) -> Optional[str]:
        """Extract barber_id from token"""
        payload = self.verify_token(token)
        if not payload:
            return None

        # The user_id is in the 'sub' claim
        user_id = payload.get("sub")
        if not user_id:
            return None

        # Convert to barber_id format
        return f"barber_{user_id[:16]}"
