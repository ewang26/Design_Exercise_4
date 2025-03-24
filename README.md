# CS 2620 Distributed Chat System

This project is a client-server chat system with support for fault tolerance and persistence. The architecture is detailed in the [design document](design.md).

## Features

- Create and log into accounts with secure password handling
- List accounts with wildcard pattern matching
- Send and receive messages between users
- Read messages with pagination
- Delete messages
- Delete accounts
- 2-fault tolerant backend (can tolerate up to 2 node failures)
- Persistent message storage that survives server restarts

## Configuration

The system can be configured using a JSON configuration file. Main configuration options:

- `host`: The host to bind the server to. Default is `localhost`.
- `port`: The port to bind the server to. Default is `8888`.
- `server_data`: The path to the server data file. Default is `server_data.json`.
- `distributed_mode`: Whether to run in distributed mode. Default is `false`.
- `peers`: Dictionary mapping node IDs to their Raft addresses.
- `server_addresses`: List of server addresses for clients to connect to.

Example configuration for distributed mode is in `config_distributed.json`.

## Running in Standalone Mode

Generate the gRPC code from the proto files:
```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/chat.proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/raft.proto
```

Start the server:
```bash
python -m chat_system.server
```

Start the client:
```bash
python -m chat_system.client
```

## Running in Distributed Mode

The distributed mode uses the Raft consensus algorithm to replicate state across multiple server nodes, providing fault tolerance and persistence.

### Manual Setup

1. Generate the gRPC code as described above.

2. Start multiple server nodes, each with a unique node ID:

```bash
# Start node 1 (port 8888 for clients, 9888 for Raft)
python -m chat_system.server config_distributed.json --node-id node1

# Start node 2 (port 8889 for clients, 9889 for Raft)
CHAT_PORT=8889 RAFT_PORT=9889 python -m chat_system.server config_distributed.json --node-id node2

# Start node 3 (port 8890 for clients, 9890 for Raft)
CHAT_PORT=8890 RAFT_PORT=9890 python -m chat_system.server config_distributed.json --node-id node3
```

3. Start a client that can connect to any of the server nodes:
```bash
python -m chat_system.client
```

### Using the Launch Script

For convenience, a script is provided to launch multiple nodes:

```bash
python launch_distributed.py --nodes 3 --start-port 8888
```

This will start three server nodes with consecutive ports.

