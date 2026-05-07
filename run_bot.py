#!/usr/bin/env python3
"""
Standalone bot runner - Run this separately from Flask
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 DeuceVerify Bot Starting...")
    print("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot failed: {e}")
        sys.exit(1)
