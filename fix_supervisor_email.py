from database import get_users_collection, init_database
import asyncio

async def fix_supervisor_email_verification():
    await init_database()
    users_collection = get_users_collection()
    
    # Update supervisor to have email verified
    result = await users_collection.update_one(
        {'email': 'dhasmanakartik84@gmail.com'},
        {'$set': {'isEmailVerified': True}}
    )
    
    if result.modified_count > 0:
        print('✅ Supervisor email verification fixed!')
        
        # Verify the update
        supervisor = await users_collection.find_one({'email': 'dhasmanakartik84@gmail.com'})
        print(f'📧 Email Verified: {supervisor.get("isEmailVerified", False)}')
    else:
        print('❌ Failed to update supervisor')

if __name__ == "__main__":
    asyncio.run(fix_supervisor_email_verification())
