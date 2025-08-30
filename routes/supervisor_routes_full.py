"""
Supervisor routes for guard management and QR location management
SUPERVISOR role - manage assigned guards and own QR location
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from bson import ObjectId

# Import services and dependencies
from services.auth_service import get_current_supervisor
from database import (
    get_users_collection, get_guards_collection, get_qr_locations_collection,
    get_scan_events_collection, get_supervisors_collection
)
from config import settings

logger = logging.getLogger(__name__)

# Create router
supervisor_router = APIRouter()


@supervisor_router.get("/dashboard")
async def get_supervisor_dashboard(current_supervisor: Dict[str, Any] = Depends(get_current_supervisor)):
    """Supervisor dashboard with statistics"""
    try:
        logger.info(f"Getting dashboard for supervisor: {current_supervisor.get('email')}")
        
        guards_collection = get_guards_collection()
        qr_locations_collection = get_qr_locations_collection()
        scan_events_collection = get_scan_events_collection()
        
        logger.info(f"Collections: guards={guards_collection is not None}, qr={qr_locations_collection is not None}, scans={scan_events_collection is not None}")
        
        if not all([guards_collection, qr_locations_collection, scan_events_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["_id"]
        supervisor_id_str = str(supervisor_id)  # Convert to string for queries
        logger.info(f"Supervisor ID: {supervisor_id_str}")
        
        # Get guard count
        logger.info("Getting guard count...")
        guard_count = await guards_collection.count_documents({"supervisorId": supervisor_id_str})
        logger.info(f"Guard count: {guard_count}")
        
        # Get QR location
        logger.info("Getting QR location...")
        qr_location = await qr_locations_collection.find_one({"supervisorId": supervisor_id_str})
        logger.info(f"QR location found: {qr_location is not None}")
        
        # Get scan statistics
        logger.info("Getting scan statistics...")
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_scans = await scan_events_collection.count_documents({
            "supervisorId": supervisor_id_str,
            "scannedAt": {"$gte": today}
        })
        
        total_scans = await scan_events_collection.count_documents({
            "supervisorId": supervisor_id_str
        })
        logger.info(f"Scans - today: {today_scans}, total: {total_scans}")
        
        result = {
            "supervisor": current_supervisor,
            "statistics": {
                "guard_count": guard_count,
                "today_scans": today_scans,
                "total_scans": total_scans,
                "has_qr_location": qr_location is not None
            },
            "qr_location": qr_location
        }
        logger.info("Dashboard data prepared successfully")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting supervisor dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get supervisor dashboard"
        )


@supervisor_router.post("/guards")
async def create_guard(
    name: str,
    employee_code: str,
    contact_number: str,
    password: str,
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor)
):
    """Create a new guard under this supervisor"""
    try:
        users_collection = get_users_collection()
        guards_collection = get_guards_collection()
        
        if not all([users_collection, guards_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["_id"]
        supervisor_area = current_supervisor.get("areaCity", "UNKNOWN")
        
        # Generate guard email
        first_name = name.split(' ')[0].lower().strip()
        clean_area = supervisor_area.lower().strip().replace(' ', '').replace('-', '')
        guard_email = f"{first_name}.{clean_area}@lh.io.in"
        
        # Check if email already exists
        existing_user = await users_collection.find_one({"email": guard_email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Guard with email {guard_email} already exists"
            )
        
        # Check if employee code already exists
        existing_guard = await guards_collection.find_one({"employeeCode": employee_code})
        if existing_guard:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Guard with employee code {employee_code} already exists"
            )
        
        # Create user
        from services.jwt_service import jwt_service
        
        user_data = {
            "email": guard_email,
            "passwordHash": jwt_service.hash_password(password),
            "name": name,
            "role": "GUARD",
            "areaCity": supervisor_area,
            "isActive": True,
            "isEmailVerified": True,  # Guards are pre-verified
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        user_result = await users_collection.insert_one(user_data)
        user_id = str(user_result.inserted_id)
        
        # Create guard profile
        guard_profile = {
            "userId": user_id,
            "supervisorId": supervisor_id,
            "employeeCode": employee_code,
            "contactNumber": contact_number,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        guard_result = await guards_collection.insert_one(guard_profile)
        
        logger.info(f"Created guard {name} with email {guard_email}")
        
        return {
            "message": "Guard created successfully",
            "guard_id": str(guard_result.inserted_id),
            "user_id": user_id,
            "email": guard_email,
            "employee_code": employee_code
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating guard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create guard"
        )


@supervisor_router.get("/guards")
async def get_supervisor_guards(
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor),
    active_only: bool = Query(True, description="Return only active guards")
):
    """Get all guards under this supervisor"""
    try:
        users_collection = get_users_collection()
        guards_collection = get_guards_collection()
        
        if not all([users_collection, guards_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["_id"]
        
        # Get guards
        guards_cursor = guards_collection.find({"supervisorId": supervisor_id})
        guards = []
        
        async for guard in guards_cursor:
            # Get user data
            user_data = await users_collection.find_one({"_id": ObjectId(guard["userId"])})
            
            if user_data:
                # Filter by active status if requested
                if active_only and not user_data.get("isActive", False):
                    continue
                
                guard_response = {
                    "guard_id": str(guard["_id"]),
                    "user_id": str(guard["userId"]),
                    "name": user_data.get("name"),
                    "email": user_data.get("email"),
                    "employee_code": guard.get("employeeCode"),
                    "contact_number": guard.get("contactNumber"),
                    "is_active": user_data.get("isActive", False),
                    "created_at": guard.get("createdAt")
                }
                guards.append(guard_response)
        
        return {"guards": guards, "count": len(guards)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting supervisor guards: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get guards"
        )


@supervisor_router.get("/scans")
async def get_supervisor_scans(
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor),
    limit: int = Query(50, ge=1, le=500, description="Number of scans to return"),
    skip: int = Query(0, ge=0, description="Number of scans to skip")
):
    """Get scans for this supervisor's area"""
    try:
        scan_events_collection = get_scan_events_collection()
        
        if not scan_events_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["_id"]
        
        # Get scans with pagination
        scans_cursor = scan_events_collection.find(
            {"supervisorId": supervisor_id}
        ).sort("scannedAt", -1).skip(skip).limit(limit)
        
        scans = []
        async for scan in scans_cursor:
            scan_response = {
                **scan,
                "_id": str(scan["_id"])
            }
            scans.append(scan_response)
        
        return {"scans": scans, "count": len(scans)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting supervisor scans: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scans"
        )
