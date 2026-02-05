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
        shop_name: str,
        owner_name: str = None,
        phone: str = None
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

            barber_data = {
                "id": user_id,
                "barber_id": barber_id,
                "shop_name": shop_name,
                "email": email,
            }
            if owner_name:
                barber_data["owner_name"] = owner_name
            if phone:
                barber_data["phone"] = phone

            barber_response = await client.post(
                f"{self.supabase_url}/rest/v1/barbers",
                headers=insert_headers,
                json=barber_data
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

    async def login_with_pin(
        self,
        email: str,
        pin: str
    ) -> Tuple[str, str, str]:
        """
        Login using email and 4-digit PIN (bcrypt verified)

        Args:
            email: User email
            pin: 4-digit PIN

        Returns:
            (access_token, barber_id, shop_name)
        """
        from passlib.hash import bcrypt

        async with httpx.AsyncClient() as client:
            # Look up user by email in barbers table
            response = await client.get(
                f"{self.supabase_url}/rest/v1/barbers?email=eq.{email}",
                headers={
                    **self.headers,
                    "Authorization": f"Bearer {self.supabase_key}",
                }
            )

            if response.status_code != 200:
                raise Exception("Failed to verify credentials")

            barbers = response.json()
            if not barbers:
                raise Exception("Invalid email or PIN")

            barber = barbers[0]

            # Verify PIN using bcrypt
            stored_pin_hash = barber.get("pin_hash")
            if not stored_pin_hash:
                raise Exception("PIN not set. Please complete registration first.")

            # Support both legacy SHA-256 and new bcrypt hashes
            if stored_pin_hash.startswith("$2"):
                # bcrypt hash
                if not bcrypt.verify(pin, stored_pin_hash):
                    raise Exception("Invalid email or PIN")
            else:
                # Legacy SHA-256 hash - verify then auto-upgrade to bcrypt
                import hashlib
                legacy_hash = hashlib.sha256(pin.encode()).hexdigest()
                if legacy_hash != stored_pin_hash:
                    raise Exception("Invalid email or PIN")
                # Auto-upgrade to bcrypt
                new_hash = bcrypt.hash(pin)
                await client.patch(
                    f"{self.supabase_url}/rest/v1/barbers?id=eq.{barber.get('id')}",
                    headers={
                        **self.headers,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Prefer": "return=minimal"
                    },
                    json={"pin_hash": new_hash}
                )

            # Generate JWT token
            user_id = barber.get("id")
            access_token = self._generate_token(user_id)

            return (access_token, barber["barber_id"], barber["shop_name"])

    async def set_pin(
        self,
        user_id: str,
        pin: str
    ) -> bool:
        """
        Set or update user's 4-digit PIN (bcrypt hashed)

        Args:
            user_id: User ID
            pin: 4-digit PIN

        Returns:
            True if successful
        """
        from passlib.hash import bcrypt
        pin_hash = bcrypt.hash(pin)

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.supabase_url}/rest/v1/barbers?id=eq.{user_id}",
                headers={
                    **self.headers,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Prefer": "return=minimal"
                },
                json={"pin_hash": pin_hash}
            )

            if response.status_code not in (200, 204):
                raise Exception(f"Failed to set PIN: {response.text}")

            return True

    async def get_profile(
        self,
        user_id: str
    ) -> dict:
        """
        Get user profile

        Args:
            user_id: User ID

        Returns:
            User profile dict
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.supabase_url}/rest/v1/barbers?id=eq.{user_id}",
                headers={
                    **self.headers,
                    "Authorization": f"Bearer {self.supabase_key}",
                }
            )

            if response.status_code != 200:
                raise Exception("Failed to fetch profile")

            barbers = response.json()
            if not barbers:
                raise Exception("Profile not found")

            barber = barbers[0]
            return {
                "barber_id": barber.get("barber_id"),
                "email": barber.get("email"),
                "shop_name": barber.get("shop_name"),
                "owner_name": barber.get("owner_name"),
                "phone": barber.get("phone"),
                "has_pin": bool(barber.get("pin_hash")),
            }
