import requests
import json

def test_endpoints_step_by_step():
    """Test endpoints one by one to isolate the issue"""
    
    print("🔍 Step 1: Testing server health...")
    try:
        health_response = requests.get("http://localhost:8000/")
        print(f"Health endpoint: {health_response.status_code}")
        if health_response.status_code == 200:
            print(f"Response: {health_response.json()}")
    except Exception as e:
        print(f"Health endpoint error: {e}")
    
    print("\n🔍 Step 2: Getting auth token...")
    login_response = requests.post(
        "http://localhost:8000/auth/login",
        data={"username": "admin@lh.io.in", "password": "Test@123"}
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return
    
    token = login_response.json()["access_token"]
    print(f"✅ Got token: {token}")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    print("\n🔍 Step 3: Testing available endpoints...")
    
    # Test different endpoints to see which ones work
    endpoints_to_test = [
        "/docs",
        "/admin/dashboard", 
        "/admin/users",
        "/admin/supervisors",
        "/admin/guards"
    ]
    
    for endpoint in endpoints_to_test:
        try:
            print(f"\n🌐 Testing: {endpoint}")
            response = requests.get(f"http://localhost:8000{endpoint}", headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print(f"   ✅ Success")
            elif response.status_code == 404:
                print(f"   ❌ Not Found")
            elif response.status_code == 500:
                print(f"   💥 Internal Server Error")
            else:
                print(f"   ⚠️  Other: {response.text[:100]}")
        except Exception as e:
            print(f"   💥 Exception: {e}")

if __name__ == "__main__":
    test_endpoints_step_by_step()
