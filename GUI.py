import json
import socket
import threading
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox, simpledialog, scrolledtext
from time import sleep
from network import send_message

class BlockchainGUI:
    def __init__(self, root, blockchain, node_identifier, args):
        self.root = root
        self.blockchain = blockchain
        self.node_identifier = node_identifier
        self.args = args

        ip = args.host
        root.title(f"Blockchain Node: {ip}:{args.port}")

        style = ttk.Style()
        style.theme_use('clam')

        # Header Frame
        header_frame = ttk.Frame(root, padding="10")
        header_frame.pack(side=tk.TOP, fill=tk.X)
        header_label = ttk.Label(header_frame, text=f"Blockchain Node Interface - {ip}:{args.port}", font=("Helvetica", 16))
        header_label.pack(side=tk.LEFT)
        
        # Leader Status Label
        self.leader_var = tk.StringVar()
        self.leader_var.set("Leader: Unknown")
        leader_label = ttk.Label(header_frame, textvariable=self.leader_var, font=("Helvetica", 12))
        leader_label.pack(side=tk.RIGHT)

        # Main Notebook for Tabs
        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Overview Tab
        self.overview_tab = ttk.Frame(notebook)
        notebook.add(self.overview_tab, text="Overview")
        self.log_text = scrolledtext.ScrolledText(self.overview_tab, wrap=tk.WORD, height=20)
        self.log_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        clear_btn = ttk.Button(self.overview_tab, text="Clear Log", command=self.clear_log)
        clear_btn.pack(pady=(0,10))

        # Pending Transactions Tab
        self.pending_transactions_tab = ttk.Frame(notebook)
        notebook.add(self.pending_transactions_tab, text="Pending Transactions")
        pending_btn_frame = ttk.Frame(self.pending_transactions_tab)
        pending_btn_frame.pack(padx=10, pady=5, fill=tk.X)
        new_tx_btn = ttk.Button(pending_btn_frame, text="New Transaction", command=self.new_transaction)
        new_tx_btn.pack(side=tk.LEFT, padx=5)
        refresh_pending_btn = ttk.Button(pending_btn_frame, text="Refresh", command=self.refresh_pending_transactions)
        refresh_pending_btn.pack(side=tk.LEFT, padx=5)
        pending_tx_frame = ttk.Frame(self.pending_transactions_tab)
        pending_tx_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.pending_tx_tree = ttk.Treeview(pending_tx_frame, columns=("Sender", "Recipient", "Amount", "Status", "Block"), show="headings")
        for col in ("Sender", "Recipient", "Amount", "Status", "Block"):
            self.pending_tx_tree.heading(col, text=col)
        self.pending_tx_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pending_tx_scroll = ttk.Scrollbar(pending_tx_frame, orient="vertical", command=self.pending_tx_tree.yview)
        self.pending_tx_tree.configure(yscrollcommand=pending_tx_scroll.set)
        pending_tx_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Success Transactions Tab
        self.success_transactions_tab = ttk.Frame(notebook)
        notebook.add(self.success_transactions_tab, text="Success Transactions")
        success_tx_frame = ttk.Frame(self.success_transactions_tab)
        success_tx_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.success_tx_tree = ttk.Treeview(success_tx_frame, columns=("Sender", "Recipient", "Amount", "Status", "Block"), show="headings")
        for col in ("Sender", "Recipient", "Amount", "Status", "Block"):
            self.success_tx_tree.heading(col, text=col)
        self.success_tx_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        success_tx_scroll = ttk.Scrollbar(success_tx_frame, orient="vertical", command=self.success_tx_tree.yview)
        self.success_tx_tree.configure(yscrollcommand=success_tx_scroll.set)
        success_tx_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        refresh_success_btn = ttk.Button(self.success_transactions_tab, text="Refresh", command=self.refresh_success_transactions)
        refresh_success_btn.pack(pady=(0,10))

        # Mining Tab
        self.mining_tab = ttk.Frame(notebook)
        notebook.add(self.mining_tab, text="Mining")
        mine_btn = ttk.Button(self.mining_tab, text="Mine New Block", command=self.mine_block)
        mine_btn.pack(pady=10)
        self.block_info_text = scrolledtext.ScrolledText(self.mining_tab, wrap=tk.WORD, height=10)
        self.block_info_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Network Tab
        self.network_tab = ttk.Frame(notebook)
        notebook.add(self.network_tab, text="Network")
        net_frame = ttk.Frame(self.network_tab)
        net_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.nodes_tree = ttk.Treeview(net_frame, columns=("Node",), show="headings")
        self.nodes_tree.heading("Node", text="Node Address")
        self.nodes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        net_scroll = ttk.Scrollbar(net_frame, orient="vertical", command=self.nodes_tree.yview)
        self.nodes_tree.configure(yscrollcommand=net_scroll.set)
        net_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        net_btn_frame = ttk.Frame(self.network_tab)
        net_btn_frame.pack(pady=(0,10))
        register_btn = ttk.Button(net_btn_frame, text="Register Node", command=self.register_node)
        register_btn.pack(side=tk.LEFT, padx=5)
        refresh_net_btn = ttk.Button(net_btn_frame, text="Refresh Nodes", command=self.refresh_nodes)
        refresh_net_btn.pack(side=tk.LEFT, padx=5)
        resolve_btn = ttk.Button(net_btn_frame, text="Resolve Conflicts", command=self.resolve_conflicts)
        resolve_btn.pack(side=tk.LEFT, padx=5)

        # Ledger Tab
        self.ledger_tab = ttk.Frame(notebook)
        notebook.add(self.ledger_tab, text="Ledger")
        ledger_frame = ttk.Frame(self.ledger_tab)
        ledger_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.ledger_text = scrolledtext.ScrolledText(ledger_frame, wrap=tk.WORD)
        self.ledger_text.pack(fill=tk.BOTH, expand=True)
        refresh_ledger_btn = ttk.Button(self.ledger_tab, text="Refresh Ledger", command=self.refresh_ledger)
        refresh_ledger_btn.pack(pady=(0,10))

        # Status Bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Initial refreshes
        self.refresh_pending_transactions()
        self.refresh_success_transactions()
        self.refresh_nodes()
        self.refresh_ledger()
        self.log("Interface initialized.")

        # Start periodic update of leader status.
        self.update_leader_status()

    def update_leader_status(self):
        current_leader = self.blockchain.current_leader if self.blockchain.current_leader is not None else "Unknown"
        self.leader_var.set(f"Leader: {current_leader}")
        self.root.after(5000, self.update_leader_status)

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.status_var.set(message)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def new_transaction(self):
        popup = tk.Toplevel(self.root)
        popup.title("New Transaction")
        ttk.Label(popup, text="Sender:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(popup, text="Recipient:").grid(row=1, column=0, padx=5, pady=5)
        ttk.Label(popup, text="Amount:").grid(row=2, column=0, padx=5, pady=5)
        entry_sender = ttk.Entry(popup)
        entry_sender.grid(row=0, column=1, padx=5, pady=5)
        entry_recipient = ttk.Entry(popup)
        entry_recipient.grid(row=1, column=1, padx=5, pady=5)
        entry_amount = ttk.Entry(popup)
        entry_amount.grid(row=2, column=1, padx=5, pady=5)

        def submit():
            sender = entry_sender.get().strip()
            recipient = entry_recipient.get().strip()
            try:
                amount = float(entry_amount.get().strip())
            except ValueError:
                messagebox.showerror("Error", "Invalid amount. Please enter a number.")
                return
            index = self.blockchain.new_transaction(sender, recipient, amount, auto_broadcast=True)
            self.log(f"Transaction will be added to Block {index}")
            popup.destroy()
            self.refresh_pending_transactions()
        submit_btn = ttk.Button(popup, text="Submit", command=submit)
        submit_btn.grid(row=3, column=0, columnspan=2, pady=10)

    def refresh_pending_transactions(self):
        for item in self.pending_tx_tree.get_children():
            self.pending_tx_tree.delete(item)
        for tx in self.blockchain.current_transactions:
            if tx.get("status", "pending") == "pending":
                self.pending_tx_tree.insert("", tk.END, values=(
                    tx.get("sender", ""),
                    tx.get("recipient", ""),
                    tx.get("amount", ""),
                    tx.get("status", "pending"),
                    "Pending"
                ))

    def refresh_success_transactions(self):
        for item in self.success_tx_tree.get_children():
            self.success_tx_tree.delete(item)
        for block in self.blockchain.chain[1:]:
            for tx in block['transactions']:
                if tx.get("status") == "success":
                    self.success_tx_tree.insert("", tk.END, values=(
                        tx.get("sender", ""),
                        tx.get("recipient", ""),
                        tx.get("amount", ""),
                        tx.get("status", ""),
                        block.get("index", "")
                    ))

    def mine_block(self):
        def task():
            if self.blockchain.current_leader != self.blockchain.node_address:
                self.log("You are not the leader, so you cannot mine a block.")
                return

            if not self.blockchain.current_transactions:
                self.log("No transactions available to mine. Add a transaction first.")
                return

            self.log("Mining a new block...")

            last_block = self.blockchain.last_block
            last_nonce = last_block['nonce']
            nonce = self.blockchain.proof_of_work(last_nonce)
            previous_hash = self.blockchain.hash(last_block)
            block = self.blockchain.new_block(nonce, previous_hash, auto_broadcast=True)

            if block:
                self.log("New Block Forged and committed via consensus.")
                self.block_info_text.delete("1.0", tk.END)
                self.block_info_text.insert(tk.END, json.dumps(block, indent=4))
            else:
                self.log("Block proposal failed consensus. Please try again.")

            self.refresh_pending_transactions()
            self.refresh_success_transactions()
            self.refresh_ledger()

        threading.Thread(target=task, daemon=True).start()

    def refresh_nodes(self):
        for item in self.nodes_tree.get_children():
            self.nodes_tree.delete(item)
        for node in self.blockchain.nodes:
            self.nodes_tree.insert("", tk.END, values=(node,))

    def register_node(self):
        address = simpledialog.askstring("Register Node", "Enter node address (host:port):", parent=self.root)
        if address:
            try:
                self.blockchain.register_node(address)
                self.log("Node registered locally!")
                response = send_message(address, {"type": "REGISTER_NODE", "node": f"{self.args.host}:{self.args.port}"}, expect_response=True)
                if response:
                    self.log(f"Response from {address}: {response.get('message')}")
                pending_response = send_message(address, {"type": "GET_PENDING"}, expect_response=True)
                if pending_response and pending_response.get("type") == "PENDING":
                    pending_from_peer = pending_response.get("pending", [])
                    for tx in pending_from_peer:
                        tx_str = json.dumps(tx, sort_keys=True)
                        local_tx_strs = [json.dumps(local_tx, sort_keys=True) for local_tx in self.blockchain.current_transactions]
                        if tx_str not in local_tx_strs:
                            self.blockchain.current_transactions.append(tx)
                    self.refresh_pending_transactions()
                else:
                    self.log(f"No pending transactions received from {address}.")
                self.refresh_nodes()
            except ValueError as e:
                messagebox.showerror("Error", str(e))

    def resolve_conflicts(self):
        self.log("Resolving conflicts by querying peers...")
        replaced = self.blockchain.resolve_conflicts()
        if replaced:
            self.log("Our chain was replaced by a longer valid chain.")
        else:
            self.log("Our chain remains authoritative.")
        self.refresh_pending_transactions()
        self.refresh_success_transactions()
        self.refresh_ledger()

    def refresh_ledger(self):
        self.ledger_text.delete("1.0", tk.END)
        ledger_content = (
            "Confirmed Blockchain:\n" + json.dumps(self.blockchain.chain, indent=4) +
            "\n\nPending Transactions:\n" + json.dumps(self.blockchain.current_transactions, indent=4)
        )
        self.ledger_text.insert(tk.END, ledger_content)
