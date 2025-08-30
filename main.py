"""
Guard Management System - Main Application
FastAPI application with Email-OTP authentication, JWT tokens, and role-based access
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging
import asyncio
import warnings
from datetime import datetime

# Suppress bcrypt warnings
warnings.filterwarnings("ignore", message=".*bcrypt.*", category=UserWarning)

# Import configuration and services
from config import settings
from database import init_database, create_default_admin, get_database_health
from services.google_drive_excel_service import google_drive_excel_service

# Import routes
from routes.auth_routes import auth_router
from routes.admin_routes_working import admin_router
from routes.supervisor_routes import supervisor_router
from routes.guard_routes_simple import guard_router
from routes.qr_routes_simple import qr_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application on startup and cleanup on shutdown"""
    # Startup
    logger.info("🚀 Starting Guard Management System...")
    
    # Validate configuration
    if not settings.validate():
        logger.error("❌ Configuration validation failed")
        raise Exception("Invalid configuration")
    
    # Show warnings for optional settings
    warnings = settings.get_warnings()
    for warning in warnings:
        logger.warning(f"⚠️ {warning}")
    
    # Initialize database
    await init_database()
    
    # Create default admin if needed
    await create_default_admin()
    
    # Start background Google Drive updates
    asyncio.create_task(google_drive_excel_service.start_background_updates())
    
    logger.info("✅ Guard Management System started successfully")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Guard Management System...")
    from database import close_database
    await close_database()


# Create FastAPI app 
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Guard Management System",
    lifespan=lifespan
)

# Custom OpenAPI schema with OAuth2 username/password flow
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags
    )
    
    # Add OAuth2 security scheme for username/password authentication
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": "/auth/login",
                    "scopes": {}
                }
            }
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(supervisor_router, prefix="/supervisor", tags=["Supervisor"])
app.include_router(guard_router, prefix="/guard", tags=["Guard"])
app.include_router(qr_router, prefix="/qr", tags=["QR Management"])


@app.get("/", tags=["System"])
async def root():
    """Root endpoint with system information"""
    return {
        "message": "Guard Management System API", 
        "version": "2.0.0",
        "status": "operational",
        "features": {
            "email_otp_auth": True,
            "jwt_tokens": True,
            "role_based_access": True,
            "qr_scanning": True,
            "tomtom_integration": bool(settings.TOMTOM_API_KEY),
            "google_drive_excel": bool(settings.GOOGLE_DRIVE_CREDENTIALS_FILE),
            "auto_radius_check": True
        },
        "endpoints": {
            "signup": "/auth/signup",
            "login": "/auth/login", 
            "qr_scan": "/qr/scan",
            "admin_dashboard": "/admin/dashboard",
            "health": "/health"
        },
        "documentation": "/docs"
    }


@app.get("/health", tags=["System"])
async def health_check():
    """Comprehensive health check endpoint"""
    
    # Check database health
    db_health = await get_database_health()
    
    # Check Google Drive Excel service health
    excel_health = google_drive_excel_service.get_service_health()
    
    # Check TomTom API availability
    tomtom_status = "configured" if settings.TOMTOM_API_KEY else "not_configured"
    
    # Check email service
    email_status = "configured" if all([
        settings.SMTP_HOST,
        settings.SMTP_USERNAME,
        settings.SMTP_PASSWORD,
        settings.SMTP_FROM_EMAIL
    ]) else "not_configured"
    
    overall_status = "healthy"
    if db_health["status"] != "connected":
        overall_status = "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "services": {
            "database": db_health,
            "google_drive_excel": excel_health,
            "tomtom_api": tomtom_status,
            "email_service": email_status
        },
        "configuration": {
            "within_radius_meters": settings.WITHIN_RADIUS_METERS,
            "otp_expire_minutes": settings.OTP_EXPIRE_MINUTES,
            "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "timezone": settings.TIMEZONE
        }
    }


@app.get("/config", tags=["System"])
async def get_configuration():
    """Get public configuration information"""
    return {
        "within_radius_meters": settings.WITHIN_RADIUS_METERS,
        "otp_expire_minutes": settings.OTP_EXPIRE_MINUTES,
        "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "timezone": settings.TIMEZONE,
        "features": {
            "tomtom_enabled": bool(settings.TOMTOM_API_KEY),
            "google_drive_enabled": bool(settings.GOOGLE_DRIVE_CREDENTIALS_FILE and settings.GOOGLE_DRIVE_FOLDER_ID),
            "email_enabled": bool(settings.SMTP_HOST and settings.SMTP_USERNAME)
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
