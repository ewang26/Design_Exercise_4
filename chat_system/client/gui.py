import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Callable, List

from chat_system.common.user import Message


class ChatGUI:
    def __init__(self,
                 on_login: Callable[[str, str], None],
                 on_logout: Callable[[], None],
                 on_create_account: Callable[[str, str], None],
                 on_send_message: Callable[[str, str], None],
                 on_list_accounts: Callable[[str, int, int], None],
                 on_delete_messages: Callable[[List[int]], None],
                 on_delete_account: Callable[[], None],
                 get_read_messages: Callable[[int, int], None],
                 on_pop_messages: Callable[[int], None]):

        self.root = tk.Tk()
        self.root.title("Chat Client")
        self.root_frame = ttk.Frame(self.root)

        # Store callbacks
        self.on_login = on_login
        self.on_logout = on_logout
        self.on_create_account = on_create_account
        self.on_send_message = on_send_message
        self.on_list_accounts = on_list_accounts
        self.on_delete_messages = on_delete_messages
        self.on_delete_account = on_delete_account
        self.get_read_messages = get_read_messages
        self.on_pop_messages = on_pop_messages

        # State variables
        self.current_page = 0
        self.page_size = 10
        self.total_messages = 0
        self.selected_messages = set()

        self.show_login_widgets()

    def show_login_widgets(self):
        # Clear current window
        self.root_frame.destroy()
        self.root_frame = ttk.Frame(self.root)

        self.login_frame = ttk.LabelFrame(self.root_frame, text="Login/Create Account")
        self.login_frame.pack(padx=10, pady=5, fill=tk.X)

        ttk.Label(self.login_frame, text="Username:").grid(row=0, column=0, padx=5, pady=5)
        self.username_entry = ttk.Entry(self.login_frame)
        self.username_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(self.login_frame, text="Password:").grid(row=1, column=0, padx=5, pady=5)
        self.password_entry = ttk.Entry(self.login_frame, show="*")
        self.password_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(self.login_frame, text="Login",
                   command=self._handle_login).grid(row=2, column=0, padx=5, pady=5)
        ttk.Button(self.login_frame, text="Create Account",
                   command=self._handle_create_account).grid(row=2, column=1, padx=5, pady=5)

        # Add frame once we're done constructing
        self.root_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

    def show_main_widgets(self):
        # Clear current window
        self.root_frame.destroy()
        self.root_frame = ttk.Frame(self.root)

        # Unread messages frame
        self.unread_frame = ttk.LabelFrame(self.root_frame, text="Unread Messages")
        self.unread_frame.pack(padx=10, pady=5, fill=tk.X)

        self.unread_label = ttk.Label(self.unread_frame, text="Unread messages: 0")
        self.unread_label.pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(self.unread_frame, text="Pop Messages",
                  command=self._handle_pop_messages).pack(side=tk.RIGHT, padx=5, pady=5)
        self.pop_count = ttk.Spinbox(self.unread_frame, from_=1, to=100, width=5)
        self.pop_count.pack(side=tk.RIGHT, padx=5, pady=5)

        # Message list frame
        self.message_frame = ttk.LabelFrame(self.root_frame, text="Messages")
        self.message_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Treeview for messages
        columns = ("id", "sender", "content")
        self.message_tree = ttk.Treeview(self.message_frame, columns=columns, show="headings")
        self.message_tree.heading("id", text="ID")
        self.message_tree.heading("sender", text="From")
        self.message_tree.heading("content", text="Message")
        self.message_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.message_tree.bind("<<TreeviewSelect>>", self._on_message_select)

        # Message controls
        self.message_controls = ttk.Frame(self.message_frame)
        self.message_controls.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(self.message_controls, text="Delete Selected",
                   command=self._handle_delete_messages).pack(side=tk.LEFT, padx=5)

        ttk.Button(self.message_controls, text=">", width=3,
                   command=self._handle_view_page_right).pack(side=tk.RIGHT, padx=5)
        self.read_label = ttk.Label(self.message_controls, text=self._get_view_history_text())
        self.read_label.pack(side=tk.RIGHT, padx=5, pady=5)
        ttk.Button(self.message_controls, text="<", width=3,
                   command=self._handle_view_page_left).pack(side=tk.RIGHT, padx=5)


        # Send message frame
        self.send_frame = ttk.LabelFrame(self.root_frame, text="Send Message")
        self.send_frame.pack(padx=10, pady=5, fill=tk.X)

        ttk.Label(self.send_frame, text="To:").pack(side=tk.LEFT, padx=5)
        self.recipient_entry = ttk.Entry(self.send_frame, width=20)
        self.recipient_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(self.send_frame, text="Message:").pack(side=tk.LEFT, padx=5)
        self.message_entry = ttk.Entry(self.send_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Button(self.send_frame, text="Send",
                  command=self._handle_send).pack(side=tk.RIGHT, padx=5)

        # User list frame
        self.user_frame = ttk.LabelFrame(self.root_frame, text="User List")
        self.user_frame.pack(padx=10, pady=5, fill=tk.X)

        ttk.Label(self.user_frame, text="Pattern:").pack(side=tk.LEFT, padx=5)
        self.pattern_entry = ttk.Entry(self.user_frame)
        self.pattern_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Button(self.user_frame, text="Search",
                  command=self._handle_list_users).pack(side=tk.RIGHT, padx=5)

        # Account management
        self.account_frame = ttk.Frame(self.root_frame)
        self.account_frame.pack(padx=10, pady=5, fill=tk.X)

        ttk.Button(self.account_frame, text="Delete Account",
                  command=self._handle_delete_account).pack(side=tk.RIGHT, padx=5)
        ttk.Button(self.account_frame, text="Logout",
                   command=self._handle_logout).pack(side=tk.RIGHT, padx=5)

        # Add frame once we're done constructing
        self.root_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

    def _handle_login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        if username and password:
            self.on_login(username, password)

    def _handle_logout(self):
        if messagebox.askyesno("Confirm Logout", "Are you sure you want to logout?"):
            self.on_logout()
            self.show_login_widgets()

    def _handle_create_account(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        if username and password:
            self.on_create_account(username, password)

    def _handle_send(self):
        recipient = self.recipient_entry.get()
        message = self.message_entry.get()
        if recipient and message:
            self.on_send_message(recipient, message)
            self.message_entry.delete(0, tk.END)

    def _handle_list_users(self):
        pattern = self.pattern_entry.get() or "*"
        self.on_list_accounts(pattern, self.current_page * self.page_size, self.page_size)

    def _handle_delete_messages(self):
        if self.selected_messages:
            self.on_delete_messages(list(self.selected_messages))
            self.selected_messages.clear()

    def _handle_view_page_left(self):
        self.current_page = max(0, self.current_page - 1)
        self.update_messages_view()

    def _handle_view_page_right(self):
        self.current_page = min(self.total_messages // self.page_size, self.current_page + 1)
        self.update_messages_view()

    def _handle_delete_account(self):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete your account?"):
            self.on_delete_account()
            self.show_login_widgets()

    def _handle_pop_messages(self):
        try:
            count = int(self.pop_count.get())
            self.on_pop_messages(count)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number")

    def _on_message_select(self, event):
        selection = self.message_tree.selection()
        self.selected_messages = {int(self.message_tree.item(item)["values"][0]) for item in selection}

    def _get_view_history_text(self):
        start = self.current_page * self.page_size
        end = min(self.total_messages, start + self.page_size)
        print(f"Viewing {start} - {end} of {self.total_messages}")
        return f"Viewing {start} - {end} of {self.total_messages}"

    def display_message(self, message: str):
        """Display a system message."""
        messagebox.showinfo("Message", message)

    def update_unread_count(self, count: int):
        """Update the unread message count display."""
        self.unread_label.config(text=f"Unread messages: {count}")

    def update_read_count(self, count: int):
        """Update the unread message count display."""
        self.total_messages = count
        self.read_label.config(text=self._get_view_history_text())

    def update_messages_view(self):
        self.read_label.config(text=self._get_view_history_text())
        self.get_read_messages(self.current_page * self.page_size, self.page_size)

    def display_messages(self, messages: List[Message]):
        """Display messages in the message tree."""
        self.message_tree.delete(*self.message_tree.get_children())
        # Sort messages by decreasing id
        messages.sort(key=lambda x: x.id, reverse=True)
        for msg in messages:
            self.message_tree.insert("", tk.END, values=(msg.id, msg.sender, msg.content))

    def display_users(self, users: List[str]):
        """Display the list of users in a popup window."""
        dialog = tk.Toplevel(self.root)
        dialog.title("User List")

        tree = ttk.Treeview(dialog, columns="name", show="headings")
        tree.heading("name", text="Username")
        tree.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        for username in users:
            tree.insert("", tk.END, values=username)

    def start(self):
        """Start the GUI main loop."""
        self.root.mainloop()
