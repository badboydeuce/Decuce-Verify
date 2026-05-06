#!/usr/bin/env python3
"""
DeuceVerify - Unified Service Launcher
Runs both Flask API and Telegram Bot together
"""

import subprocess
import sys
import time
import signal
import os

# Add the project root to Python path so modules can be found
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def run_services():
    """Run both Flask API and Telegram Bot simultaneously"""
    
    print("=" * 60)
    print("🚀 DeuceVerify - Starting Services")
    print("=" * 60)
    print(f"📁 Project Root: {PROJECT_ROOT}")
    print(f"🐍 Python Path: {sys.path[0]}")
    print("=" * 60)
    
    # Set environment variable for Python path
    env = os.environ.copy()
    env['PYTHONPATH'] = PROJECT_ROOT
    env['FLASK_APP'] = 'api/app.py'
    
    # Start Flask API
    print("\n🌐 Starting Flask API on port 5000...")
    api_process = subprocess.Popen(
        [sys.executable, "api/app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        env=env,
        cwd=PROJECT_ROOT
    )
    
    # Wait for Flask to initialize
    time.sleep(3)
    
    # Check if API started successfully
    if api_process.poll() is not None:
        print("❌ Flask API failed to start!")
        output, _ = api_process.communicate()
        print(f"Error output: {output}")
        return 1
    
    print("✅ Flask API started")
    
    # Start Telegram Bot
    print("\n🤖 Starting Telegram Bot...")
    bot_process = subprocess.Popen(
        [sys.executable, "-m", "bot.main"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        env=env,
        cwd=PROJECT_ROOT
    )
    
    # Check if Bot started successfully
    time.sleep(2)
    if bot_process.poll() is not None:
        print("❌ Telegram Bot failed to start!")
        output, _ = bot_process.communicate()
        print(f"Error output: {output}")
        return 1
    
    print("✅ Telegram Bot started")
    print("\n" + "=" * 60)
    print("🎉 Both services are running!")
    print("=" * 60)
    
    # Handle shutdown signals
    def shutdown(sig, frame):
        print("\n🛑 Shutting down services...")
        if api_process.poll() is None:
            api_process.terminate()
            print("  - Flask API stopped")
        if bot_process.poll() is None:
            bot_process.terminate()
            print("  - Telegram Bot stopped")
        print("✅ Shutdown complete")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Monitor both processes and print output in real-time
    def print_output(process, name):
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"[{name}] {line.rstrip()}")
    
    import threading
    api_thread = threading.Thread(target=print_output, args=(api_process, "API"))
    bot_thread = threading.Thread(target=print_output, args=(bot_process, "BOT"))
    api_thread.daemon = True
    bot_thread.daemon = True
    api_thread.start()
    bot_thread.start()
    
    # Wait for either process to exit
    while True:
        if api_process.poll() is not None:
            print(f"\n❌ Flask API exited with code {api_process.returncode}")
            bot_process.terminate()
            return 1
        
        if bot_process.poll() is not None:
            print(f"\n❌ Telegram Bot exited with code {bot_process.returncode}")
            api_process.terminate()
            return 1
        
        time.sleep(1)

if __name__ == "__main__":
    try:
        exit_code = run_services()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
