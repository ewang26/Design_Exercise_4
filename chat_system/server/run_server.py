#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from chat_system.common.config import ConnectionSettings
from chat_system.server.replicated_server import ReplicatedChatServer

def main():
    parser = argparse.ArgumentParser(description="Run a replicated chat server")
    parser.add_argument("--server-id", type=int, required=True,
                      help="Server ID in the cluster")
    parser.add_argument("--config", type=str, required=True,
                      help="Path to cluster configuration file")
    parser.add_argument("--data-dir", type=str, required=True,
                      help="Directory for server data")
    
    args = parser.parse_args()
    
    # Load cluster configuration
    try:
        with open(args.config) as f:
            cluster_config = json.load(f)
    except Exception as e:
        print(f"Error loading cluster configuration: {e}")
        sys.exit(1)
    
    # Validate server ID
    if args.server_id < 0 or args.server_id >= len(cluster_config):
        print(f"Invalid server ID: {args.server_id}")
        sys.exit(1)
    
    # Create data directory
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and start server
    try:
        server = ReplicatedChatServer(
            server_id=args.server_id,
            cluster_config=cluster_config,
            data_dir=str(data_dir),
            config=ConnectionSettings()
        )
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 