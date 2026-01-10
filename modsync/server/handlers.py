"""
HTTP request handlers for ModSync server
"""

import http.server
import json
import os
import urllib.parse
import re
from datetime import datetime


class RequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the ModSync server"""
    
    def __init__(self, server_instance, *args, **kwargs):
        self.server_instance = server_instance
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Log HTTP requests"""
        self.server_instance.logger.info(f"Request: {self.address_string()} - {format % args}")
    
    def send_json_response(self, data: dict, status_code: int = 200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')  # CORS
        self.end_headers()
        
        json_data = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.wfile.write(json_data)
        
        self.server_instance.stats.add_bytes_sent(len(json_data))
    
    def do_GET(self):
        """Handle GET requests"""
        self.server_instance.stats.increment_requests()
        self.server_instance.stats.increment_connections()
        
        try:
            if self.path == '/files' or self.path == '/api/files':
                # List files
                file_list = self.server_instance.file_service.get_file_list()
                self.send_json_response({
                    'status': 'success',
                    'files': file_list,
                    'total_count': len(file_list)
                })
            
            elif self.path == '/server_info' or self.path == '/api/info':
                # Server info
                info = self.server_instance.server_info_service.get_server_info(
                    self.server_instance.stats, 
                    self.server_instance.file_service
                )
                self.send_json_response({
                    'status': 'success',
                    'info': info
                })
            
            elif self.path.startswith('/mods/') or self.path.startswith('/files/'):
                # Serve specific file
                # Extract file path from URL
                if self.path.startswith('/mods/'):
                    relpath = self.path[6:]  # '/mods/' -> ''
                else:
                    relpath = self.path[7:]  # '/files/' -> ''

                # Decode URL path and normalize
                relpath = urllib.parse.unquote(relpath)
                relpath = os.path.normpath(relpath).replace('\\', '/')

                # Check that path doesn't try to escape directory
                if '..' in relpath or relpath.startswith('/') or relpath.startswith('../'):
                    self.send_error(403, "Forbidden")
                    return

                filepath = os.path.join(self.server_instance.file_service.mods_directory, relpath)

                if os.path.exists(filepath) and os.path.isfile(filepath):
                    # Serve the file
                    self.send_response(200)
                    self.send_header('Content-type', 'application/octet-stream')
                    self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(filepath)}"')
                    self.send_header('Content-Length', str(os.path.getsize(filepath)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()

                    with open(filepath, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.server_instance.stats.add_bytes_sent(len(chunk))
                else:
                    self.send_error(404, "File not found")
            
            elif self.path.startswith('/speed_test_') and self.path.endswith('.bin'):
                # Speed test - generate files of different sizes
                size_match = re.search(r'speed_test_(\d+)([km])b\.bin$', self.path, re.IGNORECASE)
                if size_match:
                    size_val = int(size_match.group(1))
                    size_unit = size_match.group(2).lower()
                    
                    if size_unit == 'k':
                        size_bytes = size_val * 1024
                    elif size_unit == 'm':
                        size_bytes = size_val * 1024 * 1024
                    else:
                        self.send_error(400, "Invalid size unit")
                        return
                    
                    # Limit file size
                    size_bytes = min(size_bytes, 100 * 1024 * 1024)  # Max 100MB

                    self.send_response(200)
                    self.send_header('Content-type', 'application/octet-stream')
                    self.send_header('Content-Length', str(size_bytes))
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()

                    # Send random data for speed test
                    sent = 0
                    while sent < size_bytes:
                        chunk_size = min(8192, size_bytes - sent)
                        chunk = os.urandom(chunk_size)  # Generate random data
                        self.wfile.write(chunk)
                        sent += chunk_size
                        self.server_instance.stats.add_bytes_sent(chunk_size)
                else:
                    self.send_error(400, "Invalid speed test file request")
            
            else:
                # Root path - server info
                if self.path == '/' or self.path == '/api':
                    info = self.server_instance.server_info_service.get_server_info(
                        self.server_instance.stats, 
                        self.server_instance.file_service
                    )
                    self.send_json_response({
                        'status': 'success',
                        'message': 'ModSync Server API v1.0',
                        'info': info
                    })
                else:
                    self.send_error(404, "Not Found")
        
        finally:
            self.server_instance.stats.decrement_connections()