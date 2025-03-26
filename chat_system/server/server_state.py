from typing import Dict, Optional, List, Tuple
import base64
import re
from ..common.security import Security
from ..common.user import User, Message

from ..proto import server_pb2, server_pb2_grpc

class ServerState:
    def __init__(self, server):
        self.server = server

        self.accounts: Dict[str, User] = {}  # username -> User
        self.login_info: Dict[str, Tuple[bytes, bytes]] = {}  # username -> (password hash, salt)
        self.timestamp = 0

    def get_state(self):
        """Save the account manager state to a file."""
        state = {
            "timestamp": self.timestamp,
        }
        users = {}
        for user_id, user in self.accounts.items():
            password_hash, salt = self.login_info[user_id]
            users[user_id] = {
                "password_hash": base64.b64encode(password_hash).decode('ascii'),
                "salt": base64.b64encode(salt).decode('ascii'),
                "message_queue": [(m.id, m.sender, m.content) for m in user.message_queue],
                "read_mailbox": [(m.id, m.sender, m.content) for m in user.read_mailbox]
            }
        state["users"] = users
        return state

    def load_state(self, state: Dict):
        """Load the account manager state from a file."""
        self.accounts.clear()
        self.login_info.clear()

        self.timestamp = state["timestamp"]

        users = state["users"]
        for username, user_state in users.items():
            password_hash = base64.b64decode(user_state["password_hash"].encode('ascii'))
            salt = base64.b64decode(user_state["salt"].encode('ascii'))
            messages = [Message(*m) for m in user_state["message_queue"]]
            received_messages = [Message(*m) for m in user_state["read_mailbox"]]

            user = User(username, messages, received_messages)
            self.accounts[username] = user
            self.login_info[username] = (password_hash, salt)

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by id."""
        return self.accounts.get(user_id)

    def create_account(self, username: str, password: str) -> Optional[str]:
        """Create a new account. Return True if successful."""

        # Check if the username is valid
        if len(username) == 0:
            return "Invalid username"

        # Check if the username is already taken
        if username in self.accounts:
            return "Username already taken"

        # Store new user
        password_hash, salt = Security.hash_password(password)
        self.add_user(username, password_hash, salt)

        return None

    def add_user(self, username: str, password_hash: bytes, salt: bytes):
        """Add a user to the server state."""
        if username in self.accounts:
            return
        self.accounts[username] = User(username, [], [])
        self.login_info[username] = (password_hash, salt)

        self.timestamp += 1
        self.server.broadcast_server_update(
            lambda stub: stub.SyncAddUser(server_pb2.SyncAddUserRequest(
                username=username,
                password=base64.b64encode(password_hash).decode('ascii'),
                salt=base64.b64encode(salt).decode('ascii')
            ))
        )

    def login(self, username: str, password: str) -> Optional[User]:
        """Attempt to log in. Return True if successful."""

        # See if the user exists
        if username not in self.accounts:
            return None

        # Verify password
        password_hash, salt = self.login_info[username]
        if Security.verify_password(password, password_hash, salt):
            return self.accounts[username]
        return None

    def list_accounts(self, pattern: str) -> List[User]:
        """List accounts matching the pattern."""
        regex = re.compile(pattern.replace('*', '.*'))
        return [user for user in self.accounts.values() if regex.match(user.name)]

    def delete_account(self, user_id: str):
        """Delete an account."""
        if user_id not in self.accounts:
            return

        self.accounts.pop(user_id)
        self.login_info.pop(user_id)
        self.timestamp += 1
        self.server.broadcast_server_update(
            lambda stub: stub.SyncDeleteUser(server_pb2.SyncDeleteUserRequest(username=user_id))
        )

    def add_unread_message(self, user_id: str, message: Message):
        """Add messages to the user's message queue."""
        if user_id not in self.accounts:
            return

        self.accounts[user_id]._add_unread_message(message)
        self.timestamp += 1
        self.server.broadcast_server_update(
            lambda stub: stub.SyncAddUnreadMessage(server_pb2.SyncAddMessage(
                user=user_id,
                message=server_pb2.Message(
                    id=message.id,
                    sender=message.sender,
                    content=message.content
                )
            ))
        )

    def add_read_message(self, user_id: str, message: Message):
        """Add messages to the user's read mailbox."""
        if user_id not in self.accounts:
            return

        self.accounts[user_id]._add_read_message(message)
        self.timestamp += 1
        self.server.broadcast_server_update(
            lambda stub: stub.SyncAddReadMessage(server_pb2.SyncAddMessage(
                user=user_id,
                message=server_pb2.Message(
                    id=message.id,
                    sender=message.sender,
                    content=message.content
                )
            ))
        )

    def remove_unread_message(self, user_id: str, message_id: int):
        """Remove messages from the user's message queue."""
        if user_id not in self.accounts:
            return

        for m in self.accounts[user_id].message_queue:
            if m.id == message_id:
                self.accounts[user_id].message_queue.remove(m)
                break
        self.timestamp += 1
        self.server.broadcast_server_update(
            lambda stub: stub.SyncRemoveUnreadMessage(server_pb2.SyncRemoveMessage(
                user=user_id,
                message_id=message_id
            ))
        )

    def remove_read_message(self, user_id: str, message_id: int):
        """Remove messages from the user's read mailbox."""
        if user_id not in self.accounts:
            return

        for m in self.accounts[user_id].read_mailbox:
            if m.id == message_id:
                self.accounts[user_id].read_mailbox.remove(m)
                break
        self.timestamp += 1
        self.server.broadcast_server_update(
            lambda stub: stub.SyncRemoveReadMessage(server_pb2.SyncRemoveMessage(
                user=user_id,
                message_id=message_id
            ))
        )

    def pop_unread_messages(self, user_id: str, num_messages: int) -> List[Message]:
        if user_id not in self.accounts:
            return []

        user = self.accounts[user_id]
        if num_messages < 0:
            messages = user.message_queue.copy()
        else:
            num_messages = min(num_messages, len(user.message_queue))
            messages = user.message_queue[:num_messages].copy()
        for m in messages:
            self.add_read_message(user_id, m)
            self.remove_unread_message(user_id, m.id)
        return messages
