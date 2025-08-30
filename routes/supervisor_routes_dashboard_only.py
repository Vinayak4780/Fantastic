"""
Supervisor routes for QR location management and guard oversight
SUPERVISOR role only - manage QR locations, view assigned guards, and access scan data
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from bson import ObjectId

# Import services and dependencies
from services.auth_service import get_current_supervisor
from services.tomtom_service import tomtom_service
from database import (
    get_supervisors_collection, get_guards_collection, get_qr_locations_collection,
    get_scan_events_collection, get_users_collection
)
from config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Create router
supervisor_router = APIRouter()


@supervisor_router.get("/dashboard")
async def get_supervisor_dashboard(current_supervisor: Dict[str, Any] = Depends(get_current_supervisor)):
    """
    Supervisor dashboard with assigned area statistics
    """
    try:
        supervisors_collection = get_supervisors_collection()
        guards_collection = get_guards_collection()
        qr_locations_collection = get_qr_locations_collection()
        scan_events_collection = get_scan_events_collection()
        
        if (supervisors_collection is None or guards_collection is None or 
            qr_locations_collection is None or scan_events_collection is None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["supervisor_id"]
        
        # Get assigned guards count
        assigned_guards = await guards_collection.count_documents({"supervisorId": ObjectId(supervisor_id)})
        
        # Get QR locations count  
        qr_locations = await qr_locations_collection.count_documents({"supervisorId": ObjectId(supervisor_id)})
        
        # Get today's scan statistics - since scans don't have supervisorId, count all scans
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_scans = await scan_events_collection.count_documents({
            "scannedAt": {"$gte": today_start}
        })
        
        # Get this week's scan statistics - count all scans
        week_start = today_start - timedelta(days=today_start.weekday())
        this_week_scans = await scan_events_collection.count_documents({
            "scannedAt": {"$gte": week_start}
        })
        
        # Get recent scan events - all scans since we don't have supervisorId in scans
        recent_scans_cursor = scan_events_collection.find({}).sort("scannedAt", -1).limit(10)
        
        recent_scans = await recent_scans_cursor.to_list(length=None)
        
        # Get guards with most activity - using guardEmail since supervisorId not in scans
        guard_activity_pipeline = [
            {"$match": {
                "scannedAt": {"$gte": week_start}
            }},
            {"$group": {
                "_id": "$guardEmail",
                "scan_count": {"$sum": 1}
            }},
            {"$sort": {"scan_count": -1}},
            {"$limit": 5},
            {"$project": {
                "guard_email": "$_id",
                "scan_count": 1,
                "_id": 0
            }}
        ]
        
        guard_activity = await scan_events_collection.aggregate(guard_activity_pipeline).to_list(length=None)
        
        # Guard activity already has proper structure, no ObjectId conversion needed
        
        return {
            "statistics": {
                "assigned_guards": assigned_guards,
                "qr_locations": qr_locations,
                "today_scans": today_scans,
                "this_week_scans": this_week_scans
            },
            "recent_scans": [
                {
                    "id": str(scan["_id"]),
                    "guard_email": scan.get("guardEmail", ""),
                    "guard_id": str(scan.get("guardId", "")),
                    "qr_id": scan.get("qrId", ""),
                    "original_scan_content": scan.get("originalScanContent", ""),
                    "location_name": scan.get("locationName", "Unknown Location"),
                    "scanned_at": scan.get("scannedAt"),
                    "timestamp": scan.get("timestampIST", ""),
                    "device_lat": scan.get("deviceLat", 0),
                    "device_lng": scan.get("deviceLng", 0),
                    "address": scan.get("address", ""),
                    "formatted_address": scan.get("formatted_address", ""),
                    "address_lookup_success": scan.get("address_lookup_success", False)
                }
                for scan in recent_scans
            ],
            "guard_activity": guard_activity,
            "area_info": {
                "city": current_supervisor["areaCity"],
                "state": current_supervisor.get("areaState"),
                "country": current_supervisor.get("areaCountry")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Supervisor dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )
