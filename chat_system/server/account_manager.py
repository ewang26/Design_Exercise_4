from typing import Dict, Optional, List, Tuple
import base64
import re
from ..common.security import Security
from ..common.user import User, Message

class AccountManager:
    def __init__(self):
        self.accounts: Dict[str, User] = {}  # username -> User
        self.login_info: Dict[str, Tuple[bytes, bytes]] = {}  # username -> (password hash, salt)

    def get_state(self):
        """Save the account manager state to a file."""
        state = {}
        for user_id, user in self.accounts.items():
            password_hash, salt = self.login_info[user_id]
            state[user_id] = {
                "password_hash": base64.b64encode(password_hash).decode('ascii'),
                "salt": base64.b64encode(salt).decode('ascii'),
                "message_queue": [(m.id, m.sender, m.content) for m in user.message_queue],
                "read_mailbox": [(m.id, m.sender, m.content) for m in user.read_mailbox]
            }
        return state

    def load_state(self, state: Dict):
        """Load the account manager state from a file."""
        self.accounts.clear()
        self.login_info.clear()

        for username, user_state in state.items():
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

        # New user exists, create the account
        new_user = User(username, [], [])

        # Store new user
        password_hash, salt = Security.hash_password(password)
        self.login_info[username] = (password_hash, salt)
        self.accounts[username] = new_user

        return None

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
        self.accounts.pop(user_id)
        self.login_info.pop(user_id)
