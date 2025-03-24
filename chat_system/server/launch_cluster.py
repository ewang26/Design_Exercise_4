#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Launch a replicated chat server cluster")
    parser.add_argument("--servers", type=int, default=3,
                      help="Number of servers in the cluster (default: 3)")
    parser.add_argument("--base-port", type=int, default=50051,
                      help="Base port number (default: 50051)")
    parser.add_argument("--host", type=str, default="localhost",
                      help="Host name (default: localhost)")
    parser.add_argument("--data-dir", type=str, default="./data",
                      help="Base directory for server data (default: ./data)")
    
    args = parser.parse_args()
    
    if args.servers < 3:
        print("Error: At least 3 servers are required for fault tolerance")
        sys.exit(1)
    
    # Create data directory
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create cluster configuration
    cluster_config = []
    for i in range(args.servers):
        cluster_config.append((args.host, args.base_port + i))
    
    # Write cluster configuration
    config_path = data_dir / "cluster_config.json"
    with open(config_path, "w") as f:
        json.dump(cluster_config, f)
    
    # Launch servers
    processes = []
    for i in range(args.servers):
        server_data_dir = data_dir / f"server_{i}"
        server_data_dir.mkdir(exist_ok=True)
        
        cmd = [
            sys.executable,
            "-m", "chat_system.server.run_server",
            "--server-id", str(i),
            "--config", str(config_path),
            "--data-dir", str(server_data_dir)
        ]
        
        # Start the server process
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        processes.append(proc)
        print(f"Started server {i} on {args.host}:{args.base_port + i}")
        time.sleep(1)  # Give each server time to start
    
    print(f"\nCluster of {args.servers} servers started")
    print("Press Ctrl+C to stop the cluster")
    
    try:
        # Monitor server processes
        while True:
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    # Server crashed, print its output
                    out, err = proc.communicate()
                    print(f"\nServer {i} crashed!")
                    print("Output:", out)
                    print("Error:", err)
                    
                    # Restart the server
                    cmd = [
                        sys.executable,
                        "-m", "chat_system.server.run_server",
                        "--server-id", str(i),
                        "--config", str(config_path),
                        "--data-dir", str(data_dir / f"server_{i}")
                    ]
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True
                    )
                    processes[i] = proc
                    print(f"Restarted server {i}")
            
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\nStopping cluster...")
        for proc in processes:
            proc.terminate()
        
        # Wait for all processes to terminate
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        
        print("All servers stopped")

if __name__ == "__main__":
    main() 