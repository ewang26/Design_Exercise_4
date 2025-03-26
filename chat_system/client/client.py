import grpc
import threading
from typing import Any, List, Optional
from ..common.distributed import DistributedConfig
from ..proto import chat_pb2, chat_pb2_grpc
from .gui import ChatGUI

class ChatClient:
    def __init__(self, config: DistributedConfig, server_id: int):
        self.host = config.servers[server_id].host
        self.port = config.servers[server_id].port
        self.config = config
        self.servers = config.servers  # List of server addresses

        self.leader_address = None
        self.stub = None
        self.channel = None
        self.gui = config.gui

        self.message_thread = None
        self.running = False

        # Connect to one of the servers and find the leader
        self._discover_leader()

    def _discover_leader(self):
        """Try to find the current leader in the cluster."""
        for server_address in self.servers:
            try:
                # Connect to the server
                channel = grpc.insecure_channel(server_address)
                stub = raft_pb2_grpc.RaftServiceStub(channel)

                # Ask for leader
                response = stub.GetLeader(raft_pb2.GetLeaderRequest())

                if response.leaderAddress:
                    # Found leader, connect to it
                    if self.channel:
                        self.channel.close()

                    self.leader_address = response.leaderAddress
                    self.channel = grpc.insecure_channel(self.leader_address)
                    self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
                    self.gui.display_message(f"Connected to leader at {self.leader_address}")
                    return True

                channel.close()
            except Exception as e:
                self.gui.display_message(f"Error connecting to {server_address}: {e}")

        self.gui.display_message("Failed to discover leader. Retry later.")
        return False

    def _handle_server_failure(self, func_name, *args, **kwargs):
        """Handle server failures by trying to reconnect to the new leader."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Try to execute the original function
                return getattr(self, f"_{func_name}")(*args, **kwargs)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.UNAVAILABLE and "Not leader" in e.details():
                    # Server is not the leader, find new leader
                    self.gui.display_message("Server is not the leader. Finding new leader...")
                    if self._discover_leader():
                        continue  # Retry with new leader

                if attempt < max_retries - 1:
                    self.gui.display_message(f"Server error: {e.details()}. Retrying ({attempt+1}/{max_retries})...")
                    time.sleep(1)  # Wait before retry
                    if self._discover_leader():  # Try to find a new leader
                        continue
                else:
                    self.gui.display_message(f"Failed after {max_retries} attempts: {e.details()}")
                    raise

    # Wrapped methods that handle server failures
    def create_account(self, username: str, password: str):
        return self._handle_server_failure('create_account_impl', username, password)

    def login(self, username: str, password: str):
        return self._handle_server_failure('login_impl', username, password)

    def logout(self):
        return self._handle_server_failure('logout_impl')

    def list_users(self, pattern: str = "", offset: int = 0, limit: int = -1):
        return self._handle_server_failure('list_users_impl', pattern, offset, limit)

    def send_message(self, receiver: str, content: str):
        return self._handle_server_failure('send_message_impl', receiver, content)

    def get_unread_message_count(self):
        return self._handle_server_failure('get_unread_message_count_impl')

    def get_read_message_count(self):
        return self._handle_server_failure('get_read_message_count_impl')

    def pop_unread_messages(self, num_messages: int = -1):
        return self._handle_server_failure('pop_unread_messages_impl', num_messages)

    def get_read_messages(self, offset: int = 0, limit: int = -1):
        return self._handle_server_failure('get_read_messages_impl', offset, limit)

    def delete_messages(self, message_ids: List[int]):
        return self._handle_server_failure('delete_messages_impl', message_ids)

    def delete_account(self):
        return self._handle_server_failure('delete_account_impl')

    # Actual implementation methods
    def _create_account_impl(self, username: str, password: str):
        try:
            response = self.stub.CreateAccount(
                chat_pb2.CreateAccountRequest(
                    username=username,
                    password=password
                )
            )
            if response.HasField('error'):
                self.gui.display_message(f"Failed to create account: {response.error}")
                return False
            self.gui.display_message(f"Account created successfully: {username}")
            return True
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to create account: {e.details()}")
            raise

    def _login_impl(self, username: str, password: str):
        try:
            response = self.stub.Login(
                chat_pb2.LoginRequest(
                    username=username,
                    password=password
                )
            )
            if response.HasField('error'):
                self.gui.display_message(f"Login failed: {response.error}")
                return False

            self.gui.display_message(f"Logged in as {username}")

            # Start receiving messages
            self.running = True
            self.message_thread = threading.Thread(target=self._receive_messages)
            self.message_thread.daemon = True
            self.message_thread.start()

            # Get initial data
            self._send_initial_requests()

            return True
        except grpc.RpcError as e:
            self.gui.display_message(f"Login failed: {e.details()}")
            raise

    def _send_initial_requests(self):
        """Send initial requests after login."""
        try:
            # Get unread message count
            response = self.stub.GetNumberOfUnreadMessages(
                chat_pb2.GetNumberOfUnreadMessagesRequest()
            )
            self.gui.display_message(f"You have {response.count} unread messages")

            # Get read message count
            response = self.stub.GetNumberOfReadMessages(
                chat_pb2.GetNumberOfReadMessagesRequest()
            )
            self.gui.display_message(f"You have {response.count} read messages")

        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to get initial data: {e.details()}")

    def _receive_messages(self):
        """Receive messages from the server."""
        while self.running:
            try:
                for notification in self.stub.SubscribeToMessages(chat_pb2.SubscribeRequest()):
                    msg = notification.message
                    self.gui.display_message(f"New message from {msg.sender}")
                    self._send_initial_requests()
                    self.gui.update_messages_view()
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED or not self.running:
                    break

                self.gui.display_message(f"Connection error: {e.details()}")

                # Try to reconnect
                time.sleep(1)
                if self._discover_leader():
                    continue
                else:
                    break
