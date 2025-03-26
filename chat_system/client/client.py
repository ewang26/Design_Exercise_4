import grpc
from typing import List
from ..common.distributed import DistributedConfig
from ..proto import chat_pb2, chat_pb2_grpc
from .gui import ChatGUI

class ChatClient:
    def __init__(self, config: DistributedConfig):
        self.servers = config.servers  # List of server addresses

        self.leader = None
        self.stub = None
        self.channel = None

        self.message_thread = None
        self.running = False

        # User we are currently logged in as
        self.username = None
        self.password = None

        self.gui = ChatGUI(
            on_login=self.login,
            on_logout=self.logout,
            on_create_account=self.create_account,
            on_send_message=self.send_message,
            on_list_accounts=self.list_accounts,
            on_delete_messages=self.delete_messages,
            on_delete_account=self.delete_account,
            get_read_messages=self.get_read_messages,
            on_pop_messages=self.pop_unread_messages
        )

    def start(self):
        """Start the client."""
        if self.discover_leader():
            self.gui.start()

    def discover_leader(self):
        """Try to find the current leader in the cluster."""
        if self.channel is not None:
            self.channel.close()

        # Loop through in order of priority; the first one we connect to will be the leader
        channel = None
        for i, server_address in enumerate(self.servers):
            # Skip the current leader
            if i == self.leader:
                continue

            try:
                # Connect to the server
                host, port = server_address.host, server_address.port
                channel = grpc.insecure_channel(f'{host}:{port}')
                stub = chat_pb2_grpc.ChatServiceStub(channel)

                # See if it's alive
                stub.Health(chat_pb2.Empty())

                # If the RPC call succeeds, it's alive
                self.leader = i
                self.channel = channel
                self.stub = stub
                self.gui.display_message(f"Found leader {i}: {host}:{port}")

                # Re-login if we were logged in
                if self.username is not None:
                    self.login(self.username, self.password)
                return True
            except grpc.RpcError:
                channel.close()

        self.gui.display_message("Failed to discover leader. Retry later.")
        return False

    def query_server(self, method):
        """Query the server with the given method and parameter. Retry if the server is not the leader."""
        if self.stub is None:
            self.gui.display_message("Not connected to a server")
            return

        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = method(self.stub)
                break
            except grpc.RpcError as e:
                self.gui.display_message(f"Server error: {e.details()}")
                # Try to find the new leader
                # If we get UNAVAILABLE, leader is down
                # If we get PERMISSION_DENIED, leader is not the leader anymore
                if e.code() == grpc.StatusCode.UNAVAILABLE \
                        or e.code() == grpc.StatusCode.PERMISSION_DENIED and "Not leader" in e.details():
                    self.gui.display_message("Server is not the leader. Finding new leader...")
                    self.discover_leader()
        return response

    # Actual implementation methods
    def create_account(self, username: str, password: str):
        """Send create account request."""
        try:
            response = self.query_server(lambda stub: stub.CreateAccount(
                chat_pb2.CreateAccountRequest(username=username, password=password)
            ))
            if response.error:
                self.gui.display_message(response.error)
            else:
                self.gui.display_message("Account created successfully, please log in")
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to create account: {e.details()}")

    def login(self, username: str, password: str):
        """Send login request."""
        try:
            response = self.query_server(lambda stub: stub.Login(
                chat_pb2.LoginRequest(username=username, password=password)
            ))
            if response.error:
                self.gui.display_message(response.error)
            else:
                self.username = username
                self.password = password
                self.gui.show_main_widgets()
                self._send_initial_requests()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to login: {e.details()}")

    def _send_initial_requests(self):
        """Send initial requests after login."""
        try:
            # Call asynchronously since they don't block each other
            unread = self.query_server(lambda stub: stub.GetNumberOfUnreadMessages.future(
                chat_pb2.GetNumberOfUnreadMessagesRequest()
            ))
            read = self.query_server(lambda stub: stub.GetNumberOfReadMessages.future(
                chat_pb2.GetNumberOfReadMessagesRequest()
            ))
            self.gui.update_unread_count(unread.result().count)
            self.gui.update_read_count(read.result().count)
            self.gui.update_messages_view()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to get message counts: {e.details()}")

    def logout(self):
        """Send logout request."""
        try:
            self.query_server(lambda stub: stub.Logout(chat_pb2.LogoutRequest()))
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to logout: {e.details()}")

        self.username = None
        self.password = None

    def list_accounts(self, pattern: str, offset: int, limit: int):
        """Send list accounts request."""
        try:
            response = self.query_server(lambda stub: stub.ListUsers(
                chat_pb2.ListUsersRequest(
                    pattern=pattern,
                    offset=offset,
                    limit=limit
                )
            ))
            self.gui.display_users(response.usernames)
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to list accounts: {e.details()}")

    def send_message(self, recipient_username: str, content: str):
        """Send a message to another user."""
        try:
            self.query_server(lambda stub: stub.SendMessage(
                chat_pb2.SendMessageRequest(
                    receiver=recipient_username,
                    content=content
                )
            ))
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to send message: {e.details()}")

    def pop_unread_messages(self, count: int):
        """Pop unread messages."""
        try:
            response = self.query_server(lambda stub: stub.PopUnreadMessages(
                chat_pb2.PopUnreadMessagesRequest(num_messages=count)
            ))
            self.gui.display_messages(response.messages)
            self._send_initial_requests()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to pop messages: {e.details()}")

    def get_read_messages(self, offset: int, limit: int):
        """Get read messages."""
        try:
            response = self.query_server(lambda stub: stub.GetReadMessages(
                chat_pb2.GetReadMessagesRequest(
                    offset=offset,
                    num_messages=limit
                )
            ))
            self.gui.display_messages(response.messages)
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to get messages: {e.details()}")

    def delete_messages(self, message_ids: List[int]):
        """Delete messages."""
        try:
            self.query_server(lambda stub: stub.DeleteMessages(
                chat_pb2.DeleteMessagesRequest(message_ids=message_ids)
            ))
            self._send_initial_requests()
            self.gui.update_messages_view()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to delete messages: {e.details()}")

    def delete_account(self):
        """Delete account."""
        try:
            self.query_server(lambda stub: stub.DeleteAccount(chat_pb2.DeleteAccountRequest()))
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to delete account: {e.details()}")

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
                if not self.running:
                    break
                self.gui.display_message(f"Connection error: {e.details()}")

                if self.discover_leader():
                    continue
                else:
                    break
