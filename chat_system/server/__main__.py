import argparse
from .server import ChatServer
from ..common.distributed import load_config

def main():
    parser = argparse.ArgumentParser(prog='Chat Server')
    parser.add_argument('config_file', type=str, help='Path to the config file')
    parser.add_argument('server_id', type=int, help='The server ID')
    parser.add_argument('save_path', type=str, help='Path to the file to save the server state')
    args = parser.parse_args()

    # Read in config file
    config = load_config(args.config_file)

    # Start server
    server = ChatServer(config, args.server_id, args.save_path)
    server.load_state_from_file()
    server.start()

if __name__ == "__main__":
    main()
