#!/usr/bin/env python3
"""
Run both Flask API and Telegram Bot together
This ensures both services start correctly in Railway
"""

import subprocess
import sys
import os
import time
import signal

def run_services():
    """Run both services simultaneously"""
    
    print("=" * 50)
    print("DeuceVerify - Starting Services")
    print("=" * 50)
    
    # Start Flask API
    print("🚀 Starting Flask API...")
    api_process = subprocess.Popen(
        [sys.executable, "api/app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    # Wait for API to initialize
    time.sleep(2)
    
    # Start Telegram Bot
    print("🤖 Starting Telegram Bot...")
    bot_process = subprocess.Popen(
        [sys.executable, "-m", "bot.main"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    print("✅ Both services started!")
    print("=" * 50)
    
    # Function to handle shutdown
    def shutdown(sig, frame):
        print("\n🛑 Shutting down...")
        api_process.terminate()
        bot_process.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Monitor both processes
    while True:
        api_rc = api_process.poll()
        bot_rc = bot_process.poll()
        
        if api_rc is not None:
            print(f"❌ Flask API exited with code {api_rc}")
            if api_rc != 0:
                # Get output
                output, _ = api_process.communicate()
                print(f"Output: {output}")
                break
                
        if bot_rc is not None:
            print(f"❌ Bot exited with code {bot_rc}")
            if bot_rc != 0:
                output, _ = bot_process.communicate()
                print(f"Output: {output}")
                break
        
        time.sleep(1)
    
    # If we get here, something died
    api_process.terminate()
    bot_process.terminate()
    sys.exit(1)

if __name__ == "__main__":
    run_services()
