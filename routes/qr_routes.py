"""
QR Code routes for public QR scanning and location verification
Public endpoint for QR scanning without authentication (guard app integration)
Also includes supervisor QR generation endpoints
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from bson import ObjectId
import qrcode
import io
import base64
from geopy.distance import geodesic

# Import services and dependencies
from services.auth_service import get_current_supervisor
from services.tomtom_service import tomtom_service
from services.excel_service import excel_service
from database import (
    get_qr_locations_collection, get_scan_events_collection, get_guards_collection,
    get_supervisors_collection, get_users_collection
)
from config import settings

# Import models
from models import (
    QRCodePublicScanRequest, QRCodePublicScanResponse, QRLocationResponse,
    QRCodeGenerateRequest, QRCodeGenerateResponse, SuccessResponse,
    Coordinates
)

logger = logging.getLogger(__name__)

# Create router
qr_router = APIRouter()


@qr_router.post("/public/scan", response_model=QRCodePublicScanResponse)
async def public_scan_qr_code(scan_request: QRCodePublicScanRequest):
    """
    Public QR code scanning endpoint for guard mobile app
    Does not require authentication - uses guard email for identification
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        scan_events_collection = get_scan_events_collection()
        guards_collection = get_guards_collection()
        users_collection = get_users_collection()
        supervisors_collection = get_supervisors_collection()
        
        if not all([qr_locations_collection, scan_events_collection, guards_collection, users_collection, supervisors_collection]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Find guard by email
        guard_user = await users_collection.find_one({
            "email": scan_request.guardEmail,
            "role": "GUARD",
            "isActive": True
        })
        
        if not guard_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Guard not found or inactive"
            )
        
        # Get guard details
        guard = await guards_collection.find_one({"userId": guard_user["_id"]})
        if not guard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Guard profile not found"
            )
        
        supervisor_id = guard["supervisorId"]
        
        # Find QR location
        qr_location = await qr_locations_collection.find_one({
            "qrId": scan_request.qrId,
            "supervisorId": supervisor_id,
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
            "guardId": guard["_id"],
            "supervisorId": supervisor_id,
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
            "notes": scan_request.notes,
            "deviceInfo": scan_request.deviceInfo
        }
        
        # Insert scan event
        result = await scan_events_collection.insert_one(scan_event_doc)
        
        # Log to Google Sheets (async, don't wait for it)
        try:
            supervisor = await supervisors_collection.find_one({"_id": supervisor_id})
            if supervisor and supervisor.get("sheetId"):
                # Create scan event data for sheets
                scan_event_data = {
                    "guard_name": guard_user["name"],
                    "guard_email": guard_user["email"],
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
        response = QRCodePublicScanResponse(
            scanEventId=str(result.inserted_id),
            success=True,
            qrId=scan_request.qrId,
            locationName=qr_location["locationName"],
            isWithinRadius=is_within_radius,
            distanceFromQR=round(distance_meters, 2),
            radiusLimit=settings.WITHIN_RADIUS_METERS,
            address=current_address,
            scannedAt=scan_event_doc["scannedAt"],
            message="QR code scanned successfully" if is_within_radius else f"Warning: You are {round(distance_meters, 1)}m away from the QR location",
            guardName=guard_user["name"],
            areaCity=qr_location["areaCity"]
        )
        
        logger.info(f"Public scan: Guard {scan_request.guardEmail} scanned QR {scan_request.qrId} - Within radius: {is_within_radius}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public QR scan error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process QR scan"
        )


@qr_router.get("/public/location/{qr_id}")
async def get_qr_location_info(qr_id: str):
    """
    Get QR location information (public endpoint for guard app)
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        if not qr_locations_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Find QR location
        qr_location = await qr_locations_collection.find_one({
            "qrId": qr_id,
            "isActive": True
        })
        
        if not qr_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QR location not found"
            )
        
        return {
            "qr_id": qr_location["qrId"],
            "location_name": qr_location["locationName"],
            "coordinates": {
                "latitude": qr_location["coordinates"]["latitude"],
                "longitude": qr_location["coordinates"]["longitude"]
            },
            "address": qr_location.get("address", ""),
            "area_city": qr_location["areaCity"],
            "area_state": qr_location.get("areaState", ""),
            "area_country": qr_location.get("areaCountry", ""),
            "radius_limit": settings.WITHIN_RADIUS_METERS
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get QR location info error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get QR location information"
        )


@qr_router.post("/generate", response_model=QRCodeGenerateResponse)
async def generate_qr_code(
    qr_request: QRCodeGenerateRequest,
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor)
):
    """
    Generate QR code image for a QR location (supervisor only)
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        if not qr_locations_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["supervisor_id"]
        
        # Check if QR location exists and belongs to this supervisor
        qr_location = await qr_locations_collection.find_one({
            "qrId": qr_request.qrId,
            "supervisorId": ObjectId(supervisor_id),
            "isActive": True
        })
        
        if not qr_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QR location not found"
            )
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=qr_request.size,
            border=4,
        )
        
        # QR code data includes the QR ID
        qr_data = qr_request.qrId
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        response = QRCodeGenerateResponse(
            qrId=qr_request.qrId,
            locationName=qr_location["locationName"],
            qrCodeImage=f"data:image/png;base64,{img_base64}",
            size=qr_request.size,
            coordinates=Coordinates(
                latitude=qr_location["coordinates"]["latitude"],
                longitude=qr_location["coordinates"]["longitude"]
            ),
            address=qr_location.get("address", ""),
            generatedAt=datetime.utcnow()
        )
        
        logger.info(f"Supervisor {current_supervisor['email']} generated QR code for {qr_request.qrId}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate QR code error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR code"
        )


@qr_router.get("/validate/{qr_id}")
async def validate_qr_code(qr_id: str):
    """
    Validate if QR code exists and is active (public endpoint)
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        if not qr_locations_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Check if QR location exists and is active
        qr_location = await qr_locations_collection.find_one({
            "qrId": qr_id,
            "isActive": True
        })
        
        if not qr_location:
            return {
                "valid": False,
                "qr_id": qr_id,
                "message": "QR code not found or inactive"
            }
        
        return {
            "valid": True,
            "qr_id": qr_id,
            "location_name": qr_location["locationName"],
            "area_city": qr_location["areaCity"],
            "message": "QR code is valid and active"
        }
        
    except Exception as e:
        logger.error(f"Validate QR code error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate QR code"
        )


@qr_router.get("/bulk-generate")
async def bulk_generate_qr_codes(
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor),
    size: int = Query(10, ge=5, le=50, description="QR code box size"),
    format: str = Query("zip", description="Output format: zip or json")
):
    """
    Generate QR codes for all active locations of this supervisor
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        if not qr_locations_collection:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_id = current_supervisor["supervisor_id"]
        
        # Get all active QR locations for this supervisor
        cursor = qr_locations_collection.find({
            "supervisorId": ObjectId(supervisor_id),
            "isActive": True
        }).sort("locationName", 1)
        
        qr_locations = await cursor.to_list(length=None)
        
        if not qr_locations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active QR locations found"
            )
        
        qr_codes = []
        
        for qr_location in qr_locations:
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=size,
                border=4,
            )
            
            qr.add_data(qr_location["qrId"])
            qr.make(fit=True)
            
            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
            qr_code_data = {
                "qr_id": qr_location["qrId"],
                "location_name": qr_location["locationName"],
                "qr_code_image": f"data:image/png;base64,{img_base64}",
                "coordinates": {
                    "latitude": qr_location["coordinates"]["latitude"],
                    "longitude": qr_location["coordinates"]["longitude"]
                },
                "address": qr_location.get("address", "")
            }
            
            qr_codes.append(qr_code_data)
        
        response = {
            "supervisor_area": current_supervisor["areaCity"],
            "total_qr_codes": len(qr_codes),
            "qr_codes": qr_codes,
            "generated_at": datetime.utcnow(),
            "size": size
        }
        
        logger.info(f"Supervisor {current_supervisor['email']} generated {len(qr_codes)} QR codes")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk generate QR codes error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR codes"
        )
