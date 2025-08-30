"""
JWT authentication service for access and refresh tokens
Handles token creation, validation, and refresh token management
"""

import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
import secrets
import hashlib
from config import settings
from models import UserRole
import logging
import warnings

logger = logging.getLogger(__name__)

# Suppress bcrypt version warnings
warnings.filterwarnings("ignore", message=".*bcrypt.*", category=UserWarning)

# Password hashing context with updated configuration
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__rounds=12  # Specify rounds to avoid version issues
)


class JWTService:
    """JWT token management service"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """
        Create JWT access token
        
        Args:
            data: Payload data to encode
            
        Returns:
            JWT access token string
        """
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        Create JWT refresh token
        
        Args:
            user_id: User ID to encode
            
        Returns:
            JWT refresh token string
        """
        to_encode = {
            "user_id": user_id,
            "type": "refresh",
            "exp": datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        }
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            token_type: Expected token type ('access' or 'refresh')
            
        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Check token type
            if payload.get("type") != token_type:
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.JWTError:
            logger.warning("Invalid token")
            return None
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def generate_otp(self) -> str:
        """Generate a 6-digit OTP"""
        return f"{secrets.randbelow(1000000):06d}"
    
    def hash_otp(self, otp: str) -> str:
        """Hash OTP for secure storage"""
        return hashlib.sha256(otp.encode()).hexdigest()
    
    def verify_otp(self, plain_otp: str, hashed_otp: str) -> bool:
        """Verify OTP against hash"""
        return hashlib.sha256(plain_otp.encode()).hexdigest() == hashed_otp
    
    def generate_refresh_token_hash(self, refresh_token: str) -> str:
        """Generate hash for refresh token storage"""
        return hashlib.sha256(refresh_token.encode()).hexdigest()


# Global JWT service instance
jwt_service = JWTService()
