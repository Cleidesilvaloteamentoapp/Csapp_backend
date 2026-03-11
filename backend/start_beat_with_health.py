#!/usr/bin/env python3
"""
Start Celery Beat with a minimal HTTP health endpoint for Railway.
Railway requires a healthcheck endpoint, but Celery Beat doesn't expose HTTP.
This script runs both: a simple HTTP server for /health and Celery Beat.
"""
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that only responds to /health"""
    
    def do_GET(self):
        if self.path in ['/health', '/']:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","service":"celery-beat"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP access logs"""
        pass


def start_health_server(port):
    """Start HTTP server in background thread"""
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Health check server listening on port {port}")
    server.serve_forever()


def start_celery_beat():
    """Start Celery Beat process"""
    print("Starting Celery Beat...")
    cmd = [
        'celery',
        '-A', 'app.tasks.celery_app',
        'beat',
        '--loglevel=info'
    ]
    
    # Run Celery Beat and wait for it
    process = subprocess.Popen(cmd)
    process.wait()
    sys.exit(process.returncode)


if __name__ == '__main__':
    # Get port from Railway or default to 8000
    port = int(os.environ.get('PORT', 8000))
    
    # Start health server in background thread
    health_thread = Thread(target=start_health_server, args=(port,), daemon=True)
    health_thread.start()
    
    # Start Celery Beat in main thread (blocks)
    start_celery_beat()
