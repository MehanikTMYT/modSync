#!/usr/bin/env python3
"""
Minecraft Mod Sync Client - Command Line Interface
CLI client for synchronizing mods with the server
"""

import sys
import os
import argparse
import threading
import time
import json
import hashlib
from pathlib import Path

# Add path to shared modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from modsync.client.config.manager import ConfigManager
from modsync.client.network.connection_utils import ConnectionManager
from modsync.client.download.manager import DownloadManager
from modsync.client.download.simple_strategy import DownloadStrategy


class CLIModSyncApp:
    """CLI Application for ModSync"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.mods_path = self.config_manager.get('paths', 'mods_folder', './minecraft/mods')
        self.running = False
        self.download_manager = None
        
    def log_message(self, message, level="info"):
        """Log message to console"""
        print(f"[{level.upper()}] {message}")
        
    def get_server_hashes(self):
        """Get file hashes from server with auto-reconnect"""
        from modsync.client.network.connection_utils import VDS_SERVER_IP
        try:
            url = f"{VDS_SERVER_IP}/hashes.json"
            self.log_message(f"🔍 Getting file list from server: {url}")
            
            response = ConnectionManager.make_request_with_retry(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            return data['files'], data.get('file_count', 0), data.get('total_size', 0)
        except Exception as e:
            self.log_message(f"❌ Server connection error: {str(e)}", "error")
            raise
            
    def calculate_file_hash(self, filepath):
        """Calculate MD5 hash of file"""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.log_message(f"⚠️ Hash calculation error for {filepath}: {str(e)}", "warning")
            return None
            
    def sync_mods_cli(self, strategy_choice="balanced_adaptive"):
        """CLI version of sync_mods method"""
        try:
            self.log_message("🚀 Starting mod synchronization...", "info")
            
            # Check connection before sync
            if not ConnectionManager.is_server_available(timeout=5):
                raise ConnectionError("Server unavailable. Check connection and try again.")
                
            # Get strategy
            strategies = DownloadStrategy.get_manual_strategies()
            chosen_strategy = strategies.get(strategy_choice, strategies['balanced_adaptive'])
            self.log_message(f"🎯 Using strategy: {chosen_strategy['name']}", "info")
            self.log_message(f"📝 {chosen_strategy['description']}", "info")
            
            # Create download manager
            self.download_manager = DownloadManager(chosen_strategy)
            self.download_manager.set_progress_callback(self.update_file_progress_cli)
            self.download_manager.set_error_callback(self.log_message)
            
            # Get server data
            server_files, total_files_count, total_size_bytes = self.get_server_hashes()
            local_path = self.mods_path
            
            if not local_path:
                raise ValueError("No sync folder selected")
                
            if not os.path.exists(local_path):
                self.log_message(f"📁 Creating folder: {local_path}", "info")
                os.makedirs(local_path, exist_ok=True)
                
            # Collect local files
            local_files = {}
            skipped_temp_files = 0
            
            for root, _, files in os.walk(local_path):
                for file in files:
                    # Skip temporary files
                    if file.endswith('.filepart') or file.startswith('.'):
                        skipped_temp_files += 1
                        continue
                        
                    filepath = os.path.join(root, file)
                    relpath = os.path.relpath(filepath, local_path).replace('\\', '/')
                    
                    try:
                        file_size = os.path.getsize(filepath)
                        file_mtime = os.path.getmtime(filepath)
                        
                        local_files[relpath] = {
                            'path': filepath,
                            'size': file_size,
                            'mtime': file_mtime
                        }
                    except Exception as e:
                        self.log_message(f"⚠️ Error processing file {filepath}: {str(e)}", "warning")
                        
            if skipped_temp_files > 0:
                self.log_message(f"⏳ Skipped temporary files: {skipped_temp_files}", "info")
                
            # Analyze problem files
            problem_files = {
                'missing_on_server': [],
                'hash_mismatch': [],
                'missing_on_client': []
            }
            
            missing_file_count = 0
            corrupt_file_count = 0
            new_file_count = 0
            
            # Check local files against server
            for relpath, file_info in local_files.items():
                if relpath not in server_files:
                    missing_file_count += 1
                    self.log_message(f"🗑️ File missing on server: {relpath}", "warning")
                    problem_files['missing_on_server'].append(file_info)
                else:
                    # Check file integrity
                    local_hash = self.calculate_file_hash(file_info['path'])
                    server_hash = server_files[relpath].get('hash')
                    
                    if local_hash != server_hash:
                        corrupt_file_count += 1
                        self.log_message(f"❌ Hash mismatch for: {relpath}", "warning")
                        problem_files['hash_mismatch'].append({
                            'relpath': relpath,
                            'local_path': file_info['path'],
                            'size': file_info['size'],
                            'server_hash': server_hash
                        })
                        
            # Check server files against local
            for relpath, server_info in server_files.items():
                local_path_full = os.path.join(local_path, relpath)
                
                if relpath not in local_files:
                    new_file_count += 1
                    self.log_message(f"📥 File missing locally: {relpath}", "info")
                    problem_files['missing_on_client'].append({
                        'relpath': relpath,
                        'local_path': local_path_full,
                        'size': server_info['size'],
                        'hash': server_info['hash']
                    })
                    
            # Stats
            total_problems = missing_file_count + corrupt_file_count + new_file_count
            self.log_message(f"📊 Total problems detected: {total_problems}", "info")
            self.log_message(f"📊 Missing on server: {missing_file_count}", "info")
            self.log_message(f"📊 Hash mismatch: {corrupt_file_count}", "info")
            self.log_message(f"📊 Missing on client: {new_file_count}", "info")
            
            if total_problems == 0:
                self.log_message("✅ All files are up-to-date!", "success")
                return
                
            # Remove files missing on server
            self.log_message(f"🗑️ Deleting {missing_file_count} files missing on server...", "info")
            
            for file_info in problem_files['missing_on_server']:
                try:
                    if os.path.exists(file_info['path']):
                        os.remove(file_info['path'])
                        self.log_message(f"✅ Deleted: {os.path.basename(file_info['path'])}", "info")
                except Exception as e:
                    self.log_message(f"❌ Delete error {file_info['path']}: {str(e)}", "error")
                    
            # Download missing and corrupted files
            files_to_download = []
            
            # Add new files from server
            for file_info in problem_files['missing_on_client']:
                files_to_download.append(file_info)
                
            # Add files with mismatched hashes
            for file_info in problem_files['hash_mismatch']:
                files_to_download.append({
                    'relpath': file_info['relpath'],
                    'local_path': file_info['local_path'],
                    'size': file_info['size'],
                    'hash': file_info['server_hash']
                })
                
            if files_to_download:
                self.log_message(f"⬇️ Starting download of {len(files_to_download)} files...", "info")
                download_result = self.download_manager.download_files(files_to_download, {})
                success_count = sum(1 for r in download_result['results'].values() if r)
                
                self.log_message(f"✅ Successfully processed: {success_count}/{len(files_to_download)} files", "success")
                
            # Final stats
            self.log_message(f"\n🎉 Sync completed successfully!", "success")
            self.log_message(f"Files processed: {total_files_count}", "info")
            self.log_message(f"Total size: {total_size_bytes/1024/1024:.1f} MB", "info")
            
        except ConnectionError as e:
            self.log_message(f"🌐 Connection error: {str(e)}", "error")
        except Exception as e:
            self.log_message(f"🔥 Critical error: {str(e)}", "error")
        finally:
            self.running = False
            
    def update_file_progress_cli(self, file_info, progress, downloaded, total, extra_info=None):
        """Update file progress for CLI"""
        if file_info and extra_info:
            filename = os.path.basename(file_info['relpath'])
            print(f"  {filename}: {progress:.1f}% ({downloaded/1024/1024:.1f}/{total/1024/1024:.1f}MB) {extra_info}")
        elif file_info:
            filename = os.path.basename(file_info['relpath'])
            print(f"  {filename}: {progress:.1f}% ({downloaded/1024/1024:.1f}/{total/1024/1024:.1f}MB)")
        else:
            print(f"Progress: {progress:.1f}%")
            
    def test_connection(self):
        """Test connection to server"""
        self.log_message("🔍 Testing server connection...", "info")
        
        results = ConnectionManager.test_connection_with_retry()
        
        if 'error' in results:
            self.log_message(f"🔴 Server unavailable: {results['error']}", "error")
            return False
        else:
            avg_speed = results.get('average_speed_mbps', 0)
            quality = results.get('connection_quality', 'unknown')
            self.log_message(f"🟢 Connection stable: {avg_speed:.2f} Mbps ({quality})", "success")
            return True


def main():
    parser = argparse.ArgumentParser(description='Minecraft Mod Sync Client (CLI)')
    parser.add_argument('--sync', action='store_true', help='Start synchronization')
    parser.add_argument('--test', action='store_true', help='Test server connection')
    parser.add_argument('--strategy', choices=[
        'stable_sequential', 'balanced_adaptive', 'fast_optimized', 'gaming_priority'
    ], default='balanced_adaptive', help='Download strategy to use')
    parser.add_argument('--mods-path', type=str, help='Path to mods folder')
    
    args = parser.parse_args()
    
    app = CLIModSyncApp()
    
    # Override mods path if provided
    if args.mods_path:
        app.mods_path = args.mods_path
        app.config_manager.set('paths', 'mods_folder', args.mods_path)
        app.config_manager.save_config()
    
    if args.test:
        app.test_connection()
    elif args.sync:
        app.sync_mods_cli(args.strategy)
    else:
        # Show help if no arguments provided
        parser.print_help()


if __name__ == "__main__":
    main()