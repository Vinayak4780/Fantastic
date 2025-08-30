import requests
import json

def test_supervisor_auth_flow():
    """Test the complete supervisor authentication flow step by step"""
    
    print("🔍 Testing Supervisor Authentication Flow...")
    
    # Step 1: Login
    print("\n1️⃣ Step 1: Login")
    login_response = requests.post(
        "http://localhost:8000/auth/login",
        data={"username": "dhasmanakartik84@gmail.com", "password": "test@123"}
    )
    
    print(f"Login Status: {login_response.status_code}")
    if login_response.status_code == 200:
        login_data = login_response.json()
        print(f"✅ Login successful!")
        print(f"Token type: {login_data.get('token_type')}")
        print(f"User role: {login_data.get('user', {}).get('role')}")
        
        token = login_data.get('access_token')
        print(f"Token (first 50 chars): {token[:50]}...")
        
        # Step 2: Test token with dashboard
        print("\n2️⃣ Step 2: Test Dashboard with Token")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        dashboard_response = requests.get(
            "http://localhost:8000/supervisor/dashboard",
            headers=headers
        )
        
        print(f"Dashboard Status: {dashboard_response.status_code}")
        if dashboard_response.status_code == 200:
            print(f"✅ Dashboard access successful!")
            print(f"Response: {dashboard_response.json()}")
        else:
            print(f"❌ Dashboard access failed!")
            print(f"Error: {dashboard_response.text}")
            
        # Step 3: Test with different endpoints
        print("\n3️⃣ Step 3: Test Other Auth Endpoints")
        test_endpoints = [
            "/supervisor/guards",
            "/supervisor/locations", 
            "/admin/dashboard"  # This should fail with 403
        ]
        
        for endpoint in test_endpoints:
            response = requests.get(f"http://localhost:8000{endpoint}", headers=headers)
            print(f"  {endpoint}: {response.status_code}")
            if response.status_code not in [200, 403, 404]:
                print(f"    Error: {response.text[:100]}")
                
    else:
        print(f"❌ Login failed!")
        print(f"Error: {login_response.text}")

if __name__ == "__main__":
    test_supervisor_auth_flow()
