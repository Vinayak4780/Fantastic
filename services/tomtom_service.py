import httpx
import logging
from typing import Dict, Any, Optional
from config import Settings

# Configure logger
logger = logging.getLogger(__name__)

class TomTomService:
    """
    Service for TomTom API integration - Address lookup and location services
    """
    
    def __init__(self, api_key: str = "YOUR_TOMTOM_API_KEY"):
        """
        Initialize TomTom service
        
        Args:
            api_key: TomTom API key for authentication
        """
        self.api_key = api_key
        self.base_url = "https://api.tomtom.com/search/2/reverseGeocode"
        
    async def get_address_from_coordinates(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        Convert GPS coordinates to full address using TomTom API with building detection
        
        Args:
            latitude: GPS latitude
            longitude: GPS longitude
            
        Returns:
            Dictionary with comprehensive address information including building names
        """
        try:
            if self.api_key == 'YOUR_TOMTOM_API_KEY':
                # Return mock address for testing
                return {
                    "success": True,
                    "address": f"Mock Building, Test Street, Location at {latitude:.4f}, {longitude:.4f}",
                    "formatted_address": f"GPS Coordinates: {latitude:.4f}, {longitude:.4f}",
                    "building_name": "Mock Corporate Building",
                    "street": "Test Street",
                    "city": "Test City",
                    "state": "Test State",
                    "country": "Test Country",
                    "latitude": latitude,
                    "longitude": longitude,
                    "note": "TomTom API key not configured - using mock data"
                }
            
            # Get basic address from reverse geocoding
            address_info = await self._get_reverse_geocoded_address(latitude, longitude)
            
            # Search for nearby buildings/POIs
            building_info = await self._search_nearby_buildings(latitude, longitude)
            
            # Combine results for comprehensive address
            return await self._combine_address_results(address_info, building_info, latitude, longitude)
            
        except httpx.TimeoutException:
            logger.error(f"TomTom API timeout for coordinates {latitude}, {longitude}")
            return {
                "success": False,
                "address": f"Location at {latitude:.4f}, {longitude:.4f}",
                "formatted_address": f"GPS Coordinates: {latitude:.4f}, {longitude:.4f}",
                "error": "Request timeout"
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"TomTom API HTTP error {e.response.status_code}: {e.response.text}")
            return {
                "success": False,
                "address": f"Location at {latitude:.4f}, {longitude:.4f}",
                "formatted_address": f"GPS Coordinates: {latitude:.4f}, {longitude:.4f}",
                "error": f"API error: {e.response.status_code}"
            }
        except Exception as e:
            logger.error(f"Error getting address from TomTom: {e}")
            return {
                "success": False,
                "address": f"Location at {latitude:.4f}, {longitude:.4f}",
                "formatted_address": f"GPS Coordinates: {latitude:.4f}, {longitude:.4f}",
                "error": "Address lookup failed"
            }
    
    async def _get_reverse_geocoded_address(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Get basic address from reverse geocoding"""
        try:
            # TomTom Reverse Geocoding API URL
            url = f"{self.base_url}/{latitude},{longitude}.json"
            
            params = {
                'key': self.api_key,
                'returnSpeedLimit': 'false',
                'returnRoadUse': 'false',
                'allowFreeformNewLine': 'false',
                'radius': 100,
                'limit': 5
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('addresses') and len(data['addresses']) > 0:
                    return data['addresses'][0]['address']
                else:
                    return {}
                    
        except Exception as e:
            logger.error(f"Reverse geocoding error: {e}")
            return {}
    
    async def _search_nearby_buildings(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Search for nearby buildings/POIs to get specific building names"""
        try:
            # TomTom Search API for nearby POIs
            search_url = "https://api.tomtom.com/search/2/nearbySearch/.json"
            
            params = {
                'key': self.api_key,
                'lat': latitude,
                'lon': longitude,
                'radius': 50,
                'limit': 10,
                'categorySet': '9663,7315,7318,7361',
                'view': 'Unified'
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(search_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('results') and len(data['results']) > 0:
                    closest_building = data['results'][0]
                    return {
                        'building_name': closest_building.get('poi', {}).get('name', ''),
                        'building_category': closest_building.get('poi', {}).get('categories', []),
                        'building_brands': closest_building.get('poi', {}).get('brands', []),
                        'distance': closest_building.get('dist', 0)
                    }
                else:
                    return {}
                    
        except Exception as e:
            logger.error(f"Building search error: {e}")
            return {}
    
    async def _combine_address_results(self, address_info: Dict, building_info: Dict, latitude: float, longitude: float) -> Dict[str, Any]:
        """Combine reverse geocoding and building search results"""
        try:
            result = {
                "success": True,
                "latitude": latitude,
                "longitude": longitude
            }
            
            if address_info:
                formatted_address = address_info.get('freeformAddress', '')
                street = address_info.get('streetName', '')
                building_number = address_info.get('buildingNumber', '')
                district = address_info.get('municipality', '')
                city = address_info.get('municipalitySubdivision', '') or address_info.get('localName', '')
                state = address_info.get('countrySubdivision', '')
                postal_code = address_info.get('postalCode', '')
                country = address_info.get('country', '')
                
                address_parts = []
                
                if building_info and building_info.get('building_name'):
                    building_name = building_info['building_name']
                    address_parts.append(building_name)
                    result["building_name"] = building_name
                    result["building_distance"] = building_info.get('distance', 0)
                
                if street:
                    if building_number:
                        address_parts.append(f"{building_number} {street}")
                    else:
                        address_parts.append(street)
                
                if district and district != city:
                    address_parts.append(district)
                
                if city:
                    address_parts.append(city)
                
                if postal_code:
                    address_parts.append(postal_code)
                
                if state:
                    address_parts.append(state)
                
                if country:
                    address_parts.append(country)
                
                comprehensive_address = ", ".join(filter(None, address_parts))
                
                result.update({
                    "address": comprehensive_address or formatted_address,
                    "formatted_address": formatted_address,
                    "street": street,
                    "building_number": building_number,
                    "district": district,
                    "city": city,
                    "state": state,
                    "postal_code": postal_code,
                    "country": country
                })
            else:
                result.update({
                    "address": f"Location at {latitude:.4f}, {longitude:.4f}",
                    "formatted_address": f"GPS Coordinates: {latitude:.4f}, {longitude:.4f}",
                    "street": "",
                    "city": "",
                    "state": "",
                    "postal_code": "",
                    "country": ""
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error combining address results: {e}")
            return {
                "success": False,
                "address": f"Location at {latitude:.4f}, {longitude:.4f}",
                "formatted_address": f"GPS Coordinates: {latitude:.4f}, {longitude:.4f}",
                "error": "Address processing failed"
            }


# Create service instance for easy import with proper API key
settings = Settings()
tomtom_service = TomTomService(api_key=settings.TOMTOM_API_KEY)
