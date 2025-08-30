"""
Guard routes for QR scanning and attendance marking
GUARD role only - scan QR codes and view own scan history
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from bson import ObjectId

# Import services and dependencies
from services.auth_service import get_current_guard
from database import get_scan_events_collection
from config import settings

logger = logging.getLogger(__name__)

# Create router
guard_router = APIRouter()


@guard_router.get("/profile")
async def get_guard_profile(current_guard: Dict[str, Any] = Depends(get_current_guard)):
    """Get guard profile and statistics"""
    try:
        scan_events_collection = get_scan_events_collection()
        
        if scan_events_collection is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["_id"]
        guard_email = current_guard.get("email", "")
        
        # Get scan statistics - use guardEmail to find scans
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_scans = await scan_events_collection.count_documents({
            "guardEmail": guard_email,
            "scannedAt": {"$gte": today}
        })
        
        total_scans = await scan_events_collection.count_documents({
            "guardEmail": guard_email
        })
        
        # Convert ObjectId fields to strings for JSON serialization
        guard_data = {
            "_id": str(current_guard["_id"]),
            "email": current_guard.get("email", ""),
            "name": current_guard.get("name", ""),
            "role": current_guard.get("role", ""),
            "isActive": current_guard.get("isActive", True),
            "createdAt": current_guard.get("createdAt"),
            "lastLoginAt": current_guard.get("lastLoginAt")
        }
        
        return {
            "guard": guard_data,
            "statistics": {
                "today_scans": today_scans,
                "total_scans": total_scans
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting guard profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get guard profile"
        )


@guard_router.get("/scans")
async def get_guard_scans(
    current_guard: Dict[str, Any] = Depends(get_current_guard),
    limit: int = Query(50, ge=1, le=500, description="Number of scans to return"),
    skip: int = Query(0, ge=0, description="Number of scans to skip")
):
    """Get guard's own scan history"""
    try:
        scan_events_collection = get_scan_events_collection()
        
        if scan_events_collection is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["_id"]
        
        # Get scans with pagination - look for guard's email instead of guardId
        guard_email = current_guard.get("email", "")
        
        scans_cursor = scan_events_collection.find(
            {"guardEmail": guard_email}
        ).sort("scannedAt", -1).skip(skip).limit(limit)
        
        scans = []
        async for scan in scans_cursor:
            scan_data = {
                "_id": str(scan["_id"]),
                "guardId": str(scan.get("guardId", "")),
                "guardEmail": scan.get("guardEmail", ""),
                "qrId": str(scan.get("qrId", "")),
                "originalScanContent": scan.get("originalScanContent", ""),
                "scannedAt": scan.get("scannedAt"),
                "scannedLat": scan.get("deviceLat"),  # Map deviceLat to scannedLat
                "scannedLng": scan.get("deviceLng"),  # Map deviceLng to scannedLng
                "deviceLat": scan.get("deviceLat"),
                "deviceLng": scan.get("deviceLng"),
                "locationAddress": scan.get("address", ""),
                "formatted_address": scan.get("formatted_address", ""),
                "address_components": scan.get("address_components", {}),
                "address_lookup_success": scan.get("address_lookup_success", False),
                "timestamp": scan.get("timestampIST", ""),
                "timestampIST": scan.get("timestampIST", ""),
                "locationUpdated": scan.get("locationUpdated", False),
                "status": scan.get("status", "")
            }
            scans.append(scan_data)
        
        return scans
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting guard scans: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scans"
        )


@guard_router.post("/scan")
async def scan_qr_code(
    qr_id: str,
    device_lat: float,
    device_lng: float,
    current_guard: Dict[str, Any] = Depends(get_current_guard)
):
    """
    Scan QR code and create scan event (simplified version)
    """
    try:
        from services.google_drive_excel_service import google_drive_excel_service
        from datetime import timezone, timedelta
        
        scan_events_collection = get_scan_events_collection()
        
        if scan_events_collection is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["_id"]
        
        # Create scan event (simplified)
        scanned_at = datetime.utcnow()
        
        # Convert to IST for Excel
        ist_timezone = timezone(timedelta(hours=5, minutes=30))
        scanned_at_ist = scanned_at.astimezone(ist_timezone)
        timestamp_ist = scanned_at_ist.strftime("%d-%m-%Y %H:%M:%S")
        
        scan_event = {
            "qrId": qr_id,
            "guardId": guard_id,
            "deviceLat": device_lat,
            "deviceLng": device_lng,
            "scannedAt": scanned_at,
            "createdAt": datetime.utcnow(),
            "timestampIST": timestamp_ist
        }
        
        # Insert scan event
        result = await scan_events_collection.insert_one(scan_event)
        scan_event["_id"] = str(result.inserted_id)
        
        # Log to Google Drive Excel
        try:
            scan_data_for_excel = {
                "timestamp": timestamp_ist,
                "date": timestamp_ist.split(' ')[0] if ' ' in timestamp_ist else timestamp_ist,
                "time": timestamp_ist.split(' ')[1] if ' ' in timestamp_ist else "00:00:00",
                "guard_name": current_guard.get("name", "Unknown"),
                "guard_email": current_guard.get("email", ""),
                "employee_code": "",  # Guard profile not available in simple version
                "supervisor_name": "Supervisor Name",
                "supervisor_area": "Area City",
                "area_city": "Area City", 
                "qr_location": f"QR {qr_id}",
                "latitude": device_lat,
                "longitude": device_lng,
                "distance_meters": 0.0,
                "status": "SUCCESS",
                "address": "Address not available",
                "landmark": "",
                "remarks": "Guard scan"
            }
            
            await google_drive_excel_service.add_scan_to_queue(scan_data_for_excel)
            
        except Exception as e:
            logger.error(f"Failed to log to Excel: {e}")
        
        logger.info(f"Guard {current_guard.get('name')} scanned QR {qr_id}")
        
        return {
            "message": "QR code scanned successfully",
            "scan_id": str(scan_event["_id"]),
            "timestamp": timestamp_ist
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing QR scan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process QR scan"
        )
