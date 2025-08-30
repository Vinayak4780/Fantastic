"""
Admin routes for user management and system administration
ADMIN role only - manage supervisors, guards, and system configuration
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from bson import ObjectId

# Import services and dependencies
from services.auth_service import get_current_admin
from database import (
    get_users_collection, get_supervisors_collection, get_guards_collection,
    get_scan_events_collection, get_database_health
)
from config import settings

# Import models
from models import (
    UserCreate, UserResponse, UserRole, SupervisorCreate, SupervisorResponse,
    GuardCreate, GuardResponse, ScanEventResponse, AreaReportRequest,
    ScanReportResponse, SuccessResponse, SystemConfig, SystemConfigUpdate
)

logger = logging.getLogger(__name__)

# Create router
admin_router = APIRouter()


@admin_router.get("/dashboard")
async def get_admin_dashboard(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Admin dashboard with system statistics
    """
    try:
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        guards_collection = get_guards_collection()
        scan_events_collection = get_scan_events_collection()
        
        if not all([users_collection, supervisors_collection, guards_collection, scan_events_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Get basic counts
        total_users = await users_collection.count_documents({})
        active_users = await users_collection.count_documents({"isActive": True})
        total_supervisors = await supervisors_collection.count_documents({})
        total_guards = await guards_collection.count_documents({})
        
        # Get scan statistics
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_scans = await scan_events_collection.count_documents({
            "scannedAt": {"$gte": today_start}
        })
        
        # Get area breakdown
        area_pipeline = [
            {"$group": {"_id": "$areaCity", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        areas = await supervisors_collection.aggregate(area_pipeline).to_list(length=None)
        
        # Database health
        db_health = await get_database_health()
        
        return {
            "statistics": {
                "total_users": total_users,
                "active_users": active_users,
                "total_supervisors": total_supervisors,
                "total_guards": total_guards,
                "today_scans": today_scans
            },
            "areas": areas,
            "database_health": db_health,
            "system_config": {
                "within_radius_meters": settings.WITHIN_RADIUS_METERS,
                "otp_expire_minutes": settings.OTP_EXPIRE_MINUTES,
                "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )


@admin_router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """
    List all users with optional filtering
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build filter
        filter_query = {}
        if role:
            filter_query["role"] = role.value
        if active is not None:
            filter_query["isActive"] = active
        
        # Get users
        cursor = users_collection.find(filter_query).skip(skip).limit(limit).sort("createdAt", -1)
        users = await cursor.to_list(length=None)
        
        # Convert to response models
        user_responses = []
        for user in users:
            user_response = UserResponse(
                id=str(user["_id"]),
                email=user["email"],
                name=user["name"],
                role=UserRole(user["role"]),
                areaCity=user.get("areaCity"),
                isActive=user["isActive"],
                createdAt=user["createdAt"],
                updatedAt=user["updatedAt"],
                lastLogin=user.get("lastLogin")
            )
            user_responses.append(user_response)
        
        return user_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@admin_router.delete("/users/{user_id}", response_model=SuccessResponse)
async def disable_user(
    user_id: str,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Soft delete user by disabling account
    """
    try:
        users_collection = get_users_collection()
        if not users_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Don't allow disabling other admins
        user_to_disable = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user_to_disable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user_to_disable["role"] == UserRole.ADMIN.value and str(user_to_disable["_id"]) != str(current_admin["_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot disable other admin accounts"
            )
        
        # Disable user (soft delete)
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "isActive": False,
                    "updatedAt": datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"Admin {current_admin['email']} disabled user {user_to_disable['email']}")
        return SuccessResponse(message="User account disabled successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Disable user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable user"
        )


@admin_router.post("/supervisors", response_model=SupervisorResponse)
async def create_supervisor(
    supervisor_data: SupervisorCreate,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Create a new supervisor
    """
    try:
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([users_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Check if email already exists
        existing_user = await users_collection.find_one({"email": supervisor_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create user record first
        user_doc = {
            "email": supervisor_data.email,
            "name": supervisor_data.name,
            "role": UserRole.SUPERVISOR.value,
            "areaCity": supervisor_data.areaCity,
            "isActive": True,
            "isEmailVerified": True,  # Admin-created accounts are pre-verified
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        user_result = await users_collection.insert_one(user_doc)
        user_id = user_result.inserted_id
        
        # Create supervisor record
        supervisor_doc = {
            "userId": user_id,
            "areaCity": supervisor_data.areaCity,
            "areaState": supervisor_data.areaState,
            "areaCountry": supervisor_data.areaCountry,
            "sheetId": supervisor_data.sheetId,
            "assignedGuards": [],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        supervisor_result = await supervisors_collection.insert_one(supervisor_doc)
        
        # Get created supervisor with user data
        created_supervisor = await supervisors_collection.find_one({"_id": supervisor_result.inserted_id})
        created_user = await users_collection.find_one({"_id": user_id})
        
        response = SupervisorResponse(
            id=str(created_supervisor["_id"]),
            userId=str(created_supervisor["userId"]),
            email=created_user["email"],
            name=created_user["name"],
            areaCity=created_supervisor["areaCity"],
            areaState=created_supervisor["areaState"],
            areaCountry=created_supervisor["areaCountry"],
            sheetId=created_supervisor["sheetId"],
            assignedGuards=created_supervisor["assignedGuards"],
            isActive=created_user["isActive"],
            createdAt=created_supervisor["createdAt"],
            updatedAt=created_supervisor["updatedAt"]
        )
        
        logger.info(f"Admin {current_admin['email']} created supervisor {supervisor_data.email}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create supervisor error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create supervisor"
        )


@admin_router.get("/supervisors", response_model=List[SupervisorResponse])
async def list_supervisors(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    area_city: Optional[str] = Query(None, description="Filter by area city"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """
    List all supervisors with optional filtering
    """
    try:
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([users_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build filter for supervisors
        supervisor_filter = {}
        if area_city:
            supervisor_filter["areaCity"] = {"$regex": area_city, "$options": "i"}
        
        # Get supervisors with user data
        pipeline = [
            {"$match": supervisor_filter},
            {"$lookup": {
                "from": "users",
                "localField": "userId",
                "foreignField": "_id",
                "as": "user_data"
            }},
            {"$unwind": "$user_data"},
            {"$skip": skip},
            {"$limit": limit},
            {"$sort": {"createdAt": -1}}
        ]
        
        if active is not None:
            pipeline.insert(2, {"$match": {"user_data.isActive": active}})
        
        supervisors = await supervisors_collection.aggregate(pipeline).to_list(length=None)
        
        # Convert to response models
        supervisor_responses = []
        for supervisor in supervisors:
            response = SupervisorResponse(
                id=str(supervisor["_id"]),
                userId=str(supervisor["userId"]),
                email=supervisor["user_data"]["email"],
                name=supervisor["user_data"]["name"],
                areaCity=supervisor["areaCity"],
                areaState=supervisor["areaState"],
                areaCountry=supervisor["areaCountry"],
                sheetId=supervisor["sheetId"],
                assignedGuards=supervisor["assignedGuards"],
                isActive=supervisor["user_data"]["isActive"],
                createdAt=supervisor["createdAt"],
                updatedAt=supervisor["updatedAt"]
            )
            supervisor_responses.append(response)
        
        return supervisor_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List supervisors error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list supervisors"
        )


@admin_router.post("/guards", response_model=GuardResponse)
async def create_guard(
    guard_data: GuardCreate,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Create a new guard and assign to supervisor
    """
    try:
        users_collection = get_users_collection()
        guards_collection = get_guards_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([users_collection, guards_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Check if email already exists
        existing_user = await users_collection.find_one({"email": guard_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Verify supervisor exists
        supervisor = await supervisors_collection.find_one({"_id": ObjectId(guard_data.supervisorId)})
        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found"
            )
        
        # Create user record first
        user_doc = {
            "email": guard_data.email,
            "name": guard_data.name,
            "role": UserRole.GUARD.value,
            "areaCity": supervisor["areaCity"],  # Guard inherits supervisor's area
            "isActive": True,
            "isEmailVerified": True,  # Admin-created accounts are pre-verified
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        user_result = await users_collection.insert_one(user_doc)
        user_id = user_result.inserted_id
        
        # Create guard record
        guard_doc = {
            "userId": user_id,
            "supervisorId": ObjectId(guard_data.supervisorId),
            "shift": guard_data.shift,
            "phoneNumber": guard_data.phoneNumber,
            "emergencyContact": guard_data.emergencyContact,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        guard_result = await guards_collection.insert_one(guard_doc)
        
        # Add guard to supervisor's assigned guards list
        await supervisors_collection.update_one(
            {"_id": ObjectId(guard_data.supervisorId)},
            {
                "$push": {"assignedGuards": str(guard_result.inserted_id)},
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )
        
        # Get created guard with user data
        created_guard = await guards_collection.find_one({"_id": guard_result.inserted_id})
        created_user = await users_collection.find_one({"_id": user_id})
        
        response = GuardResponse(
            id=str(created_guard["_id"]),
            userId=str(created_guard["userId"]),
            supervisorId=str(created_guard["supervisorId"]),
            email=created_user["email"],
            name=created_user["name"],
            areaCity=created_user["areaCity"],
            shift=created_guard["shift"],
            phoneNumber=created_guard["phoneNumber"],
            emergencyContact=created_guard["emergencyContact"],
            isActive=created_user["isActive"],
            createdAt=created_guard["createdAt"],
            updatedAt=created_guard["updatedAt"]
        )
        
        logger.info(f"Admin {current_admin['email']} created guard {guard_data.email} under supervisor {guard_data.supervisorId}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create guard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create guard"
        )


@admin_router.get("/guards", response_model=List[GuardResponse])
async def list_guards(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    supervisor_id: Optional[str] = Query(None, description="Filter by supervisor ID"),
    area_city: Optional[str] = Query(None, description="Filter by area city"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """
    List all guards with optional filtering
    """
    try:
        users_collection = get_users_collection()
        guards_collection = get_guards_collection()
        
        if not all([users_collection, guards_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build filter for guards
        guard_filter = {}
        if supervisor_id:
            guard_filter["supervisorId"] = ObjectId(supervisor_id)
        
        # Get guards with user data
        pipeline = [
            {"$match": guard_filter},
            {"$lookup": {
                "from": "users",
                "localField": "userId",
                "foreignField": "_id",
                "as": "user_data"
            }},
            {"$unwind": "$user_data"},
            {"$skip": skip},
            {"$limit": limit},
            {"$sort": {"createdAt": -1}}
        ]
        
        # Add additional filters
        additional_match = {}
        if active is not None:
            additional_match["user_data.isActive"] = active
        if area_city:
            additional_match["user_data.areaCity"] = {"$regex": area_city, "$options": "i"}
        
        if additional_match:
            pipeline.insert(2, {"$match": additional_match})
        
        guards = await guards_collection.aggregate(pipeline).to_list(length=None)
        
        # Convert to response models
        guard_responses = []
        for guard in guards:
            response = GuardResponse(
                id=str(guard["_id"]),
                userId=str(guard["userId"]),
                supervisorId=str(guard["supervisorId"]),
                email=guard["user_data"]["email"],
                name=guard["user_data"]["name"],
                areaCity=guard["user_data"]["areaCity"],
                shift=guard["shift"],
                phoneNumber=guard["phoneNumber"],
                emergencyContact=guard["emergencyContact"],
                isActive=guard["user_data"]["isActive"],
                createdAt=guard["createdAt"],
                updatedAt=guard["updatedAt"]
            )
            guard_responses.append(response)
        
        return guard_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List guards error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list guards"
        )


@admin_router.post("/reports/area", response_model=List[ScanReportResponse])
async def generate_area_report(
    report_request: AreaReportRequest,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Generate comprehensive area-wise scan report
    """
    try:
        scan_events_collection = get_scan_events_collection()
        guards_collection = get_guards_collection()
        
        if not all([scan_events_collection, guards_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build aggregation pipeline
        match_filter = {
            "scannedAt": {
                "$gte": report_request.startDate,
                "$lte": report_request.endDate
            }
        }
        
        if report_request.areaCity:
            match_filter["areaCity"] = {"$regex": report_request.areaCity, "$options": "i"}
        
        pipeline = [
            {"$match": match_filter},
            {"$lookup": {
                "from": "guards",
                "localField": "guardId",
                "foreignField": "_id",
                "as": "guard_data"
            }},
            {"$unwind": "$guard_data"},
            {"$lookup": {
                "from": "users",
                "localField": "guard_data.userId",
                "foreignField": "_id",
                "as": "user_data"
            }},
            {"$unwind": "$user_data"},
            {"$project": {
                "guardName": "$user_data.name",
                "guardEmail": "$user_data.email",
                "areaCity": 1,
                "locationName": 1,
                "scannedAt": 1,
                "coordinates": 1,
                "address": 1,
                "isWithinRadius": 1,
                "distanceFromQR": 1
            }},
            {"$sort": {"scannedAt": -1}}
        ]
        
        scan_events = await scan_events_collection.aggregate(pipeline).to_list(length=None)
        
        # Convert to response models
        report_responses = []
        for event in scan_events:
            response = ScanReportResponse(
                guardName=event["guardName"],
                guardEmail=event["guardEmail"],
                areaCity=event["areaCity"],
                locationName=event["locationName"],
                scannedAt=event["scannedAt"],
                coordinates=event["coordinates"],
                address=event.get("address", ""),
                isWithinRadius=event["isWithinRadius"],
                distanceFromQR=event.get("distanceFromQR", 0.0)
            )
            report_responses.append(response)
        
        logger.info(f"Admin {current_admin['email']} generated area report for {report_request.areaCity or 'all areas'}")
        return report_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate area report error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate area report"
        )


@admin_router.get("/system/config")
async def get_system_config(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Get current system configuration
    """
    try:
        config_data = {
            "within_radius_meters": settings.WITHIN_RADIUS_METERS,
            "otp_expire_minutes": settings.OTP_EXPIRE_MINUTES,
            "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
            "max_otp_attempts": settings.MAX_OTP_ATTEMPTS,
            "database_url": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "Hidden",
            "smtp_settings": {
                "server": settings.SMTP_SERVER,
                "port": settings.SMTP_PORT,
                "use_tls": settings.SMTP_USE_TLS,
                "from_email": settings.SMTP_FROM_EMAIL
            },
            "tomtom_api_enabled": bool(settings.TOMTOM_API_KEY),
            "google_sheets_enabled": bool(settings.GOOGLE_SHEETS_CREDENTIALS_JSON)
        }
        
        return config_data
        
    except Exception as e:
        logger.error(f"Get system config error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system configuration"
        )


@admin_router.put("/system/config", response_model=SuccessResponse)
async def update_system_config(
    config_update: SystemConfigUpdate,
    current_admin: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Update system configuration (limited fields)
    """
    try:
        # Note: This is a placeholder implementation
        # In a real application, you might want to store configuration in database
        # or update environment variables through a configuration management system
        
        logger.info(f"Admin {current_admin['email']} requested system config update: {config_update.dict(exclude_unset=True)}")
        
        return SuccessResponse(
            message="System configuration update requested. Changes require application restart to take effect."
        )
        
    except Exception as e:
        logger.error(f"Update system config error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update system configuration"
        )
