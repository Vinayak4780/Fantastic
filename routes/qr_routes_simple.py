"""
Ultra-Simple QR Code routes - MINIMAL ESSENTIAL APIs ONLY
Only includes:
1. GET /qr/my-qr-image - Supervisor gets QR code image (no parameters needed)
2. POST /qr/scan - Guard scans QR code and saves GPS coordinates
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from typing import Dict, Any
import logging
from bson import ObjectId
import qrcode
import io
import base64
from datetime import datetime, timezone, timedelta

# Import services and dependencies
from services.auth_service import get_current_supervisor
from database import get_qr_locations_collection, get_scan_events_collection
from config import settings

logger = logging.getLogger(__name__)

# Create router
qr_router = APIRouter()


# ============================================================================
# SUPERVISOR ENDPOINT - QR Generation (ONLY ESSENTIAL API)
# ============================================================================

@qr_router.get("/my-qr-image")
async def get_my_qr_image(
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor)
):
    """
    SUPERVISOR ONLY: Get your QR code as direct image - NO PARAMETERS NEEDED
    Creates QR if doesn't exist, or returns existing QR image
    Perfect for camera scanning - just call this endpoint!
    """
    try:
        qr_locations_collection = get_qr_locations_collection()
        supervisor_id_str = str(current_supervisor["_id"])
        
        # Find or create QR location for this supervisor
        existing_qr = await qr_locations_collection.find_one({"supervisorId": supervisor_id_str})
        
        if not existing_qr:
            # Create new QR location automatically
            default_label = f"Guard Point - {current_supervisor.get('email', 'Supervisor')}"
            new_qr_location = {
                "supervisorId": supervisor_id_str,
                "supervisorEmail": current_supervisor.get("email"),
                "supervisorArea": current_supervisor.get("area", "Unknown"),
                "label": default_label,
                "lat": 0.0,
                "lng": 0.0,
                "isActive": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
                "firstScanUpdate": False
            }
            
            result = await qr_locations_collection.insert_one(new_qr_location)
            qr_id = str(result.inserted_id)
        else:
            qr_id = str(existing_qr["_id"])
        
        # Generate QR code
        qr_content = f"GUARD_QR_{qr_id}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=15,
            border=6,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        
        # Create high-quality image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return as image - ready for camera scanning
        return StreamingResponse(
            io.BytesIO(img_buffer.getvalue()),
            media_type="image/png",
            headers={
                "Content-Disposition": f"inline; filename=Guard_QR.png"
            }
        )
        
    except Exception as e:
        # Simple error without detailed logging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR"
        )


# ============================================================================
# GUARD ENDPOINT - QR Scanning (ONLY ESSENTIAL API)
# ============================================================================

@qr_router.post("/scan")
async def scan_qr_code(
    scanned_content: str,
    guard_email: str,
    device_lat: float,
    device_lng: float
):
    """
    GUARD ONLY: Camera QR scanning endpoint
    Optimized for mobile apps - automatically extracts QR ID from scanned content
    """
    try:
        from services.google_drive_excel_service import google_drive_excel_service
        from services.tomtom_service import tomtom_service
        
        scan_events_collection = get_scan_events_collection()
        qr_locations_collection = get_qr_locations_collection()
        
        if scan_events_collection is None or qr_locations_collection is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Extract QR ID from scanned content (handle different formats)
        qr_id = scanned_content.strip()
        
        # Handle different QR content formats
        if qr_id.startswith("GUARD_QR_"):
            actual_qr_id = qr_id.replace("GUARD_QR_", "")
        elif qr_id.startswith("QR_"):
            actual_qr_id = qr_id.replace("QR_", "")
        elif len(qr_id) == 24:  # MongoDB ObjectId length
            actual_qr_id = qr_id
        else:
            # Try to extract ObjectId pattern
            import re
            object_id_match = re.search(r'([a-f0-9]{24})', qr_id)
            if object_id_match:
                actual_qr_id = object_id_match.group(1)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid QR code format: {scanned_content}"
                )
        
        # Validate QR code exists
        try:
            qr_location = await qr_locations_collection.find_one({"_id": ObjectId(actual_qr_id)})
        except:
            qr_location = None
        
        if not qr_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"QR code not found: {actual_qr_id}"
            )
        
        if not qr_location.get("active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QR code is inactive"
            )
        
        # Update QR location coordinates if they are default (0,0) - first scan
        location_updated = False
        if qr_location.get("lat", 0) == 0.0 and qr_location.get("lng", 0) == 0.0:
            await qr_locations_collection.update_one(
                {"_id": ObjectId(actual_qr_id)},
                {
                    "$set": {
                        "lat": device_lat,
                        "lng": device_lng,
                        "updatedAt": datetime.utcnow(),
                        "firstScanUpdate": True
                    }
                }
            )
            location_updated = True
            logger.info(f"Updated QR location {actual_qr_id} with coordinates from first scan")
        
        # Get address from GPS coordinates using TomTom API
        address_info = await tomtom_service.get_address_from_coordinates(device_lat, device_lng)
        
        # Create scan event
        scanned_at = datetime.utcnow()
        
        # Convert to IST for Excel
        ist_timezone = timezone(timedelta(hours=5, minutes=30))
        scanned_at_ist = scanned_at.astimezone(ist_timezone)
        timestamp_ist = scanned_at_ist.strftime("%d-%m-%Y %H:%M:%S")
        
        scan_event = {
            "qrId": actual_qr_id,
            "originalScanContent": scanned_content,
            "guardEmail": guard_email,
            "deviceLat": device_lat,
            "deviceLng": device_lng,
            "scannedAt": scanned_at,
            "createdAt": datetime.utcnow(),
            "timestampIST": timestamp_ist,
            "locationUpdated": location_updated,
            # Add address information
            "address": address_info.get("address", f"Location at {device_lat:.4f}, {device_lng:.4f}"),
            "formatted_address": address_info.get("formatted_address", ""),
            "address_components": address_info.get("components", {}),
            "address_lookup_success": address_info.get("success", False)
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
                "guard_name": guard_email.split('@')[0],  # Extract name from email
                "guard_email": guard_email,
                "employee_code": "",
                "supervisor_name": qr_location.get("supervisorName", "Supervisor"),
                "supervisor_area": qr_location.get("supervisorArea", "Unknown"),
                "area_city": qr_location.get("supervisorArea", "Unknown"),
                "qr_location": qr_location.get("label", f"QR {actual_qr_id}"),
                "latitude": device_lat,
                "longitude": device_lng,
                "distance_meters": 0.0,
                "status": "SUCCESS",
                "address": address_info.get("address", "Address not available"),
                "landmark": address_info.get("formatted_address", ""),
                "remarks": f"Camera scan {('(First scan - location set)' if location_updated else '')} - {address_info.get('address', 'Location recorded')}"
            }
            
            await google_drive_excel_service.add_scan_to_queue(scan_data_for_excel)
            
        except Exception as e:
            logger.error(f"Failed to log to Excel: {e}")
        
        logger.info(f"QR scan: {guard_email} scanned {scanned_content} -> {actual_qr_id}")
        
        return {
            "message": "QR code scanned successfully",
            "scan_id": scan_event["_id"],
            "timestamp": timestamp_ist,
            "qr_id": actual_qr_id,
            "qr_label": qr_location.get("label", "Patrol Point"),
            "supervisor_area": qr_location.get("supervisorArea", "Unknown"),
            "location_updated": location_updated,
            "coordinates": {
                "scanned_lat": device_lat,
                "scanned_lng": device_lng
            },
            "location_address": {
                "address": address_info.get("address", f"Location at {device_lat:.4f}, {device_lng:.4f}"),
                "formatted_address": address_info.get("formatted_address", ""),
                "detailed_address": address_info.get("detailed_address", ""),
                "address_lookup_success": address_info.get("success", False),
                "components": address_info.get("components", {})
            },
            "note": f"QR location coordinates {'updated from your GPS' if location_updated else 'recorded successfully'}. Guard location: {address_info.get('address', 'GPS coordinates saved')}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing QR scan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process QR scan"
        )
