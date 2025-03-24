# Client-Server Architecture

## Overview

We want to build a client-server chat application, where **multiple clients** connect over sockets to the server. Each client can either create or log into an account, so messages from each client will be tied to **one user** at a time.

A user can do the following tasks:
- Provide a wildcard pattern and get a list of users matching it
  - Potentially do pagination, if there are a lot of users that match
- Send a message to a single user
- Pop messages from an unread message queue.
  - User can specify how many messages to pop
- Read all received messages
  - Again may need to do pagination
- Delete a (set of) message(s)
- Delete an account
  - Any delivered messages from this user should not be deleted

Additionally, if a user is currently logged in and they receive a message, the server should notify the client. This way, the client can pop the message from the unread queue.

## Server state
At a high level, the server should maintain a list of `User`s. Each user then has an `message_queue` and `read_mailbox` of `Message`s. Sending messages to a user will add a message to their `message_queue`, and the user can then pop messages from this queue. When a user pops a message, it should be moved to their `read_mailbox`.

Since we require users to have unique usernames, we can use the username as the unique identifier for each user.

Concretely, we should have
```python
class User:
    name: str
    message_queue: List[Message]
    read_mailbox: List[Message]

class Message:
    id: int
    sender: str
    content: str
```

When a client logs in, the server should map the client's socket to its user id. This way, the client doesn't need to send its user id with every request.

Note that because many clients can be connected at once (potentially with one user on multiple clients as well), there may be concurrent accesses to the server state. We can either use a lock to protect the state, or have the server be single-threaded and use a queue to handle requests. **We chose the second option for simplicity, because we don't expect a high load on the server.**

## Client state

The client does not need to cache much state. Since the server keeps track of what accounts are logged in and what messages are sent, the client can just keep track of the messages it has received.

Since messages have a unique id that is purely incrementing, we can order messages by their id. This way, the client can display all messages in chronological order.

## Interfaces

`CreateAccount(name: str, password: str) -> Optional[str]`:

`Login(name: str, password: str) -> Optional[str]`:

`ListUsers(pattern: str, offset: int, limit: int) -> List[str]`:
- Takes in a wildcard pattern and returns a list of users that match the pattern. The `offset` and `limit` parameters are for pagination. `limit` can be `-1` to return all users after `offset`.

`SendMessage(receiver: str, content: str) -> None`:

`ReceivedMessage(new_message: Message) -> None`:
- Sent from the server to the client, whenever the client receives a new message.

`GetNumberOfUnreadMessages() -> int`:

`GetNumberOfReadMessages() -> int`:

`PopUnreadMessages(num_messages: int) -> List[Message]`:
- Pops the first `num_messages` messages from the unread queue. Can pass `-1` to pop all messages.

`GetReadMessages(offset: int, num_messages: int) -> List[Message]`:

`DeleteMessages(message_ids: List[int]) -> None`:

`DeleteAccount() -> None`:

## Wire Protocol

For our custom protocol, we can use the fact that each interface has a constant type for fields and return values. When a client is calling an interface, it will first send a 1-byte request type, followed by the arguments for the interface. The server will then respond with the return value. This return value should be typed as well, since the client cannot easily pair requests with responses due to multithreading.

The arguments and return values are encoded into bytes as follows:
- `str`: 4-byte length, followed by the string
- `int`: 4-byte integer
- `List[...]`: 4-byte length, followed by the encoded elements
- `Tuple[...]`: sequentially encode the elements
- `Optional[...]`: 1-byte integer, either a 0 for None or 1 for Some. If it is Some, then follow by encoding the value.
- `bool`: 1-byte integer, 0 for False, 1 for True
- `Message`: sequentially encode `id`, `sender`, and `content`.

