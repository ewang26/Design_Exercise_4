import unittest
from chat_system.server.account_manager import AccountManager
from chat_system.common.user import Message

class TestAccountManager(unittest.TestCase):
    def setUp(self):
        self.account_manager = AccountManager()

    def test_create_account(self):
        """Test account creation."""
        # Test successful creation
        self.assertIsNone(self.account_manager.create_account("test", "password"))

        # Test duplicate username
        self.assertIsNotNone(self.account_manager.create_account("test", "different"))

        # Test bad username
        self.assertIsNotNone(self.account_manager.create_account("", "different"))

    def test_unique_ids(self):
        """Test that user ids are unique."""
        ids = set()
        for i in range(10):
            self.account_manager.create_account(str(i), "password")
            user_id = self.account_manager.login(str(i), "password").name
            self.assertNotIn(user_id, ids)
            ids.add(user_id)

    def test_login(self):
        """Test login functionality."""
        username = "test"
        password = "password"

        # Create account first
        self.account_manager.create_account(username, password)

        # Test successful login
        self.assertIsNotNone(self.account_manager.login(username, password))

        # Test wrong password
        self.assertIsNone(self.account_manager.login(username, "wrong"))

        # Test non-existent user
        self.assertIsNone(self.account_manager.login("nonexistent", password))

    def test_list_accounts(self):
        """Test account listing with patterns."""
        # Create test accounts
        accounts = ["test1", "test2", "other1", "other2"]
        for acc in accounts:
            self.account_manager.create_account(acc, "password")

        # Test listing all accounts
        users = self.account_manager.list_accounts("*")
        self.assertEqual(set([user.name for user in users]), set(accounts))

        # Test pattern matching
        test_accounts = self.account_manager.list_accounts("test*")
        self.assertEqual(set([acc.name for acc in test_accounts]), {"test1", "test2"})

    def test_password_security(self):
        """Test password security features."""
        # Test empty password
        self.account_manager.create_account("empty", "")
        self.assertIsNotNone(self.account_manager.login("empty", ""))
        self.assertIsNone(self.account_manager.login("empty", "wrong"))

        # Test long password
        long_pass = "a" * 1000
        self.account_manager.create_account("long", long_pass)
        self.assertIsNotNone(self.account_manager.login("long", long_pass))
        self.assertIsNone(self.account_manager.login("long", "wrong"))

        # Test similar passwords produce different security data
        self.account_manager.create_account("user1", "password123")
        self.account_manager.create_account("user2", "password123")

        # Get the stored password hashes
        user1 = self.account_manager.login("user1", "password123")
        user2 = self.account_manager.login("user2", "password123")

        hash1, salt1 = self.account_manager.login_info[user1.name]
        hash2, salt2 = self.account_manager.login_info[user2.name]

        # Same password should have different salts and hashes
        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(hash1, hash2)

    def test_message_ordering(self):
        """Test that messages maintain correct ordering."""
        self.account_manager.create_account("sender", "pass")
        self.account_manager.create_account("receiver", "pass")

        sender = self.account_manager.login("sender", "pass")
        receiver = self.account_manager.login("receiver", "pass")

        # Send messages in specific order
        messages = ["first", "second", "third"]
        for msg in messages:
            receiver.add_message(Message(0, sender.name, msg))

        # Check order in unread queue
        queue = receiver.message_queue
        for i, msg in enumerate(messages):
            self.assertEqual(queue[i].content, msg)

        # Check order maintained after popping
        popped = receiver.pop_unread_messages(-1)
        for i, msg in enumerate(messages):
            self.assertEqual(popped[i].content, msg)
            self.assertEqual(receiver.read_mailbox[i].content, msg)

    def test_password_character_handling(self):
        """Test that the system properly handles various types of password characters."""
        test_cases = [
            ("normal", "simple123"),           # Basic alphanumeric
            ("spaces", "pass word space"),     # Spaces in password
            ("symbols", "!@#$%^&*()_+-="),    # Special characters
            ("unicode", "パスワード123"),       # Unicode characters
            ("emoji", "password🔑🎮"),         # Emojis
            ("very_long", "a" * 100),         # Long password
            ("very_short", "a"),              # Single character
        ]

        for username, password in test_cases:
            # Should be able to create account
            error = self.account_manager.create_account(username, password)
            self.assertIsNone(error, f"Failed to create account with password type: {username}")

            # Should be able to login with exact password
            user = self.account_manager.login(username, password)
            self.assertIsNotNone(user, f"Failed to login with password type: {username}")

            # Wrong password should fail
            self.assertIsNone(
                self.account_manager.login(username, password + "wrong"),
                f"Login succeeded with wrong password for type: {username}"
            )

    def test_message_deletion_edge_cases(self):
        """Test edge cases for message deletion."""
        self.account_manager.create_account("user", "pass")
        user = self.account_manager.login("user", "pass")

        # Try deleting non-existent messages
        user.delete_messages([1, 2, 3])
        self.assertEqual(len(user.read_mailbox), 0)

        # Add and delete messages
        user.add_read_message(Message(1, 0, "test"))
        user.delete_messages([1])
        self.assertEqual(len(user.read_mailbox), 0)

        # Try deleting same message multiple times
        user.add_read_message(Message(2, 0, "test"))
        user.delete_messages([2, 2, 2])
        self.assertEqual(len(user.read_mailbox), 0)

