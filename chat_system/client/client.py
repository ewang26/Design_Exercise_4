import grpc
import threading
import random
import time
from typing import Any, List, Optional
from ..common.config import ConnectionSettings
from ..proto import chat_pb2, chat_pb2_grpc
from .gui import ChatGUI

class ChatClient:
    def __init__(self, config: ConnectionSettings = ConnectionSettings()):
        self.host = config.host
        self.port = config.port
        self.server_addresses = config.server_addresses or [f"{self.host}:{self.port}"]
        self.current_server_index = 0
        self.channel = None
        self.stub = None
        self.reconnect_timeout = 1.0  # Initial reconnect timeout (will increase exponentially)
        self.max_reconnect_timeout = 30.0  # Maximum reconnect timeout
        self.message_thread = None
        self.shutdown_flag = threading.Event()

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
        """Connect to a server, trying each one until successful."""
        # Close existing channel if any
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
        
        # Try each server in the list
        for i in range(len(self.server_addresses)):
            server_addr = self.server_addresses[(self.current_server_index + i) % len(self.server_addresses)]
            try:
                self.gui.display_message(f"Connecting to server at {server_addr}...")
                self.channel = grpc.insecure_channel(server_addr)
                self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
                
                # Test connection with a simple request
                # We use the ListUsers endpoint with a simple query to verify connection
                self.stub.ListUsers(
                    chat_pb2.ListUsersRequest(pattern="", offset=0, limit=1),
                    timeout=2.0
                )
                
                # Connection successful, update current server index
                self.current_server_index = (self.current_server_index + i) % len(self.server_addresses)
                self.gui.display_message(f"Connected to server at {server_addr}")
                
                # Start message subscription thread
                if self.message_thread and self.message_thread.is_alive():
                    self.shutdown_flag.set()  # Signal existing thread to shut down
                    self.message_thread.join(1.0)  # Wait for it to complete
                
                self.shutdown_flag.clear()
                self.message_thread = threading.Thread(target=self._receive_messages)
                self.message_thread.daemon = True
                self.message_thread.start()
                
                # Reset reconnect timeout on successful connection
                self.reconnect_timeout = 1.0
                return True
                
            except Exception as e:
                self.gui.display_message(f"Connection to {server_addr} failed: {e}")
        
        self.gui.display_message("Failed to connect to any server. Will retry...")
        return False

    def _try_reconnect(self):
        """Try to reconnect to a server with exponential backoff."""
        self.gui.display_message(f"Connection lost. Trying to reconnect in {self.reconnect_timeout:.1f} seconds...")
        time.sleep(self.reconnect_timeout)
        
        # Exponential backoff
        self.reconnect_timeout = min(self.reconnect_timeout * 2, self.max_reconnect_timeout)
        
        if self.connect():
            self.gui.display_message("Reconnected to server")
            return True
        return False

    def start(self):
        """Start the client."""
        if self.connect():
            self.gui.start()
        else:
            # If initial connection fails, start UI anyway but keep trying to connect
            threading.Thread(target=self._background_reconnect).start()
            self.gui.start()
    
    def _background_reconnect(self):
        """Background thread that keeps trying to reconnect until successful."""
        while not self.shutdown_flag.is_set():
            if self._try_reconnect():
                break
        
    def _handle_rpc_error(self, method_name, e):
        """Handle RPC errors, attempting reconnection for certain failure types."""
        if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]:
            self.gui.display_message(f"Server connection error: {e.details()}")
            # Start a background thread to reconnect
            threading.Thread(target=self._background_reconnect).start()
        else:
            self.gui.display_message(f"Error in {method_name}: {e.details()}")

    def create_account(self, username: str, password: str):
        """Send create account request."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            response = self.stub.CreateAccount(
                chat_pb2.CreateAccountRequest(username=username, password=password)
            )
            if response.error:
                self.gui.display_message(response.error)
            else:
                self.gui.display_message("Account created successfully, please log in")
        except grpc.RpcError as e:
            self._handle_rpc_error("create_account", e)

    def login(self, username: str, password: str):
        """Send login request."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            response = self.stub.Login(
                chat_pb2.LoginRequest(username=username, password=password)
            )
            if response.error:
                self.gui.display_message(response.error)
            else:
                self.gui.show_main_widgets()
                self._send_initial_requests()
        except grpc.RpcError as e:
            self._handle_rpc_error("login", e)

    def _send_initial_requests(self):
        """Send initial requests after login."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
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
            self._handle_rpc_error("_send_initial_requests", e)

    def logout(self):
        """Send logout request."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            self.stub.Logout(chat_pb2.LogoutRequest())
            # Even if logout fails, return to login screen
            self.gui.show_login_widgets()
        except grpc.RpcError as e:
            self._handle_rpc_error("logout", e)
            # Still return to login screen
            self.gui.show_login_widgets()

    def list_accounts(self, pattern: str, offset: int, limit: int):
        """Send list accounts request."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            response = self.stub.ListUsers(
                chat_pb2.ListUsersRequest(
                    pattern=pattern,
                    offset=offset,
                    limit=limit
                )
            )
            self.gui.display_users(response.usernames)
        except grpc.RpcError as e:
            self._handle_rpc_error("list_accounts", e)

    def send_message(self, recipient_username: str, content: str):
        """Send a message to another user."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            self.stub.SendMessage(
                chat_pb2.SendMessageRequest(
                    receiver=recipient_username,
                    content=content
                )
            )
            self.gui.display_message(f"Message sent to {recipient_username}")
        except grpc.RpcError as e:
            self._handle_rpc_error("send_message", e)

    def pop_unread_messages(self, count: int):
        """Pop unread messages."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            response = self.stub.PopUnreadMessages(
                chat_pb2.PopUnreadMessagesRequest(num_messages=count)
            )
            self.gui.display_messages(response.messages)
            self._send_initial_requests()
        except grpc.RpcError as e:
            self._handle_rpc_error("pop_unread_messages", e)

    def get_read_messages(self, offset: int, limit: int):
        """Get read messages."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            response = self.stub.GetReadMessages(
                chat_pb2.GetReadMessagesRequest(
                    offset=offset,
                    num_messages=limit
                )
            )
            self.gui.display_messages(response.messages)
        except grpc.RpcError as e:
            self._handle_rpc_error("get_read_messages", e)

    def delete_messages(self, message_ids: List[int]):
        """Delete messages."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            self.stub.DeleteMessages(
                chat_pb2.DeleteMessagesRequest(message_ids=message_ids)
            )
            self._send_initial_requests()
            self.gui.update_messages_view()
        except grpc.RpcError as e:
            self._handle_rpc_error("delete_messages", e)

    def delete_account(self):
        """Delete account."""
        try:
            if not self.stub:
                self.gui.display_message("Not connected to server")
                return
                
            self.stub.DeleteAccount(chat_pb2.DeleteAccountRequest())
            self.gui.show_login_widgets()
            self.gui.display_message("Account deleted successfully")
        except grpc.RpcError as e:
            self._handle_rpc_error("delete_account", e)

    def _receive_messages(self):
        """Receive messages from the server."""
        while not self.shutdown_flag.is_set():
            try:
                if not self.stub:
                    time.sleep(1)
                    continue
                    
                for notification in self.stub.SubscribeToMessages(chat_pb2.SubscribeRequest()):
                    if self.shutdown_flag.is_set():
                        break
                        
                    msg = notification.message
                    self.gui.display_message(f"New message from {msg.sender}")
                    self._send_initial_requests()
                    self.gui.update_messages_view()
                
                # If we get here, the stream ended normally
                if not self.shutdown_flag.is_set():
                    # Try to reconnect in the background
                    threading.Thread(target=self._background_reconnect).start()
                    
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED or self.shutdown_flag.is_set():
                    break
                
                # Try to reconnect
                if not self.shutdown_flag.is_set():
                    threading.Thread(target=self._background_reconnect).start()
                    break
