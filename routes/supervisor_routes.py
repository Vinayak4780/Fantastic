"""
Supervisor routes for QR location management and guard oversight
SUPERVISOR role only - manage QR locations, view assigned guards, and access scan data
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import io
import os
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
        
        supervisor_user_id = str(current_supervisor["_id"])  # This is the user ID from the users collection
        supervisor_state = current_supervisor["areaCity"]  # This is the state like "Maharashtra"
        
        # Get assigned guards count (guards assigned to this supervisor)
        assigned_guards = await guards_collection.count_documents({
            "supervisorId": ObjectId(supervisor_user_id)
        })
        
        # Get QR locations count  
        qr_locations = await qr_locations_collection.count_documents({
            "supervisorId": ObjectId(supervisor_user_id)
        })
        
        # Filter scans by supervisor's state - look for scans with addresses containing the state
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Build scan filter for supervisor's specific state (e.g., "Maharashtra")
        state_filter = {
            "$or": [
                {"address": {"$regex": supervisor_state, "$options": "i"}},
                {"formatted_address": {"$regex": supervisor_state, "$options": "i"}}
            ]
        }
        
        # Get today's scan statistics for this state
        today_state_filter = {
            "$and": [
                {"scannedAt": {"$gte": today_start}},
                state_filter
            ]
        }
        today_scans = await scan_events_collection.count_documents(today_state_filter)
        
        # Get this week's scan statistics for this state
        week_start = today_start - timedelta(days=today_start.weekday())
        week_state_filter = {
            "$and": [
                {"scannedAt": {"$gte": week_start}},
                state_filter
            ]
        }
        this_week_scans = await scan_events_collection.count_documents(week_state_filter)
        
        # Get recent scan events - only from supervisor's state
        recent_scans_cursor = scan_events_collection.find(state_filter).sort("scannedAt", -1).limit(10)
        
        recent_scans = await recent_scans_cursor.to_list(length=None)
        
        # Get guards with most activity - only from supervisor's state
        guard_activity_pipeline = [
            {"$match": {
                "$and": [
                    {"scannedAt": {"$gte": week_start}},
                    state_filter
                ]
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
                "state": supervisor_state,
                "assigned_area": current_supervisor["areaCity"],
                "state_full": current_supervisor.get("areaState"),
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


@supervisor_router.post("/generate-excel-report")
async def generate_excel_report(
    current_supervisor: Dict[str, Any] = Depends(get_current_supervisor),
    days_back: int = Query(7, ge=1, le=30, description="Number of days to include in report")
):
    """
    Generate Excel report of scan data for supervisor's area and send to admin
    """
    try:
        scan_events_collection = get_scan_events_collection()
        guards_collection = get_guards_collection()
        users_collection = get_users_collection()
        
        if (scan_events_collection is None or guards_collection is None or 
            users_collection is None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        supervisor_user_id = str(current_supervisor["_id"])
        supervisor_state = current_supervisor["areaCity"]
        supervisor_email = current_supervisor["email"]
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        # Filter scans by supervisor's state and date range
        state_filter = {
            "$and": [
                {"scannedAt": {"$gte": start_date, "$lte": end_date}},
                {
                    "$or": [
                        {"address": {"$regex": supervisor_state, "$options": "i"}},
                        {"formatted_address": {"$regex": supervisor_state, "$options": "i"}}
                    ]
                }
            ]
        }
        
        # Get scans with guard information - improved pipeline
        pipeline = [
            {"$match": state_filter},
            {"$sort": {"scannedAt": -1}},
            {"$limit": 1000},  # Limit to prevent huge reports
            
            # Add guardObjectId field for lookup
            {"$addFields": {
                "guardObjectId": {
                    "$cond": {
                        "if": {"$ne": ["$guardId", None]},
                        "then": "$guardId",
                        "else": None
                    }
                }
            }},
            
            # Lookup guard record
            {"$lookup": {
                "from": "guards",
                "localField": "guardObjectId",
                "foreignField": "_id",
                "as": "guard_data"
            }},
            
            # Lookup user by email (primary method)
            {"$lookup": {
                "from": "users",
                "localField": "guardEmail",
                "foreignField": "email",
                "as": "user_data_by_email"
            }},
            
            # Lookup user by guardId->userId (secondary method)
            {"$lookup": {
                "from": "users",
                "localField": "guard_data.userId",
                "foreignField": "_id",
                "as": "user_data_by_id"
            }},
            
            # Combine user data sources
            {"$addFields": {
                "user_data": {
                    "$cond": {
                        "if": {"$gt": [{"$size": "$user_data_by_email"}, 0]},
                        "then": "$user_data_by_email",
                        "else": "$user_data_by_id"
                    }
                }
            }},
            
            # Clean up unnecessary fields
            {"$project": {
                "user_data_by_email": 0,
                "user_data_by_id": 0
            }}
        ]
        
        scans_with_details = await scan_events_collection.aggregate(pipeline).to_list(length=None)
        
        if not scans_with_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scan data found for {supervisor_state} in the last {days_back} days"
            )
        
        # Prepare Excel data
        excel_data = []
        for scan in scans_with_details:
            # Get guard name from users collection
            guard_name = "Unknown Guard"
            guard_email = scan.get("guardEmail", "")
            
            # First try to get name from user_data (matched by email)
            if scan.get("user_data") and len(scan["user_data"]) > 0:
                guard_name = scan["user_data"][0].get("name", "Unknown Guard")
            
            # If no user_data, try to get from guard_data (if guardId exists)
            elif scan.get("guard_data") and len(scan["guard_data"]) > 0:
                guard_record = scan["guard_data"][0]
                # Get user details from the guard's userId
                if guard_record.get("userId"):
                    try:
                        user_details = await users_collection.find_one({"_id": guard_record["userId"]})
                        if user_details:
                            guard_name = user_details.get("name", "Unknown Guard")
                            if not guard_email:  # If email not in scan, get from user
                                guard_email = user_details.get("email", "")
                    except Exception as e:
                        logger.warning(f"Could not fetch user details: {e}")
            
            # Final fallback - use email username if nothing else works
            if guard_name == "Unknown Guard" and guard_email:
                guard_name = guard_email.split("@")[0]  # Use email username as fallback
            
            # Format the data row
            row_data = {
                "Guard Name": guard_name,
                "Guard Email": scan.get("guardEmail", ""),
                "Area/State": supervisor_state,
                "Scan Date": scan.get("scannedAt", "").strftime("%Y-%m-%d") if scan.get("scannedAt") else "",
                "Scan Time": scan.get("scannedAt", "").strftime("%H:%M:%S") if scan.get("scannedAt") else "",
                "Timestamp IST": scan.get("timestampIST", ""),
                "Detailed Address": scan.get("address", ""),
                "Formatted Address": scan.get("formatted_address", ""),
                "GPS Latitude": scan.get("deviceLat", ""),
                "GPS Longitude": scan.get("deviceLng", ""),
                "QR Code ID": scan.get("qrId", ""),
                "Location Updated": scan.get("locationUpdated", False),
                "Address Lookup Success": scan.get("address_lookup_success", False)
            }
            excel_data.append(row_data)
        
        # Generate filename
        filename = f"supervisor_report_{supervisor_state}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx"
        
        # Create Excel file in memory
        import io
        import pandas as pd
        
        output = io.BytesIO()
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Write to Excel with formatting
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'{supervisor_state}_Scans', index=False)
            
            # Get the workbook and worksheet
            worksheet = writer.sheets[f'{supervisor_state}_Scans']
            
            # Auto-adjust column widths
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
        
        output.seek(0)
        
        # Save Excel file to the excel_reports folder
        excel_folder = "excel_reports"
        try:
            os.makedirs(excel_folder, exist_ok=True)
        except Exception as e:
            logger.error(f"Could not create excel_reports folder: {e}")
            # Fallback to current directory
            excel_folder = "."
        
        # Save the Excel file locally
        file_path = os.path.join(excel_folder, filename).replace("/", "\\")
        try:
            with open(file_path, 'wb') as f:
                f.write(output.getvalue())
            logger.info(f"Excel file saved successfully: {file_path}")
        except Exception as e:
            logger.error(f"Error saving Excel file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not save Excel file: {str(e)}"
            )
        
        # Create a README file with file info
        try:
            readme_path = os.path.join(excel_folder, f"README_{filename.replace('.xlsx', '.txt')}").replace("/", "\\")
            with open(readme_path, 'w') as f:
                f.write(f"Supervisor Report Generated\n")
                f.write(f"Generated by: {supervisor_email}\n")
                f.write(f"Area: {supervisor_state}\n")
                f.write(f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n")
                f.write(f"Total Scans: {len(excel_data)}\n")
                f.write(f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
                f.write(f"File: {filename}\n")
        except Exception as e:
            logger.warning(f"Could not create README file: {e}")
        
        logger.info(f"Supervisor {supervisor_email} generated Excel report for {supervisor_state}")
        
        return {
            "message": "Excel report generated successfully and saved locally",
            "report_details": {
                "supervisor_email": supervisor_email,
                "area": supervisor_state,
                "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "total_scans": len(excel_data),
                "filename": filename,
                "local_path": f"\\{excel_folder}\\{filename}",
                "folder_path": f"\\{excel_folder}"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate Excel report error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Excel report: {str(e)}"
        )
