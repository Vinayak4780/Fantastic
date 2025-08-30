from database import get_users_collection, init_database
from services.jwt_service import jwt_service
import asyncio

async def fix_admin_password():
    # Initialize database first
    await init_database()
    
    users_collection = get_users_collection()
    admin = await users_collection.find_one({'email': 'admin@lh.io.in'})
    
    if admin:
        print(f'Admin found: {admin["email"]} - Role: {admin["role"]}')
        
        # Test current password
        current_hash = admin.get('passwordHash')
        print(f'Current hash: {current_hash}')
        
        # Test various possible passwords
        test_passwords = ['Test@123', 'test@123', 'TEST@123', 'admin@123', 'Admin@123']
        
        for pwd in test_passwords:
            is_valid = jwt_service.verify_password(pwd, current_hash)
            print(f'Password "{pwd}": {is_valid}')
        
        # Create new hash for Test@123 and update
        new_hash = jwt_service.hash_password('Test@123')
        print(f'New hash for Test@123: {new_hash}')
        
        # Update the admin password
        result = await users_collection.update_one(
            {'email': 'admin@lh.io.in'},
            {'$set': {'passwordHash': new_hash}}
        )
        
        if result.modified_count > 0:
            print('✅ Admin password updated successfully!')
            
            # Verify the new password works
            admin_updated = await users_collection.find_one({'email': 'admin@lh.io.in'})
            is_valid = jwt_service.verify_password('Test@123', admin_updated['passwordHash'])
            print(f'New password verification: {is_valid}')
        else:
            print('❌ Failed to update admin password')
    else:
        print('Admin user not found')

if __name__ == "__main__":
    asyncio.run(fix_admin_password())
