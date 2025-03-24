import grpc
import threading
from typing import Any, List, Optional
from ..common.config import ConnectionSettings
from ..proto import chat_pb2, chat_pb2_grpc
from .gui import ChatGUI

class ChatClient:
    def __init__(self, config: ConnectionSettings = ConnectionSettings()):
        self.host = config.host
        self.port = config.port
        self.channel = None
        self.stub = None

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

    def connect(self) -> bool:
        """Connect to the server."""
        try:
            self.channel = grpc.insecure_channel(f'{self.host}:{self.port}')
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)

            # Start message subscription thread
            thread = threading.Thread(target=self._receive_messages)
            thread.daemon = True
            thread.start()
            return True
        except Exception as e:
            self.gui.display_message(f"Connection failed: {e}")
            return False

    def start(self):
        """Start the client."""
        if self.connect():
            self.gui.start()

    def create_account(self, username: str, password: str):
        """Send create account request."""
        try:
            response = self.stub.CreateAccount(
                chat_pb2.CreateAccountRequest(username=username, password=password)
            )
            if response.error:
                self.gui.display_message(response.error)
            else:
                self.gui.display_message("Account created successfully, please log in")
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to create account: {e.details()}")

    def login(self, username: str, password: str):
        """Send login request."""
        try:
            response = self.stub.Login(
                chat_pb2.LoginRequest(username=username, password=password)
            )
            if response.error:
                self.gui.display_message(response.error)
            else:
                self.gui.show_main_widgets()
                self._send_initial_requests()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to login: {e.details()}")

    def _send_initial_requests(self):
        """Send initial requests after login."""
        try:
            # Call asynchronously since they don't block each other
            unread = self.stub.GetNumberOfUnreadMessages.future(
                chat_pb2.GetNumberOfUnreadMessagesRequest()
            )
            read = self.stub.GetNumberOfReadMessages.future(
                chat_pb2.GetNumberOfReadMessagesRequest()
            )
            self.gui.update_unread_count(unread.result().count)
            self.gui.update_read_count(read.result().count)
            self.gui.update_messages_view()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to get message counts: {e.details()}")

    def logout(self):
        """Send logout request."""
        try:
            self.stub.Logout(chat_pb2.LogoutRequest())
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to logout: {e.details()}")

    def list_accounts(self, pattern: str, offset: int, limit: int):
        """Send list accounts request."""
        try:
            response = self.stub.ListUsers(
                chat_pb2.ListUsersRequest(
                    pattern=pattern,
                    offset=offset,
                    limit=limit
                )
            )
            self.gui.display_users(response.usernames)
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to list accounts: {e.details()}")

    def send_message(self, recipient_username: str, content: str):
        """Send a message to another user."""
        try:
            self.stub.SendMessage(
                chat_pb2.SendMessageRequest(
                    receiver=recipient_username,
                    content=content
                )
            )
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to send message: {e.details()}")

    def pop_unread_messages(self, count: int):
        """Pop unread messages."""
        try:
            response = self.stub.PopUnreadMessages(
                chat_pb2.PopUnreadMessagesRequest(num_messages=count)
            )
            self.gui.display_messages(response.messages)
            self._send_initial_requests()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to pop messages: {e.details()}")

    def get_read_messages(self, offset: int, limit: int):
        """Get read messages."""
        try:
            response = self.stub.GetReadMessages(
                chat_pb2.GetReadMessagesRequest(
                    offset=offset,
                    num_messages=limit
                )
            )
            self.gui.display_messages(response.messages)
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to get messages: {e.details()}")

    def delete_messages(self, message_ids: List[int]):
        """Delete messages."""
        try:
            self.stub.DeleteMessages(
                chat_pb2.DeleteMessagesRequest(message_ids=message_ids)
            )
            self._send_initial_requests()
            self.gui.update_messages_view()
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to delete messages: {e.details()}")

    def delete_account(self):
        """Delete account."""
        try:
            self.stub.DeleteAccount(chat_pb2.DeleteAccountRequest())
        except grpc.RpcError as e:
            self.gui.display_message(f"Failed to delete account: {e.details()}")

    def _receive_messages(self):
        """Receive messages from the server."""
        while True:
            try:
                for notification in self.stub.SubscribeToMessages(chat_pb2.SubscribeRequest()):
                    msg = notification.message
                    self.gui.display_message(f"New message from {msg.sender}")
                    self._send_initial_requests()
                    self.gui.update_messages_view()
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED:
                    break
                self.gui.display_message(f"Connection error: {e.details()}")
                break
