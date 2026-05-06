# Sync SMS-Man services
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.utils.smsman_client import SMSManClient
from dotenv import load_dotenv

load_dotenv()

async def sync():
    client = SMSManClient(token=os.getenv('SMS_MAN_TOKEN'))
    countries = await client.get_countries()
    services = await client.get_services()
    print(f"✅ Synced {len(countries)} countries and {len(services)} services")
    await client.close()

if __name__ == "__main__":
    asyncio.run(sync())
