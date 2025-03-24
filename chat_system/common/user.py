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

    def add_message(self, message: Message):
        self.message_queue.append(message)

    def add_read_message(self, message: Message):
        self.read_mailbox.append(message)

    def pop_unread_messages(self, num_messages: int) -> List[Message]:
        if num_messages < 0:
            messages = self.message_queue
            self.message_queue = []
        else:
            num_messages = min(num_messages, len(self.message_queue))
            messages = self.message_queue[:num_messages]
            self.message_queue = self.message_queue[num_messages:]
        self.read_mailbox.extend(messages)
        return messages

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

    def delete_messages(self, message_ids: List[int]):
        for id in message_ids:
            for message in self.read_mailbox:
                if message.id == id:
                    self.read_mailbox.remove(message)
                    break
