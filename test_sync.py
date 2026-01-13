#!/usr/bin/env python3
"""
Test script for Minecraft mod synchronization system
This script tests the client-server synchronization functionality
"""

import os
import sys
import time
import shutil
from pathlib import Path
import requests
import tempfile

# Add workspace to Python path
sys.path.insert(0, '/workspace')

def setup_client_mods():
    """Set up client mods directory with some initial mods"""
    client_mods = Path("/workspace/client_mods")
    client_mods.mkdir(exist_ok=True)
    
    # Copy a few mods to the client to simulate partial sync
    server_mods = Path("/workspace/server")
    server_jars = list(server_mods.glob("*.jar"))[:5]  # Take first 5 mods
    
    print(f"Setting up client with {len(server_jars)} initial mods...")
    for jar in server_jars:
        dest = client_mods / jar.name
        shutil.copy2(jar, dest)
        print(f"  Copied {jar.name}")
    
    # Add one fake mod that's not on server to test deletion
    fake_mod = client_mods / "fake-mod-1.0.jar"
    fake_mod.write_text("fake content")
    print(f"  Added fake mod: {fake_mod.name}")
    
    return client_mods

def test_server_connection():
    """Test connection to the server"""
    try:
        response = requests.get("http://localhost:8800/health", timeout=10)
        if response.status_code == 200:
            print("✅ Server connection successful")
            health_data = response.json()
            print(f"   Server version: {health_data.get('server_version', 'unknown')}")
            print(f"   Mods directory: {health_data.get('mods_directory', 'unknown')}")
            print(f"   Files count: {health_data.get('file_count', 0)}")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error connecting to server: {e}")
        return False

def test_manifest():
    """Test getting manifest from server"""
    try:
        response = requests.get("http://localhost:8800/manifest", timeout=10)
        if response.status_code == 200:
            manifest = response.json()
            print(f"✅ Got manifest with {len(manifest)} files")
            if manifest:
                sample_file = next(iter(manifest))
                print(f"   Sample entry: {sample_file}")
                print(f"   Size: {manifest[sample_file]['size']} bytes")
                print(f"   Hash: {manifest[sample_file]['hash'][:16]}..." if manifest[sample_file]['hash'] else "   No hash (large file)")
            return manifest
        else:
            print(f"❌ Manifest request failed with status {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error getting manifest: {e}")
        return None

def test_file_download():
    """Test downloading a file from server"""
    try:
        # Get manifest to pick a file
        response = requests.get("http://localhost:8800/manifest", timeout=10)
        if response.status_code == 200:
            manifest = response.json()
            if manifest:
                sample_file = next(iter(manifest))
                print(f"Testing download of: {sample_file}")
                
                download_response = requests.get(f"http://localhost:8800/file/{sample_file}", timeout=30)
                if download_response.status_code == 200:
                    print(f"✅ Download successful, received {len(download_response.content)} bytes")
                    
                    # Test range request
                    headers = {"Range": "bytes=0-1023"}  # First 1KB
                    range_response = requests.get(f"http://localhost:8800/file/{sample_file}", headers=headers, timeout=30)
                    if range_response.status_code == 206:  # Partial content
                        print(f"✅ Range request successful, got {len(range_response.content)} bytes")
                        return True
                    else:
                        print(f"❌ Range request failed with status {range_response.status_code}")
                        return False
                else:
                    print(f"❌ Download failed with status {download_response.status_code}")
                    return False
        return False
    except Exception as e:
        print(f"❌ Error testing file download: {e}")
        return False

def test_client_sync():
    """Test client synchronization"""
    from client.api import ModSyncAPI
    from client.config import ClientConfig
    
    # Update client config to use our test directory
    config = ClientConfig()
    client_mods_path = Path("/workspace/client_mods")
    config.get_profile()["mods_path"] = str(client_mods_path)
    config.save()
    
    # Create API instance
    api = ModSyncAPI()
    
    print("\n--- Testing client sync ---")
    try:
        # Run sync
        print("Starting sync operation...")
        
        def log_func(msg):
            print(f"  {msg}")
        
        api.sync(
            mods_path=client_mods_path,
            log=log_func,
            on_start=lambda total_size: print(f"  Expected download size: {total_size} bytes"),
            on_file_start=lambda filename, size: print(f"  Starting download: {filename} ({size} bytes)"),
            on_file_progress=lambda current, total: None,  # Suppress frequent updates
            on_total_progress=lambda current, total: None  # Suppress frequent updates
        )
        
        print("✅ Sync completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🧪 Testing Minecraft Mod Synchronization System")
    print("=" * 50)
    
    # Setup client mods
    client_mods = setup_client_mods()
    
    print(f"\n📁 Client mods directory: {client_mods}")
    print(f"📁 Server mods directory: /workspace/server")
    
    # Wait for server to be ready (if running)
    print("\n--- Testing server functionality ---")
    time.sleep(2)  # Give server time to start if needed
    
    if not test_server_connection():
        print("\n❌ Server is not running. Please start the server first.")
        print("Run: cd /workspace/server && python main.py")
        return False
    
    # Test manifest
    print("\n--- Testing manifest ---")
    manifest = test_manifest()
    
    # Test file download
    print("\n--- Testing file download ---")
    test_file_download()
    
    # Test client sync
    success = test_client_sync()
    
    # Check results
    print(f"\n--- Results ---")
    final_files = list(client_mods.glob("*.jar"))
    print(f"Final client mods: {len(final_files)} files")
    
    server_files = set(f.name for f in Path("/workspace/server").glob("*.jar"))
    client_files = set(f.name for f in client_mods.glob("*.jar"))
    
    print(f"Server has: {len(server_files)} files")
    print(f"Client has: {len(client_files)} files")
    
    missing = server_files - client_files
    extra = client_files - server_files
    
    if missing:
        print(f"❌ Missing from client: {len(missing)} files")
        for f in sorted(missing):
            print(f"   - {f}")
    else:
        print("✅ No files missing from client")
    
    if extra:
        print(f"❌ Extra files on client: {len(extra)} files")
        for f in sorted(extra):
            print(f"   - {f}")
    else:
        print("✅ No extra files on client")
    
    if not missing and not extra and success:
        print("\n🎉 All tests passed! Synchronization working correctly.")
        return True
    else:
        print("\n⚠️  Some issues detected during synchronization.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)