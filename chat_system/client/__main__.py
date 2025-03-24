import sys
from .client import ChatClient
from ..common.config import load_config

def main():
    # Load config from file
    if len(sys.argv) > 1:
        config = load_config(sys.argv[1])
    else:
        config = load_config()

    # Start client
    client = ChatClient(config)
    client.start()

if __name__ == "__main__":
    main()
