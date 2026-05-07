#!/usr/bin/env python3
"""
Standalone bot runner - Only ONE instance should run
"""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 DeuceVerify Bot (Standalone)")
    print("=" * 50)
    print(f"Bot Token: {'✅' if os.getenv('BOT_TOKEN') else '❌'}")
    print(f"Database: {'✅' if os.getenv('DATABASE_URL') else '❌'}")
    print("=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Bot stopped")
    except Exception as e:
        print(f"❌ Bot failed: {e}")
        sys.exit(1)
