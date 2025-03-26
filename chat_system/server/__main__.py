import sys
import os
import signal
import argparse

from .raft_server import RaftNode
from .cluster_config import ClusterConfig

def main():
    parser = argparse.ArgumentParser(description='Start a Raft chat server')
    parser.add_argument('config_file', help='Path to cluster configuration file')
    parser.add_argument('server_id', type=int, help='Server ID (0-indexed)')
    parser.add_argument('storage_dir', help='Directory for persistent storage')
    
    args = parser.parse_args()
    
    # Load cluster configuration
    config = ClusterConfig(args.config_file)
    
    # Get server-specific configuration
    server_config = config.get_server_config(args.server_id)
    server_id = f"server{args.server_id}"
    
    # Get raft address (host:port)
    raft_address = f"{server_config['host']}:{server_config['raft_port']}"
    
    # Get peer addresses
    peers = config.get_peer_addresses(args.server_id)
    
    # Create storage directory if it doesn't exist
    os.makedirs(args.storage_dir, exist_ok=True)
    
    # Create and start the Raft node
    node = RaftNode(
        server_id=server_id,
        server_address=raft_address,
        peers=peers,
        storage_dir=args.storage_dir,
        chat_port=server_config['chat_port']
    )
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print(f"Shutting down server {server_id}...")
        node.server.stop(0)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the server
    print(f"Starting server {server_id} at {raft_address}")
    node.start()

if __name__ == "__main__":
    main()
