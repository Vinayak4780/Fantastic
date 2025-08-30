"""
Database configuration and connection management
Updated for Email-OTP authentication system with MongoDB
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta
from config import settings

# Load environment variables
load_dotenv()

# Global database client
client = None
database = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_database():
    """Initialize database connection and create indexes"""
    global client, database
    
    try:
        logger.info("🔗 Attempting to connect to MongoDB...")
        
        client = AsyncIOMotorClient(
            settings.MONGO_URL,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            maxPoolSize=50
        )
        database = client[settings.DATABASE_NAME]
        
        # Test connection with a simple ping
        await client.admin.command('ping')
        logger.info(f"✅ Connected to MongoDB")
        logger.info(f"📊 Using database: {settings.DATABASE_NAME}")
        
        # Create indexes for better performance
        await create_indexes()
        
        # Create TTL indexes for automatic cleanup
        await create_ttl_indexes()
        
        # Ensure all required collections exist
        await ensure_collections()
        
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
        logger.warning("⚠️ Continuing without database connection...")
        client = None
        database = None


async def cleanup_old_indexes():
    """Remove old/conflicting database indexes"""
    if database is None:
        return
        
    try:
        # Remove old username index that conflicts
        try:
            await database.users.drop_index("username_1")
            logger.info("🔄 Dropped old username index")
        except Exception:
            pass  # Index might not exist
        
        # Remove any other conflicting indexes
        try:
            existing_indexes = await database.users.list_indexes().to_list(length=None)
            for index in existing_indexes:
                index_name = index.get('name', '')
                if 'username' in index_name and index_name != '_id_':
                    try:
                        await database.users.drop_index(index_name)
                        logger.info(f"🔄 Dropped conflicting index: {index_name}")
                    except Exception:
                        pass
        except Exception:
            pass
            
        logger.info("✅ Old indexes cleanup completed")
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to cleanup old indexes: {e}")


async def create_indexes():
    """Create database indexes for better performance"""
    if database is None:
        logger.warning("Database not available, skipping index creation")
        return
        
    try:
        # Clean up old indexes that might conflict
        await cleanup_old_indexes()
        
        # Users collection indexes
        await database.users.create_index("email", unique=True)
        await database.users.create_index([("role", 1), ("isActive", 1)])
        await database.users.create_index("createdAt")
        
        # Supervisors collection indexes
        await database.supervisors.create_index("code", unique=True)
        await database.supervisors.create_index("userId", unique=True)
        await database.supervisors.create_index("areaCity")
        
        # Guards collection indexes
        await database.guards.create_index("employeeCode", unique=True)
        await database.guards.create_index("userId", unique=True)
        await database.guards.create_index("supervisorId")
        
        # QR Locations collection indexes
        await database.qr_locations.create_index("supervisorId", unique=True)  # One QR per supervisor
        await database.qr_locations.create_index([("lat", 1), ("lng", 1)])
        await database.qr_locations.create_index("active")
        
        # Scan Events collection indexes
        await database.scan_events.create_index([("guardId", 1), ("scannedAt", -1)])
        await database.scan_events.create_index([("supervisorId", 1), ("scannedAt", -1)])
        await database.scan_events.create_index([("qrId", 1), ("scannedAt", -1)])
        await database.scan_events.create_index("scannedAt")
        await database.scan_events.create_index("withinRadius")
        
        # OTP Tokens collection indexes
        await database.otp_tokens.create_index("email")
        await database.otp_tokens.create_index([("email", 1), ("purpose", 1)])
        # Note: expiresAt TTL index is created separately in create_ttl_indexes()
        
        # Refresh Tokens collection indexes
        await database.refresh_tokens.create_index("userId")
        await database.refresh_tokens.create_index("tokenHash", unique=True)
        await database.refresh_tokens.create_index("revoked")
        # Note: expiresAt TTL index is created separately in create_ttl_indexes()
        
        logger.info("✅ Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to create indexes: {e}")


async def create_ttl_indexes():
    """Create TTL (Time To Live) indexes for automatic document cleanup"""
    if database is None:
        return
        
    try:
        # Check if TTL indexes already exist and drop them if they conflict
        try:
            # Drop existing conflicting indexes if they exist
            await database.otp_tokens.drop_index("expiresAt_1")
            logger.info("🔄 Dropped existing OTP tokens expiresAt index")
        except Exception:
            pass  # Index might not exist, which is fine
            
        try:
            await database.refresh_tokens.drop_index("expiresAt_1") 
            logger.info("🔄 Dropped existing refresh tokens expiresAt index")
        except Exception:
            pass  # Index might not exist, which is fine
        
        # Create TTL indexes with proper settings
        # OTP tokens - automatically expire based on expiresAt field
        await database.otp_tokens.create_index("expiresAt", expireAfterSeconds=0)
        logger.info("✅ Created TTL index for OTP tokens")
        
        # Refresh tokens - automatically expire based on expiresAt field
        await database.refresh_tokens.create_index("expiresAt", expireAfterSeconds=0)
        logger.info("✅ Created TTL index for refresh tokens")
        
        # Optional: Clean up old scan events after 1 year (365 days)
        # Uncomment if you want to auto-cleanup old scan data
        # await database.scan_events.create_index("createdAt", expireAfterSeconds=365*24*60*60)
        
        logger.info("✅ TTL indexes created successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to create TTL indexes: {e}")
        # Don't raise the exception as this is not critical for app functionality


async def ensure_collections():
    """Ensure all required collections exist in the database"""
    if database is None:
        logger.warning("Database not available, skipping collection creation")
        return
    
    try:
        required_collections = [
            "users",
            "supervisors", 
            "guards",
            "qr_locations",
            "scan_events",
            "otp_tokens",
            "refresh_tokens"
        ]
        
        existing_collections = await database.list_collection_names()
        
        for collection_name in required_collections:
            if collection_name not in existing_collections:
                await database.create_collection(collection_name)
                logger.info(f"✅ Created collection: {collection_name}")
            else:
                logger.info(f"📋 Collection exists: {collection_name}")
        
        logger.info("✅ All required collections are available")
        
    except Exception as e:
        logger.error(f"❌ Failed to ensure collections: {e}")


# Collection accessor functions


def get_database():
    """Get database instance"""
    if database is None:
        logger.warning("Database not initialized")
        return None
    return database


def get_collection(collection_name: str):
    """Get a specific collection"""
    db = get_database()
    if db is None:
        return None
    return db[collection_name]


# Collection getters for convenience
def get_users_collection():
    """Get users collection"""
    return get_collection("users")


def get_supervisors_collection():
    """Get supervisors collection"""
    return get_collection("supervisors")


def get_guards_collection():
    """Get guards collection"""
    return get_collection("guards")


def get_qr_locations_collection():
    """Get QR locations collection"""
    return get_collection("qr_locations")


def get_scan_events_collection():
    """Get scan events collection"""
    return get_collection("scan_events")


def get_otp_tokens_collection():
    """Get OTP tokens collection"""
    return get_collection("otp_tokens")


def get_refresh_tokens_collection():
    """Get refresh tokens collection"""
    return get_collection("refresh_tokens")


async def get_database_health() -> dict:
    """Get database health status"""
    if database is None:
        return {
            "status": "disconnected",
            "message": "Database not initialized"
        }
    
    try:
        # Test database connection
        await client.admin.command('ping')
        
        # Get collection counts
        users_count = await database.users.count_documents({})
        supervisors_count = await database.supervisors.count_documents({})
        guards_count = await database.guards.count_documents({})
        scan_events_count = await database.scan_events.count_documents({})
        
        return {
            "status": "connected",
            "message": "Database operational",
            "database_name": settings.DATABASE_NAME,
            "collections": {
                "users": users_count,
                "supervisors": supervisors_count,
                "guards": guards_count,
                "scan_events": scan_events_count
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }


async def cleanup_expired_tokens():
    """Manually cleanup expired tokens (in case TTL doesn't work)"""
    if database is None:
        return
    
    try:
        current_time = datetime.utcnow()
        
        # Cleanup expired OTP tokens
        otp_result = await database.otp_tokens.delete_many({
            "expiresAt": {"$lt": current_time}
        })
        
        # Cleanup expired refresh tokens
        refresh_result = await database.refresh_tokens.delete_many({
            "expiresAt": {"$lt": current_time}
        })
        
        if otp_result.deleted_count > 0 or refresh_result.deleted_count > 0:
            logger.info(f"🧹 Cleaned up {otp_result.deleted_count} OTP tokens and {refresh_result.deleted_count} refresh tokens")
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired tokens: {e}")


# Optional: Function to create default admin user
async def create_default_admin():
    """Create default admin user if none exists"""
    if database is None:
        return
        
    try:
        # Check if any admin exists
        admin_exists = await database.users.find_one({"role": "ADMIN"})
        
        if not admin_exists:
            from services.jwt_service import jwt_service
            from datetime import datetime
            
            admin_data = {
                "email": settings.DEFAULT_ADMIN_EMAIL,
                "passwordHash": jwt_service.hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                "name": settings.DEFAULT_ADMIN_NAME,
                "role": "ADMIN",
                "areaCity": None,
                "isActive": True,
                "isEmailVerified": True,  # Admin is pre-verified
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }
            
            result = await database.users.insert_one(admin_data)
            logger.info(f"✅ Created default admin user: {settings.DEFAULT_ADMIN_EMAIL}")
            logger.info(f"🔑 Default admin password: {settings.DEFAULT_ADMIN_PASSWORD}")
            logger.warning("⚠️ Please change the default admin password after first login!")
            
    except Exception as e:
        logger.error(f"Failed to create default admin: {e}")


async def close_database():
    """Close database connection"""
    global client
    if client:
        client.close()
        logger.info("Database connection closed")
