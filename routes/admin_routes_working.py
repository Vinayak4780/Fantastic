"""
Admin routes for user management and system administration
ADMIN role only - manage supervisors, guards, and system configuration
Updated with specific email patterns: admin@lh.io.in, {area}supervisor@lh.io.in
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import os
import io
from bson import ObjectId

# Import services and dependencies
from services.auth_service import get_current_admin
from services.google_drive_excel_service import google_drive_excel_service
from database import (
    get_users_collection, get_supervisors_collection, get_guards_collection,
    get_scan_events_collection, get_qr_locations_collection, get_database_health
)
from config import settings

# Import models
from models import (
    UserCreate, UserResponse, UserRole, SupervisorCreate, SupervisorResponse,
    GuardCreate, GuardResponse, ScanEventResponse, AreaReportRequest,
    ScanReportResponse, SuccessResponse, SystemConfig, SystemConfigUpdate,
    generate_supervisor_email, generate_guard_email
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
        
        if not all([
            users_collection is not None, 
            supervisors_collection is not None, 
            guards_collection is not None, 
            scan_events_collection is not None
        ]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Get basic counts
        total_users = await users_collection.count_documents({})
        total_supervisors = await supervisors_collection.count_documents({})
        total_guards = await guards_collection.count_documents({})
        total_scans_today = await scan_events_collection.count_documents({
            "scannedAt": {"$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)}
        })
        
        # Get recent activity - convert ObjectIds to strings
        recent_scans_cursor = scan_events_collection.find({}) \
            .sort("scannedAt", -1) \
            .limit(10)
        
        recent_scans = []
        async for scan in recent_scans_cursor:
            scan_data = {
                "_id": str(scan["_id"]),
                "guardId": str(scan.get("guardId", "")),
                "guardEmail": scan.get("guardEmail", ""),
                "qrId": str(scan.get("qrId", "")),
                "scannedAt": scan.get("scannedAt"),
                "deviceLat": scan.get("deviceLat"),
                "deviceLng": scan.get("deviceLng"),
                "address": scan.get("address", ""),
                "timestampIST": scan.get("timestampIST", "")
            }
            recent_scans.append(scan_data)
        
        # Convert admin ObjectIds to strings
        admin_info = {
            "_id": str(current_admin["_id"]),
            "email": current_admin["email"],
            "name": current_admin.get("name", "Admin"),
            "role": current_admin.get("role", "ADMIN")
        }
        
        return {
            "stats": {
                "totalUsers": total_users,
                "totalSupervisors": total_supervisors,
                "totalGuards": total_guards,
                "scansToday": total_scans_today
            },
            "recentActivity": recent_scans,
            "adminInfo": admin_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard"
        )


@admin_router.get("/excel/area-wise-reports")
async def get_area_wise_excel_reports(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    days_back: int = Query(7, ge=1, le=30, description="Number of days to include in report"),
    area: Optional[str] = Query(None, description="Specific area/state to filter (optional)")
):
    """
    Generate area-wise Excel reports for all areas or a specific area
    """
    try:
        scan_events_collection = get_scan_events_collection()
        users_collection = get_users_collection()
        
        if scan_events_collection is None or users_collection is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        # Build base filter for date range
        base_filter = {
            "scannedAt": {"$gte": start_date, "$lte": end_date}
        }
        
        # Add area filter if specified
        if area:
            area_filter = {
                "$and": [
                    base_filter,
                    {
                        "$or": [
                            {"address": {"$regex": area, "$options": "i"}},
                            {"formatted_address": {"$regex": area, "$options": "i"}}
                        ]
                    }
                ]
            }
        else:
            area_filter = base_filter
        
        # Get scans with user information
        pipeline = [
            {"$match": area_filter},
            {"$sort": {"scannedAt": -1}},
            {"$limit": 2000},  # Limit for performance
            
            # Lookup user by email
            {"$lookup": {
                "from": "users",
                "localField": "guardEmail",
                "foreignField": "email",
                "as": "user_data"
            }},
            
            # Group by area (extracted from address)
            {"$addFields": {
                "area_name": {
                    "$cond": {
                        "if": {"$regexMatch": {"input": "$address", "regex": "haryana", "options": "i"}},
                        "then": "Haryana",
                        "else": {
                            "$cond": {
                                "if": {"$regexMatch": {"input": "$address", "regex": "uttar pradesh", "options": "i"}},
                                "then": "Uttar Pradesh",
                                "else": {
                                    "$cond": {
                                        "if": {"$regexMatch": {"input": "$address", "regex": "maharashtra", "options": "i"}},
                                        "then": "Maharashtra",
                                        "else": {
                                            "$cond": {
                                                "if": {"$regexMatch": {"input": "$address", "regex": "delhi", "options": "i"}},
                                                "then": "Delhi",
                                                "else": "Other"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }}
        ]
        
        scans_with_areas = await scan_events_collection.aggregate(pipeline).to_list(length=None)
        
        if not scans_with_areas:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scan data found for the last {days_back} days"
            )
        
        # Group data by area
        area_data = {}
        for scan in scans_with_areas:
            area_name = scan.get("area_name", "Other")
            
            if area_name not in area_data:
                area_data[area_name] = []
            
            # Get guard name
            guard_name = "Unknown Guard"
            if scan.get("user_data") and len(scan["user_data"]) > 0:
                guard_name = scan["user_data"][0].get("name", "Unknown Guard")
            elif scan.get("guardEmail"):
                guard_name = scan["guardEmail"].split("@")[0]
            
            # Prepare row data
            row_data = {
                "Area": area_name,
                "Guard Name": guard_name,
                "Guard Email": scan.get("guardEmail", ""),
                "Scan Date": scan.get("scannedAt", "").strftime("%Y-%m-%d") if scan.get("scannedAt") else "",
                "Scan Time": scan.get("scannedAt", "").strftime("%H:%M:%S") if scan.get("scannedAt") else "",
                "Timestamp IST": scan.get("timestampIST", ""),
                "Detailed Address": scan.get("address", ""),
                "Formatted Address": scan.get("formatted_address", ""),
                "GPS Latitude": scan.get("deviceLat", ""),
                "GPS Longitude": scan.get("deviceLng", ""),
                "QR Code ID": scan.get("qrId", ""),
                "Address Lookup Success": scan.get("address_lookup_success", False)
            }
            area_data[area_name].append(row_data)
        
        # Create Excel files for each area
        import pandas as pd
        excel_files = {}
        excel_folder = "excel_reports"
        os.makedirs(excel_folder, exist_ok=True)
        
        for area_name, data in area_data.items():
            if not data:
                continue
                
            # Generate filename
            filename = f"area_report_{area_name.replace(' ', '_')}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx"
            file_path = os.path.join(excel_folder, filename).replace("/", "\\")
            
            # Create DataFrame and Excel file
            df = pd.DataFrame(data)
            
            # Create Excel file
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=f'{area_name}_Scans', index=False)
                
                # Auto-adjust column widths
                worksheet = writer.sheets[f'{area_name}_Scans']
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # Save to file
            output.seek(0)
            with open(file_path, 'wb') as f:
                f.write(output.getvalue())
            
            excel_files[area_name] = {
                "filename": filename,
                "path": f"\\{excel_folder}\\{filename}",
                "total_scans": len(data),
                "unique_guards": len(set(row["Guard Email"] for row in data))
            }
        
        logger.info(f"Admin {current_admin['email']} generated area-wise Excel reports")
        
        return {
            "message": "Area-wise Excel reports generated successfully",
            "report_details": {
                "admin_email": current_admin["email"],
                "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "total_areas": len(excel_files),
                "area_filter": area if area else "All areas"
            },
            "excel_files": excel_files,
            "summary": {
                "total_scans": sum(len(data) for data in area_data.values()),
                "areas_covered": list(area_data.keys())
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate area-wise Excel reports error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate area-wise Excel reports: {str(e)}"
        )
