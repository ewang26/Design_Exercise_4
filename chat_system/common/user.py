from dataclasses import dataclass
from typing import List
from queue import Queue

@dataclass
class Message:
    id: int
    sender: str
    content: str

@dataclass
class User:
    name: str
    message_queue: List[Message]
    read_mailbox: List[Message]
    message_subscriber_queue: Queue = Queue()

    def _add_unread_message(self, message: Message):
        self.message_queue.append(message)

    def _add_read_message(self, message: Message):
        self.read_mailbox.append(message)

    def get_number_of_unread_messages(self) -> int:
        return len(self.message_queue)

    def get_number_of_read_messages(self) -> int:
        return len(self.read_mailbox)

    def get_read_messages(self, offset: int, num_messages: int) -> List[Message]:
        n = len(self.read_mailbox)
        # Cap to make sure we stay within bounds
        offset = max(0, min(n, offset))
        num_messages = min(num_messages, n-offset)
        if num_messages < 0:
            return self.read_mailbox[:n-offset]
        else:
            return self.read_mailbox[n-num_messages-offset:n-offset]
