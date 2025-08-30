from database import get_users_collection, init_database
from services.jwt_service import jwt_service
import asyncio

async def test_admin_auth():
    # Initialize database first
    await init_database()
    
    users_collection = get_users_collection()
    admin = await users_collection.find_one({'email': 'admin@lh.io.in'})
    if admin:
        print(f'Admin found: {admin["email"]} - Role: {admin["role"]}')
        print(f'Admin user fields: {list(admin.keys())}')
        
        # Test password verification
        password_field = admin.get('password_hash', admin.get('passwordHash'))
        is_valid = jwt_service.verify_password('Test@123', password_field)
        print(f'Password verification result: {is_valid}')
        
        if is_valid:
            print('✅ Admin authentication should work now!')
        else:
            print('❌ Password verification still failing')
            print(f'Stored hash starts with: {password_field[:30]}...')
    else:
        print('Admin user not found')

if __name__ == "__main__":
    asyncio.run(test_admin_auth())
