#!/usr/bin/env python3
import subprocess
import time
import signal
import sys
import os
import argparse

def launch_distributed_system(num_nodes=3, start_port=8888, config_file="config_distributed.json"):
    """
    Launch a distributed chat system with multiple nodes.
    
    Args:
        num_nodes: Number of nodes to launch
        start_port: Starting port for client connections
        config_file: Configuration file to use
    """
    processes = []
    
    try:
        for i in range(1, num_nodes + 1):
            node_id = f"node{i}"
            port = start_port + i - 1
            
            # Create data directory for this node
            data_dir = os.path.join("server_data", node_id)
            os.makedirs(data_dir, exist_ok=True)
            
            # Start the server process
            cmd = [
                "python", "-m", "chat_system.server",
                config_file,
                "--node-id", node_id
            ]
            
            env = os.environ.copy()
            # Override port for each node
            env["CHAT_PORT"] = str(port)
            env["RAFT_PORT"] = str(port + 1000)
            
            process = subprocess.Popen(
                cmd, 
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            processes.append(process)
            print(f"Started node {node_id} with client port {port} and Raft port {port + 1000}")
            
            # Wait a bit between starting nodes to avoid race conditions
            time.sleep(1)
        
        print(f"\nDistributed system with {num_nodes} nodes is running")
        print("Press Ctrl+C to stop all nodes")
        
        # Wait for all processes to complete (or until interrupted)
        for process in processes:
            process.wait()
            
    except KeyboardInterrupt:
        print("\nShutting down all nodes...")
        for process in processes:
            process.send_signal(signal.SIGTERM)
            
        # Wait for processes to terminate
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        print("All nodes terminated")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch a distributed chat system")
    parser.add_argument("--nodes", type=int, default=3, help="Number of nodes to launch")
    parser.add_argument("--start-port", type=int, default=8888, help="Starting port for client connections")
    parser.add_argument("--config", default="config_distributed.json", help="Configuration file")
    
    args = parser.parse_args()
    
    launch_distributed_system(args.nodes, args.start_port, args.config) 