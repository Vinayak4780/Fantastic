import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings loaded from environment variables"""
    
    # Database Configuration
    MONGO_URL: str = os.getenv("MONGO_URL", "")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "guard_patrol_system")
    
    # JWT Security Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    ALGORITHM: str = "HS256"
    
    # Email/SMTP Configuration for OTP
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Guard Management System")
    
    # OTP Configuration
    OTP_EXPIRE_MINUTES: int = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))
    OTP_RATE_LIMIT_MINUTES: int = int(os.getenv("OTP_RATE_LIMIT_MINUTES", "1"))
    
    # TomTom API Configuration
    TOMTOM_API_KEY: str = os.getenv("TOMTOM_API_KEY", "")
    
    # Google Drive Configuration (replaces Google Sheets)
    GOOGLE_DRIVE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE", "./credentials/service-account.json")
    GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    UPDATE_INTERVAL_SECONDS: int = int(os.getenv("UPDATE_INTERVAL_SECONDS", "1"))
    EXCEL_FILE_NAME: str = os.getenv("EXCEL_FILE_NAME", "guard_scan_reports.xlsx")
    UPDATE_INTERVAL_SECONDS: int = int(os.getenv("UPDATE_INTERVAL_SECONDS", "1"))
    
    # QR Location Configuration
    WITHIN_RADIUS_METERS: float = float(os.getenv("WITHIN_RADIUS_METERS", "100.0"))
    
    # Default Admin Configuration
    DEFAULT_ADMIN_EMAIL: str = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@lh.io.in")
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "LH_Admin@2024")
    DEFAULT_ADMIN_NAME: str = os.getenv("DEFAULT_ADMIN_NAME", "System Administrator")
    
    # Email Domain Configuration
    EMAIL_DOMAIN: str = "@lh.io.in"
    
    # CORS Settings
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8000"
    ]
    
    # App Settings
    DEBUG: bool = bool(os.getenv("DEBUG", "True").lower() == "true")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080", 
        "http://localhost:8000"
    ]
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
    
    # Timezone Configuration
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required settings"""
        required_settings = [
            "MONGO_URL", 
            "SECRET_KEY"
        ]
        
        # SMTP settings are optional for development
        optional_smtp_settings = [
            "SMTP_HOST",
            "SMTP_USERNAME", 
            "SMTP_PASSWORD",
            "SMTP_FROM_EMAIL"
        ]
        missing_settings = []
        
        for setting in required_settings:
            if not getattr(cls, setting):
                missing_settings.append(setting)
        
        # Check SMTP settings for warnings
        smtp_missing = []
        for setting in optional_smtp_settings:
            if not getattr(cls, setting):
                smtp_missing.append(setting)
        
        if missing_settings:
            print(f"❌ Missing required settings: {', '.join(missing_settings)}")
            return False
        
        if smtp_missing:
            print(f"⚠️ SMTP settings not configured: {', '.join(smtp_missing)} - Email features will be disabled")
        
        return True
    
    @classmethod
    def get_warnings(cls) -> List[str]:
        """Get warnings for optional but recommended settings"""
        warnings = []
        
        if not cls.TOMTOM_API_KEY:
            warnings.append("TOMTOM_API_KEY not set - TomTom services will be limited")
        
        if cls.SECRET_KEY == "your-secret-key-change-in-production":
            warnings.append("SECRET_KEY is using default value - change for production")
            
        if not cls.GOOGLE_DRIVE_CREDENTIALS_FILE:
            warnings.append("GOOGLE_DRIVE_CREDENTIALS_FILE not set")
        elif not os.path.exists(cls.GOOGLE_DRIVE_CREDENTIALS_FILE):
            warnings.append(f"Google Drive credentials file not found: {cls.GOOGLE_DRIVE_CREDENTIALS_FILE}")
        
        if not cls.GOOGLE_DRIVE_FOLDER_ID:
            warnings.append("GOOGLE_DRIVE_FOLDER_ID not set - Excel files will be saved to root folder")
        
        return warnings

# Global settings instance
settings = Settings() 