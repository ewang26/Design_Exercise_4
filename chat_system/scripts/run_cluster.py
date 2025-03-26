#!/usr/bin/env python3
import argparse
import subprocess
import os
import signal
import sys
import time

def start_server(config_path, server_id, storage_dir):
    cmd = [
        "python", "-m", "chat_system.server", 
        config_path, str(server_id), storage_dir
    ]
    
    return subprocess.Popen(
        cmd,
        universal_newlines=True
    )

def main():
    parser = argparse.ArgumentParser(description='Run a cluster of chat servers')
    parser.add_argument('--config', default='chat_system/config/cluster_config.json', 
                       help='Path to cluster configuration file')
    parser.add_argument('--storage-base', default='chat_system/data', 
                       help='Base directory for server storage')
    parser.add_argument('--num-servers', type=int, default=3,
                       help='Number of servers to start')
    
    args = parser.parse_args()
    
    # Create storage directories if they don't exist
    for i in range(args.num_servers):
        os.makedirs(f"{args.storage_base}/server{i}", exist_ok=True)
    
    # Start servers
    servers = []
    for i in range(args.num_servers):
        print(f"Starting server {i}...")
        process = start_server(
            args.config, 
            i, 
            f"{args.storage_base}/server{i}"
        )
        servers.append(process)
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("Shutting down servers...")
        for process in servers:
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"Cluster of {args.num_servers} servers running.")
    print("Press Ctrl+C to shut down.")
    
    # Wait for processes
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main() 