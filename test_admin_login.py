import requests
import json

# Step 1: Admin Login to get JWT token
def test_admin_login():
    # Login endpoint
    login_url = "http://localhost:8000/auth/login"
    
    # Admin credentials from .env (using form data, not JSON)
    login_data = {
        "username": "admin@lh.io.in",  # Note: username field, not email
        "password": "Test@123"
    }
    
    print("🔐 Testing Admin Login...")
    print(f"URL: {login_url}")
    print(f"Data: {login_data}")
    
    try:
        # Send login request as form data (not JSON)
        response = requests.post(login_url, data=login_data)
        
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Login Successful!")
            print(f"📊 Response: {json.dumps(result, indent=2)}")
            
            # Extract access token
            access_token = result.get('access_token')
            if access_token:
                print(f"\n🎫 Access Token: {access_token[:50]}...")
                return access_token
            else:
                print("❌ No access token in response")
                return None
        else:
            print(f"❌ Login Failed!")
            print(f"📊 Error: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is the server running on http://localhost:8000?")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

# Step 2: Test Admin Dashboard with token
def test_admin_dashboard(token):
    if not token:
        print("❌ No token available for dashboard test")
        return
        
    dashboard_url = "http://localhost:8000/admin/dashboard"
    
    # Headers with JWT token
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    print(f"\n🏠 Testing Admin Dashboard...")
    print(f"URL: {dashboard_url}")
    print(f"Headers: {headers}")
    
    try:
        response = requests.get(dashboard_url, headers=headers)
        
        print(f"\n📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Dashboard Access Successful!")
            print(f"📊 Dashboard Data: {json.dumps(result, indent=2)}")
        else:
            print(f"❌ Dashboard Access Failed!")
            print(f"📊 Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Test complete flow
    token = test_admin_login()
    test_admin_dashboard(token)
