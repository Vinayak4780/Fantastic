import requests

def test_with_curl_format():
    """Test the exact same request as your curl command but with authentication"""
    
    # First get the token
    login_response = requests.post(
        "http://localhost:8000/auth/login",
        data={"username": "admin@lh.io.in", "password": "Test@123"}
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return
    
    token = login_response.json()["access_token"]
    print(f"✅ Got token: {token}")
    
    # Now test dashboard with token (like your curl but with auth)
    dashboard_response = requests.get(
        "http://localhost:8000/admin/dashboard",
        headers={
            "accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    
    print(f"\n📊 Dashboard Response:")
    print(f"Status Code: {dashboard_response.status_code}")
    print(f"Response: {dashboard_response.text}")
    
    # Let's also test a simpler endpoint to isolate the issue
    print(f"\n🔍 Testing simpler endpoint...")
    users_response = requests.get(
        "http://localhost:8000/admin/users",
        headers={
            "accept": "application/json", 
            "Authorization": f"Bearer {token}"
        }
    )
    print(f"Users endpoint - Status: {users_response.status_code}")
    if users_response.status_code != 200:
        print(f"Users error: {users_response.text}")

if __name__ == "__main__":
    test_with_curl_format()
