import base64
import time

import grpc
from concurrent import futures
import json
import threading
from typing import Dict, Optional

from .server_state import ServerState
from ..common.distributed import DistributedConfig
from ..common.user import Message
from ..proto import chat_pb2, chat_pb2_grpc, server_pb2, server_pb2_grpc

class SyncServicer(server_pb2_grpc.SyncServiceServicer):
    def __init__(self, server):
        self.server = server

    def Health(self, request, context):
        print("Received ping from ", context.peer())
        return server_pb2.Empty()

    def MergeState(self, request, context):
        new_state = request.state
        return server_pb2.ServerState(
            state=json.dumps(self.server.merge_state(new_state))
        )

    def SetLeader(self, request, context):
        # Only adopt this leader if it's higher priority (lower index) than our current leader
        print("Received leader update from ", context.peer(), " of ", request.leader)
        if request.leader < self.server.leader:
            self.server.set_leader(request.leader)
        return server_pb2.Empty()

    def SyncAddUser(self, request, context):
        self.server.server_state.add_user(
            request.username,
            base64.b64decode(request.password.encode('ascii')),
            base64.b64decode(request.salt.encode('ascii'))
        )
        return server_pb2.Empty()

    def SyncDeleteUser(self, request, context):
        self.server.server_state.delete_account(request.username)
        return server_pb2.Empty()

    def SyncAddUnreadMessage(self, request, context):
        message = Message(request.message.id, request.message.sender, request.message.content)
        self.server.server_state.add_unread_message(request.user, message)
        return server_pb2.Empty()

    def SyncAddReadMessage(self, request, context):
        message = Message(request.message.id, request.message.sender, request.message.content)
        self.server.server_state.add_read_message(request.user, message)
        return server_pb2.Empty()

    def SyncRemoveUnreadMessage(self, request, context):
        self.server.server_state.remove_unread_message(request.user, request.message_id)
        return server_pb2.Empty()

    def SyncRemoveReadMessage(self, request, context):
        self.server.server_state.remove_read_message(request.user, request.message_id)
        return server_pb2.Empty()

class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self, server):
        self.server = server

    def _abort_if_not_leader(self, context):
        if not self.server.is_leader():
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not leader")

    def Health(self, request, context):
        return chat_pb2.Empty()

    def CreateAccount(self, request, context):
        self._abort_if_not_leader(context)
        error = self.server.server_state.create_account(request.username, request.password)
        return chat_pb2.CreateAccountResponse(error=error if error else None)

    def Login(self, request, context):
        self._abort_if_not_leader(context)
        user = self.server.server_state.login(request.username, request.password)
        if user:
            with self.server.sessions_lock:
                self.server.client_sessions[context.peer()] = user.name
            return chat_pb2.LoginResponse()
        return chat_pb2.LoginResponse(error="Invalid username or password")

    def Logout(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            if context.peer() in self.server.client_sessions:
                self.server.client_sessions[context.peer()] = None
        return chat_pb2.LogoutResponse()

    def ListUsers(self, request, context):
        self._abort_if_not_leader(context)
        accounts = self.server.server_state.list_accounts(request.pattern)
        offset = max(0, request.offset)
        if request.limit == -1:
            accounts = accounts[offset:]
        else:
            limit = min(len(accounts), offset + request.limit)
            accounts = accounts[offset:limit]
        return chat_pb2.ListUsersResponse(usernames=[user.name for user in accounts])

    def DeleteAccount(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            peer = context.peer()
            if peer not in self.server.client_sessions:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")

            username = self.server.client_sessions[peer]
            if not username:  # Check if username is None or empty, basically make sure it's valid
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")

            # Delete the account and remove session properly
            self.server.server_state.delete_account(username)
            self.server.client_sessions[peer] = None
        return chat_pb2.DeleteAccountResponse()

    def SendMessage(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            sender_id = self.server.client_sessions.get(context.peer())

        if not sender_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")

        recipient = request.receiver
        if self.server.server_state.get_user(recipient) is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Recipient not found")

        message = Message(self.server.server_state.timestamp, sender_id, request.content)

        # Check if recipient is online. Do this atomically
        with self.server.sessions_lock:
            online = False
            for peer, username in self.server.client_sessions.items():
                if username == recipient:
                    online = True
                    break

            if online:
                self.server.server_state.add_read_message(recipient, message)
                self.server.server_state.get_user(recipient).message_subscriber_queue.put(message)
            else:
                self.server.server_state.add_unread_message(recipient, message)

        return chat_pb2.SendMessageResponse()

    def GetNumberOfUnreadMessages(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.server_state.get_user(username)
        return chat_pb2.GetNumberOfUnreadMessagesResponse(
            count=user.get_number_of_unread_messages()
        )

    def GetNumberOfReadMessages(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.server_state.get_user(username)
        return chat_pb2.GetNumberOfReadMessagesResponse(
            count=user.get_number_of_read_messages()
        )

    def PopUnreadMessages(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        messages = self.server.server_state.pop_unread_messages(username, request.num_messages)
        return chat_pb2.PopUnreadMessagesResponse(
            messages=[
                chat_pb2.Message(id=m.id, sender=m.sender, content=m.content)
                for m in messages
            ]
        )

    def GetReadMessages(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.server_state.get_user(username)
        messages = user.get_read_messages(request.offset, request.num_messages)
        return chat_pb2.GetReadMessagesResponse(
            messages=[
                chat_pb2.Message(id=m.id, sender=m.sender, content=m.content)
                for m in messages
            ]
        )

    def DeleteMessages(self, request, context):
        self._abort_if_not_leader(context)
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        for mid in request.message_ids:
            self.server.server_state.remove_read_message(username, mid)
        return chat_pb2.DeleteMessagesResponse()

    def SubscribeToMessages(self, request, context):
        self._abort_if_not_leader(context)
        peer = context.peer()

        while context.is_active():
            with self.server.sessions_lock:
                username = self.server.client_sessions.get(peer)

            if username:
                user = self.server.server_state.get_user(username)
                if user:
                    # Check for new messages
                    # This get should block until a message is available
                    message = user.message_subscriber_queue.get()
                    if message is None: # None is the sentinel value for shutdown
                        break
                    yield chat_pb2.MessageNotification(
                        message=chat_pb2.Message(
                            id=message.id,
                            sender=message.sender,
                            content=message.content
                        )
                    )

class ChatServer:
    def __init__(self, config: DistributedConfig, server_id: int, save_path: str):
        self.server_id = server_id
        self.host = config.servers[server_id].host
        self.port = config.servers[server_id].port
        self.server_state = ServerState(self)
        self.client_sessions: Dict[str, Optional[str]] = {}  # peer -> username

        self.running = True
        self.server_path = save_path
        self.sessions_lock = threading.Lock()

        self.servers = [{
            "host": server.host,
            "port": server.port,
            "stub": None,
            "channel": None
        } for server in config.servers]
        self.leader = 0
        self.ping_pong_thread = None

    def save_state_to_file(self):
        """Save the server state to a file."""
        with open(self.server_path, "w") as f:
            f.write(json.dumps(self.server_state.get_state()))

    def load_state_from_file(self):
        try:
            with open(self.server_path) as f:
                d = json.load(f)
                self.server_state.load_state(d)
        except FileNotFoundError:
            print("No server state found, starting fresh")

    def merge_state(self, new_state):
        """
        Merge the new state with the current state, if it has a larger timestamp.
        Returns the new server state (merged or not).
        """
        state_json = json.loads(new_state)
        print("Merging against remote state:",
              self.server_state.timestamp, " vs. ", state_json["timestamp"])
        if state_json["timestamp"] > self.server_state.timestamp:
            self.server_state.load_state(state_json)

            # If we're the leader, broadcast this state change to all other servers
            if self.is_leader():
                self.broadcast_server_update(
                    lambda stub: stub.MergeState(server_pb2.ServerState(state=new_state))
                )

        return self.server_state.get_state()

    def connect_to_server(self, server_id):
        """Connect to another server."""
        host, port = self.servers[server_id]["host"], self.servers[server_id]["port"]
        channel = grpc.insecure_channel(f'{host}:{port}')
        stub = server_pb2_grpc.SyncServiceStub(channel)

        self.servers[server_id]["stub"] = stub
        self.servers[server_id]["channel"] = channel

    def is_leader(self):
        return self.server_id == self.leader

    def ping_pong(self):
        while self.running:
            # Ping the leader
            leader = self.servers[self.leader]
            try:
                print("Pinging leader ", self.leader)
                if self.leader != self.server_id:
                    leader["stub"].Health(server_pb2.Empty())

                # Sleep for a second
                time.sleep(1)
            except grpc.RpcError:
                print(f"Leader {self.leader} is down, going to next server")
                self.set_leader((self.leader + 1) % len(self.servers))

    def set_leader(self, server_id):
        self.leader = server_id

        # If we're the new leader, broadcast it to all servers
        if server_id == self.server_id:
            # Broadcast the new leader to all servers
            for i, server in enumerate(self.servers):
                if i == server_id:
                    continue
                try:
                    server["stub"].SetLeader(server_pb2.Leader(leader=server_id))
                except grpc.RpcError as e:
                    print(f"Failed to set leader on server {i}: {e.details()}")
        else:
            # Otherwise, send our state to the new leader
            res = self.servers[self.leader]["stub"].MergeState(
                server_pb2.ServerState(
                    state=json.dumps(self.server_state.get_state())
                )
            )

            # Merge the state we got back
            self.merge_state(res.state)

    def broadcast_server_update(self, method):
        # Only broadcast if we're the leader
        if self.server_id != self.leader:
            return

        for i, server in enumerate(self.servers):
            if i == self.server_id:
                continue
            try:
                method(server["stub"])
            except grpc.RpcError:
                print(f"Failed to broadcast to server {i}")

    def start(self):
        """Start the chat server."""
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

        # Listen for messages from client
        chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(self), server)

        # Listen to messages from other servers
        server_pb2_grpc.add_SyncServiceServicer_to_server(SyncServicer(self), server)

        server.add_insecure_port(f'{self.host}:{self.port}')
        server.start()
        print(f"Server started on {self.host}:{self.port}")

        time.sleep(1)

        # Try connecting to other servers
        for server_id in range(len(self.servers)):
            if server_id == self.server_id:
                continue
            self.connect_to_server(server_id)

        # Broadcast our start
        self.set_leader(self.leader)

        # Start the ping-pong thread
        self.ping_pong_thread = threading.Thread(target=self.ping_pong)
        self.ping_pong_thread.daemon = True
        self.ping_pong_thread.start()

        try:
            server.wait_for_termination()
        except KeyboardInterrupt:
            self.handle_shutdown()
        finally:
            print("Stopping server.")
            # Unblock all threads waiting on user.message_subscriber_queue.get()
            for user in self.server_state.accounts.values():
                user.message_subscriber_queue.put(None)
            server.stop(None)

    def handle_shutdown(self):
        """Handle server shutdown."""
        print("Server shutting down...")
        self.running = False
        print(f"Saving server state to {self.server_path}")
        self.save_state_to_file()
