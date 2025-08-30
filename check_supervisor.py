from database import get_users_collection, init_database
from services.jwt_service import jwt_service
import asyncio

async def check_supervisor_status():
    # Initialize database first
    await init_database()
    
    users_collection = get_users_collection()
    supervisor = await users_collection.find_one({'email': 'dhasmanakartik84@gmail.com'})
    
    if supervisor:
        print(f'✅ Supervisor found: {supervisor["email"]}')
        print(f'📋 Name: {supervisor.get("name", "N/A")}')
        print(f'🎭 Role: {supervisor.get("role", "N/A")}')
        print(f'🏙️ Area/City: {supervisor.get("areaCity", "N/A")}')
        print(f'✅ Is Active: {supervisor.get("isActive", False)}')
        print(f'📧 Email Verified: {supervisor.get("isEmailVerified", False)}')
        
        # Test password verification
        password_field = supervisor.get('passwordHash')
        if password_field:
            # Test both possible passwords
            test_passwords = ['Test@123', 'test@123']
            for pwd in test_passwords:
                is_valid = jwt_service.verify_password(pwd, password_field)
                print(f'🔑 Password "{pwd}": {is_valid}')
        else:
            print('❌ No password hash found')
            
        print(f'📊 All supervisor fields: {list(supervisor.keys())}')
    else:
        print('❌ Supervisor not found in database')
        
        # Check if user exists with any variation
        all_users = await users_collection.find({}).to_list(100)
        print(f'📊 Total users in database: {len(all_users)}')
        
        for user in all_users:
            if 'dhasmanakartik84' in user.get('email', ''):
                print(f'🔍 Found similar user: {user["email"]} - Role: {user.get("role")}')

if __name__ == "__main__":
    asyncio.run(check_supervisor_status())
