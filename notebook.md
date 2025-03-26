# Engineering Notebook

### 3/26/25
### Adding replication to the chat system

- Final working version:
  - Merged the two server protos into one
  - Got the client retry system working
  - Got server replicas to send their state to the leader once they connect, so they can update their state if it's newer.

- Generate necessary gRPC files via:

```
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/chat.proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/raft.proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat_system/proto/server.proto
```

- Run server cluster via 
```
python -m chat_system.scripts.run_cluster
```

Run client via
```
python -m chat_system.scripts.run_cluster
```

- Created methods and added replication of client updates without much issue. I did discover that password hashes are not deterministic when being replicated, so I extended the proto to pass the password hash and salt.

### Testing suite:
We test both the both functional and fault-tolerance aspects of our distributed chat system.

- In ```test_accountmanager.py```, we test the core chat system logic by considering account creation & validation, user login, account listing, message ordering, and message deletion.
- In ```test_fault_tolerance.py```, we test the system's resilience by checking leader election and replication, persistence, and 2-node failure tolerance.


### 3/25/25

- Finally got a replicated system working, where each server pings the leader to check if it's still alive. If the leader fails, the server moves on to the next leader in the order. If a leader comes back online, they will signal to the other clients to reconnect to them. Things to do now:
  - Create methods in `server.py` to mirror the remaining gRPC services in `server.proto`
  - Use these methods in the server to handle the gRPC requests, so they will be automatically replicated to the other clients
  - Have the server send its state to the leader when it connects, so the leader can update its state if it's newer
  - Have the servers tell the client to reconnect to the leader if the leader comes back online
  - Have the client automatically switch to the next server in the list if the leader fails

- Replication is hard, man...

### 3/24/25

- Current thoughts for replication:
  - Use leader-follower replication model
  - Have a config file that specifies the IP addresses of the servers, use their ordering in the file to determine order of priority
  - Client automatically connects to the leader, if the leader fails, the client tries the next server in the list
  - Servers should have a gRPC heartbeat service that followers use to check if the leader is still alive
  - Since servers use the same data file, they also agree on who should be the next leader
  - Finally, if the leader comes back online, current leader should be able to signal to the client to reconnect to the leader
  - We need some way to sync the state between the servers when a new one starts up. We do this by having a `timestamp` field on the state snapshot that is updated every time the state is updated. When a server connects to the leader, it sends its current state. The leader updates its state if its newer, and sends the updated state to **all connected servers**.

- We based our redesign based on the gRPC implementation of the chat application from Design Exercise II. 
