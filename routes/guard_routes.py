"""
Guard routes for QR scanning and patrol activities
GUARD role only - scan QR codes, view scan history, and manage patrol activities
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from bson import ObjectId
from geopy.distance import geodesic

# Import services and dependencies
from services.auth_service import get_current_guard
from services.tomtom_service import tomtom_service
from services.excel_service import excel_service
from database import (
    get_guards_collection, get_qr_locations_collection, get_scan_events_collection,
    get_supervisors_collection
)
from config import settings

# Import models
from models import (
    QRScanRequest, QRScanResponse, ScanEventResponse, GuardProfileResponse,
    SuccessResponse, Coordinates
)

logger = logging.getLogger(__name__)

# Create router
guard_router = APIRouter()


@guard_router.get("/dashboard")
async def get_guard_dashboard(current_guard: Dict[str, Any] = Depends(get_current_guard)):
    """
    Guard dashboard with personal scan statistics and recent activity
    """
    try:
        guards_collection = get_guards_collection()
        scan_events_collection = get_scan_events_collection()
        qr_locations_collection = get_qr_locations_collection()
        
        if not all([guards_collection, scan_events_collection, qr_locations_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["guard_id"]
        supervisor_id = current_guard["supervisor_id"]
        
        # Get today's scan statistics
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_scans = await scan_events_collection.count_documents({
            "guardId": ObjectId(guard_id),
            "scannedAt": {"$gte": today_start}
        })
        
        # Get this week's scan statistics
        week_start = today_start - timedelta(days=today_start.weekday())
        this_week_scans = await scan_events_collection.count_documents({
            "guardId": ObjectId(guard_id),
            "scannedAt": {"$gte": week_start}
        })
        
        # Get total scans
        total_scans = await scan_events_collection.count_documents({
            "guardId": ObjectId(guard_id)
        })
        
        # Get scans within radius percentage
        within_radius_scans = await scan_events_collection.count_documents({
            "guardId": ObjectId(guard_id),
            "isWithinRadius": True
        })
        
        within_radius_percentage = (within_radius_scans / total_scans * 100) if total_scans > 0 else 0
        
        # Get recent scan events
        recent_scans_cursor = scan_events_collection.find({
            "guardId": ObjectId(guard_id)
        }).sort("scannedAt", -1).limit(10)
        
        recent_scans = await recent_scans_cursor.to_list(length=None)
        
        # Get available QR locations in the area
        available_qr_locations = await qr_locations_collection.count_documents({
            "supervisorId": ObjectId(supervisor_id),
            "isActive": True
        })
        
        # Get last scan time
        last_scan = await scan_events_collection.find_one(
            {"guardId": ObjectId(guard_id)},
            sort=[("scannedAt", -1)]
        )
        
        return {
            "statistics": {
                "today_scans": today_scans,
                "this_week_scans": this_week_scans,
                "total_scans": total_scans,
                "within_radius_percentage": round(within_radius_percentage, 1),
                "available_qr_locations": available_qr_locations
            },
            "recent_scans": [
                {
                    "id": str(scan["_id"]),
                    "location_name": scan["locationName"],
                    "scanned_at": scan["scannedAt"],
                    "is_within_radius": scan["isWithinRadius"],
                    "distance_from_qr": scan.get("distanceFromQR", 0.0)
                }
                for scan in recent_scans
            ],
            "last_scan_time": last_scan["scannedAt"] if last_scan else None,
            "guard_info": {
                "name": current_guard["name"],
                "email": current_guard["email"],
                "area_city": current_guard["areaCity"],
                "shift": current_guard["shift"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Guard dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )


@guard_router.post("/scan-qr", response_model=QRScanResponse)
async def scan_qr_code(
    scan_request: QRScanRequest,
    current_guard: Dict[str, Any] = Depends(get_current_guard)
):
    """
    Scan QR code and record patrol activity with GPS validation
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        scan_events_collection = get_scan_events_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([qr_locations_collection, scan_events_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["guard_id"]
        supervisor_id = current_guard["supervisor_id"]
        
        # Find QR location
        qr_location = await qr_locations_collection.find_one({
            "qrId": scan_request.qrId,
            "supervisorId": ObjectId(supervisor_id),
            "isActive": True
        })
        
        if not qr_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QR code not found or inactive"
            )
        
        # Calculate distance between guard's GPS and QR location
        guard_location = (scan_request.coordinates.latitude, scan_request.coordinates.longitude)
        qr_location_coords = (
            qr_location["coordinates"]["latitude"],
            qr_location["coordinates"]["longitude"]
        )
        
        distance_meters = geodesic(guard_location, qr_location_coords).meters
        is_within_radius = distance_meters <= settings.WITHIN_RADIUS_METERS
        
        # Get address from guard's current location using TomTom
        current_address = ""
        try:
            geocode_result = await tomtom_service.reverse_geocode_enhanced(
                scan_request.coordinates.latitude,
                scan_request.coordinates.longitude
            )
            if geocode_result:
                current_address = geocode_result.get("formatted_address", "")
        except Exception as e:
            logger.warning(f"Failed to geocode current address: {e}")
        
        # Create scan event document
        scan_event_doc = {
            "guardId": ObjectId(guard_id),
            "supervisorId": ObjectId(supervisor_id),
            "qrLocationId": qr_location["_id"],
            "qrId": scan_request.qrId,
            "locationName": qr_location["locationName"],
            "coordinates": {
                "latitude": scan_request.coordinates.latitude,
                "longitude": scan_request.coordinates.longitude
            },
            "address": current_address,
            "areaCity": qr_location["areaCity"],
            "areaState": qr_location["areaState"],
            "areaCountry": qr_location["areaCountry"],
            "isWithinRadius": is_within_radius,
            "distanceFromQR": round(distance_meters, 2),
            "scannedAt": datetime.utcnow(),
            "notes": scan_request.notes
        }
        
        # Insert scan event
        result = await scan_events_collection.insert_one(scan_event_doc)
        
        # Log to Google Sheets (async, don't wait for it)
        try:
            supervisor = await supervisors_collection.find_one({"_id": ObjectId(supervisor_id)})
            if supervisor and supervisor.get("sheetId"):
                # Create scan event data for sheets
                scan_event_data = {
                    "guard_name": current_guard["name"],
                    "guard_email": current_guard["email"],
                    "location_name": qr_location["locationName"],
                    "qr_id": scan_request.qrId,
                    "scanned_at": scan_event_doc["scannedAt"],
                    "coordinates": scan_request.coordinates,
                    "address": current_address,
                    "is_within_radius": is_within_radius,
                    "distance_from_qr": round(distance_meters, 2),
                    "notes": scan_request.notes
                }
                
                await excel_service.append_scan_to_sheet(
                    supervisor["sheetId"],
                    supervisor["areaCity"],
                    scan_event_data
                )
        except Exception as e:
            logger.warning(f"Failed to log to Google Sheets: {e}")
        
        # Prepare response
        response = QRScanResponse(
            scanEventId=str(result.inserted_id),
            qrId=scan_request.qrId,
            locationName=qr_location["locationName"],
            isWithinRadius=is_within_radius,
            distanceFromQR=round(distance_meters, 2),
            address=current_address,
            scannedAt=scan_event_doc["scannedAt"],
            message="QR code scanned successfully" if is_within_radius else f"Warning: You are {round(distance_meters, 1)}m away from the QR location"
        )
        
        logger.info(f"Guard {current_guard['email']} scanned QR {scan_request.qrId} - Within radius: {is_within_radius}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"QR scan error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process QR scan"
        )


@guard_router.get("/scan-history", response_model=List[ScanEventResponse])
async def get_scan_history(
    current_guard: Dict[str, Any] = Depends(get_current_guard),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    qr_id: Optional[str] = Query(None, description="Filter by QR ID"),
    within_radius_only: Optional[bool] = Query(None, description="Show only scans within radius"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """
    Get guard's scan history with optional filtering
    """
    try:
        scan_events_collection = get_scan_events_collection()
        if not scan_events_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["guard_id"]
        
        # Build filter
        filter_query = {"guardId": ObjectId(guard_id)}
        
        if start_date and end_date:
            filter_query["scannedAt"] = {"$gte": start_date, "$lte": end_date}
        elif start_date:
            filter_query["scannedAt"] = {"$gte": start_date}
        elif end_date:
            filter_query["scannedAt"] = {"$lte": end_date}
        
        if qr_id:
            filter_query["qrId"] = qr_id
        
        if within_radius_only is not None:
            filter_query["isWithinRadius"] = within_radius_only
        
        # Get scan events
        cursor = scan_events_collection.find(filter_query).skip(skip).limit(limit).sort("scannedAt", -1)
        scan_events = await cursor.to_list(length=None)
        
        # Convert to response models
        scan_responses = []
        for event in scan_events:
            response = ScanEventResponse(
                id=str(event["_id"]),
                guardId=str(event["guardId"]),
                guardName=current_guard["name"],
                guardEmail=current_guard["email"],
                qrLocationId=str(event["qrLocationId"]),
                locationName=event["locationName"],
                coordinates=Coordinates(
                    latitude=event["coordinates"]["latitude"],
                    longitude=event["coordinates"]["longitude"]
                ),
                address=event.get("address", ""),
                areaCity=event["areaCity"],
                isWithinRadius=event["isWithinRadius"],
                distanceFromQR=event.get("distanceFromQR", 0.0),
                scannedAt=event["scannedAt"]
            )
            scan_responses.append(response)
        
        return scan_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get scan history error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scan history"
        )


@guard_router.get("/available-qr-locations")
async def get_available_qr_locations(current_guard: Dict[str, Any] = Depends(get_current_guard)):
    """
    Get list of available QR locations in guard's assigned area
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        if not qr_locations_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_guard["supervisor_id"]
        
        # Get active QR locations for this supervisor
        cursor = qr_locations_collection.find({
            "supervisorId": ObjectId(supervisor_id),
            "isActive": True
        }).sort("locationName", 1)
        
        qr_locations = await cursor.to_list(length=None)
        
        # Return simplified location data
        locations = []
        for qr in qr_locations:
            location_data = {
                "qr_id": qr["qrId"],
                "location_name": qr["locationName"],
                "coordinates": {
                    "latitude": qr["coordinates"]["latitude"],
                    "longitude": qr["coordinates"]["longitude"]
                },
                "address": qr.get("address", ""),
                "area_city": qr["areaCity"]
            }
            locations.append(location_data)
        
        return {
            "locations": locations,
            "total_count": len(locations),
            "area_city": current_guard["areaCity"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get available QR locations error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get available QR locations"
        )


@guard_router.get("/profile", response_model=GuardProfileResponse)
async def get_guard_profile(current_guard: Dict[str, Any] = Depends(get_current_guard)):
    """
    Get guard's profile information
    """
    try:
        guards_collection = get_guards_collection()
        if not guards_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["guard_id"]
        
        # Get guard details
        guard = await guards_collection.find_one({"_id": ObjectId(guard_id)})
        if not guard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Guard profile not found"
            )
        
        response = GuardProfileResponse(
            id=str(guard["_id"]),
            userId=str(guard["userId"]),
            supervisorId=str(guard["supervisorId"]),
            email=current_guard["email"],
            name=current_guard["name"],
            areaCity=current_guard["areaCity"],
            shift=guard["shift"],
            phoneNumber=guard["phoneNumber"],
            emergencyContact=guard["emergencyContact"],
            isActive=current_guard["isActive"],
            createdAt=guard["createdAt"],
            updatedAt=guard["updatedAt"]
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get guard profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get guard profile"
        )


@guard_router.get("/patrol-summary")
async def get_patrol_summary(
    current_guard: Dict[str, Any] = Depends(get_current_guard),
    date: Optional[datetime] = Query(None, description="Get summary for specific date (defaults to today)")
):
    """
    Get patrol summary for a specific date
    """
    try:
        scan_events_collection = get_scan_events_collection()
        qr_locations_collection = get_qr_locations_collection()
        
        if not all([scan_events_collection, qr_locations_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        guard_id = current_guard["guard_id"]
        supervisor_id = current_guard["supervisor_id"]
        
        # Use provided date or default to today
        target_date = date if date else datetime.utcnow()
        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        # Get day's scan events
        day_scans = await scan_events_collection.find({
            "guardId": ObjectId(guard_id),
            "scannedAt": {"$gte": day_start, "$lt": day_end}
        }).sort("scannedAt", 1).to_list(length=None)
        
        # Get total available QR locations
        total_locations = await qr_locations_collection.count_documents({
            "supervisorId": ObjectId(supervisor_id),
            "isActive": True
        })
        
        # Get unique locations scanned
        scanned_qr_ids = set(scan["qrId"] for scan in day_scans)
        unique_locations_scanned = len(scanned_qr_ids)
        
        # Calculate coverage percentage
        coverage_percentage = (unique_locations_scanned / total_locations * 100) if total_locations > 0 else 0
        
        # Calculate within radius percentage
        within_radius_scans = sum(1 for scan in day_scans if scan["isWithinRadius"])
        within_radius_percentage = (within_radius_scans / len(day_scans) * 100) if day_scans else 0
        
        # Get first and last scan times
        first_scan_time = day_scans[0]["scannedAt"] if day_scans else None
        last_scan_time = day_scans[-1]["scannedAt"] if day_scans else None
        
        return {
            "date": day_start.date(),
            "summary": {
                "total_scans": len(day_scans),
                "unique_locations_scanned": unique_locations_scanned,
                "total_available_locations": total_locations,
                "coverage_percentage": round(coverage_percentage, 1),
                "within_radius_percentage": round(within_radius_percentage, 1),
                "first_scan_time": first_scan_time,
                "last_scan_time": last_scan_time
            },
            "scans": [
                {
                    "qr_id": scan["qrId"],
                    "location_name": scan["locationName"],
                    "scanned_at": scan["scannedAt"],
                    "is_within_radius": scan["isWithinRadius"],
                    "distance_from_qr": scan.get("distanceFromQR", 0.0)
                }
                for scan in day_scans
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get patrol summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get patrol summary"
        )
