import asyncio
import httpx

async def test_excel_areas():
    """Test the Excel areas endpoint"""
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                'accept': 'application/json',
                'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjg5ZTIxMDRlM2U1MmQxZjE3N2ViNzliIiwiZW1haWwiOiJhZG1pbkBsaC5pby5pbiIsInJvbGUiOiJBRE1JTiIsImV4cCI6MTc1NTQ0MTA5OCwidHlwZSI6ImFjY2VzcyJ9.SUJVHiT_o8BrJZnDS0ZVbRQArZa56Onx06gzbqp_dI0'
            }
            
            response = await client.get('http://localhost:8000/admin/excel/areas', headers=headers)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_excel_areas())
