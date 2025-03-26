import time

import grpc
from concurrent import futures
import signal
import json
import threading
from typing import Dict, Optional

from chat_system.common.config import ConnectionSettings
from .account_manager import AccountManager
from ..common.distributed import DistributedConfig
from ..common.user import Message
from ..proto import chat_pb2, chat_pb2_grpc, server_pb2, server_pb2_grpc

class SyncServicer(server_pb2_grpc.SyncServiceServicer):
    def __init__(self, server):
        self.server = server

    def Health(self, request, context):
        print("Received ping from ", context.peer())
        return server_pb2.Empty()

    def SetLeader(self, request, context):
        # Only adopt this leader if it's higher priority (lower index) than our current leader
        if request.leader < self.server.leader:
            self.server.set_leader(request.leader)
        return server_pb2.Empty()

    # TODO: Implement remaining methods

class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self, server):
        self.server = server

    def CreateAccount(self, request, context):
        error = self.server.account_manager.create_account(request.username, request.password)
        return chat_pb2.CreateAccountResponse(error=error if error else None)

    def Login(self, request, context):
        user = self.server.account_manager.login(request.username, request.password)
        if user:
            with self.server.sessions_lock:
                self.server.client_sessions[context.peer()] = user.name
            return chat_pb2.LoginResponse()
        return chat_pb2.LoginResponse(error="Invalid username or password")

    def Logout(self, request, context):
        with self.server.sessions_lock:
            if context.peer() in self.server.client_sessions:
                self.server.client_sessions[context.peer()] = None
        return chat_pb2.LogoutResponse()

    def ListUsers(self, request, context):
        accounts = self.server.account_manager.list_accounts(request.pattern)
        offset = max(0, request.offset)
        if request.limit == -1:
            accounts = accounts[offset:]
        else:
            limit = min(len(accounts), offset + request.limit)
            accounts = accounts[offset:limit]
        return chat_pb2.ListUsersResponse(usernames=[user.name for user in accounts])

    def DeleteAccount(self, request, context):
        with self.server.sessions_lock:
            peer = context.peer()
            if peer not in self.server.client_sessions:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")

            username = self.server.client_sessions[peer]
            if not username:  # Check if username is None or empty, basically make sure it's valid
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")

            # Delete the account and remove session properly
            self.server.account_manager.delete_account(username)
            self.server.client_sessions[peer] = None
        return chat_pb2.DeleteAccountResponse()

    def SendMessage(self, request, context):
        with self.server.sessions_lock:
            sender_id = self.server.client_sessions.get(context.peer())

        if not sender_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Not logged in")

        recipient = request.receiver
        if self.server.account_manager.get_user(recipient) is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Recipient not found")

        message = Message(self.server.next_message_id, sender_id, request.content)
        self.server.next_message_id += 1

        # Check if recipient is online. Do this atomically
        with self.server.sessions_lock:
            online = False
            for peer, username in self.server.client_sessions.items():
                if username == recipient:
                    online = True
                    break

            if online:
                user = self.server.account_manager.get_user(recipient)
                user.add_read_message(message)
                user.message_subscriber_queue.put(message)
            else:
                self.server.account_manager.get_user(recipient).add_message(message)

        return chat_pb2.SendMessageResponse()

    def GetNumberOfUnreadMessages(self, request, context):
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.account_manager.get_user(username)
        return chat_pb2.GetNumberOfUnreadMessagesResponse(
            count=user.get_number_of_unread_messages()
        )

    def GetNumberOfReadMessages(self, request, context):
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.account_manager.get_user(username)
        return chat_pb2.GetNumberOfReadMessagesResponse(
            count=user.get_number_of_read_messages()
        )

    def PopUnreadMessages(self, request, context):
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.account_manager.get_user(username)
        messages = user.pop_unread_messages(request.num_messages)
        return chat_pb2.PopUnreadMessagesResponse(
            messages=[
                chat_pb2.Message(id=m.id, sender=m.sender, content=m.content)
                for m in messages
            ]
        )

    def GetReadMessages(self, request, context):
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.account_manager.get_user(username)
        messages = user.get_read_messages(request.offset, request.num_messages)
        return chat_pb2.GetReadMessagesResponse(
            messages=[
                chat_pb2.Message(id=m.id, sender=m.sender, content=m.content)
                for m in messages
            ]
        )

    def DeleteMessages(self, request, context):
        with self.server.sessions_lock:
            username = self.server.client_sessions[context.peer()]

        user = self.server.account_manager.get_user(username)
        user.delete_messages(request.message_ids)
        return chat_pb2.DeleteMessagesResponse()

    def SubscribeToMessages(self, request, context):
        peer = context.peer()

        while context.is_active():
            with self.server.sessions_lock:
                username = self.server.client_sessions.get(peer)

            if username:
                user = self.server.account_manager.get_user(username)
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
        self.account_manager = AccountManager()
        self.client_sessions: Dict[str, Optional[str]] = {}  # peer -> username
        self.next_message_id = 0
        self.timestamp = 0

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

    def get_state(self):
        state = {
            "account_manager": self.account_manager.get_state(),
            "next_message_id": self.next_message_id,
            "timestamp": self.timestamp
        }
        return json.dumps(state)

    def load_state(self, str):
        """Load the server state from the given string."""
        state = json.load(str)
        self.account_manager.load_state(state["account_manager"])
        self.next_message_id = state["next_message_id"]
        self.timestamp = state["timestamp"]

    def save_state_to_file(self):
        """Save the server state to a file."""
        with open(self.server_path, "w") as f:
            f.write(self.get_state())

    def load_state_from_file(self):
        try:
            with open(self.server_path) as f:
                self.load_state(f)
        except FileNotFoundError:
            print("No server state found, starting fresh")

    def connect_to_server(self, server_id):
        """Connect to another server."""
        host, port = self.servers[server_id]["host"], self.servers[server_id]["port"]
        channel = grpc.insecure_channel(f'{host}:{port}')
        stub = server_pb2_grpc.SyncServiceStub(channel)

        self.servers[server_id]["stub"] = stub
        self.servers[server_id]["channel"] = channel

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
                except grpc.RpcError:
                    print(f"Failed to set leader on server {i}")

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
            for user in self.account_manager.accounts.values():
                user.message_subscriber_queue.put(None)
            server.stop(None)

    def handle_shutdown(self):
        """Handle server shutdown."""
        print("Server shutting down...")
        self.running = False
        print(f"Saving server state to {self.server_path}")
        self.save_state_to_file()
