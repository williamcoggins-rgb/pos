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

            if response.status_code not in (200, 201):
                error_data = response.json()
                raise Exception(error_data.get("msg", error_data.get("error_description", "Registration failed")))

            data = response.json()

            # Extract user_id from response
            if "id" in data:
                user_id = data["id"]
            elif "user" in data and data["user"]:
                user_id = data["user"]["id"]
            else:
                raise Exception("Registration failed - no user data returned")

            # Always generate our own JWT token for consistency
            # This ensures the token can be verified by our verify_token() method
            # regardless of Supabase's email confirmation settings
            access_token = self._generate_token(user_id)

            # Create barber record
            barber_id = f"barber_{user_id[:16]}"

            # Insert into barbers table
            # Use Supabase token if available, otherwise use service key
            insert_headers = {
                **self.headers,
                "Prefer": "return=minimal"
            }
            if "access_token" in data:
                insert_headers["Authorization"] = f"Bearer {data['access_token']}"
            else:
                # Use service role key for insertion
                insert_headers["Authorization"] = f"Bearer {self.supabase_key}"

            barber_response = await client.post(
                f"{self.supabase_url}/rest/v1/barbers",
                headers=insert_headers,
                json={
                    "id": user_id,
                    "barber_id": barber_id,
                    "shop_name": shop_name,
                }
            )

            # Log if barber creation failed (but don't fail registration)
            if barber_response.status_code not in (200, 201):
                print(f"Warning: Failed to create barber record: {barber_response.text}")

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

    def _generate_token(self, user_id: str) -> str:
        """
        Generate a JWT token for a user
        Used when Supabase doesn't return an access_token (email confirmation mode)
        """
        payload = {
            "sub": user_id,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(days=7),
            "iss": "barberscore-pos",
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

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
