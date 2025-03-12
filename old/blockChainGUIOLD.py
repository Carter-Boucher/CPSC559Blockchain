import hashlib
import json
import socket
import threading
from time import time, sleep
from uuid import uuid4
import argparse
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox, simpledialog, scrolledtext

# -----------------------------
# Utility Functions
# -----------------------------
def canonical_transaction(tx):
    """Return a canonical JSON representation of a transaction, ignoring the 'status' field."""
    return json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True)

# -----------------------------
# Blockchain and Block Classes
# -----------------------------
class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()
        self.seen_transactions = set()
        self.seen_blocks = set()
        
        # Create and append the fixed genesis block.
        genesis_block = self.create_genesis_block()
        self.chain.append(genesis_block)
        self.seen_blocks.add(self.hash(genesis_block))

    def create_genesis_block(self):
        genesis_block = {
            'index': 1,
            'timestamp': 1234567890,  # a fixed timestamp
            'transactions': [],
            'nonce': 100,
            'previous_hash': '1'
        }
        return genesis_block

    def register_node(self, address):
        """
        Add a new node to the list of nodes.
        :param address: Address of node, e.g., "127.0.0.1:5001"
        """
        if ":" not in address:
            raise ValueError("Address must be in host:port format")
        self.nodes.add(address)

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid.
        :param chain: A blockchain (list of blocks)
        :return: True if valid, False otherwise.
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            if block['previous_hash'] != self.hash(last_block):
                return False
            if not self.valid_proof(last_block['nonce'], block['nonce'], self.hash(last_block)):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        Consensus Algorithm:
        Replaces our chain with the longest valid chain in the network.
        :return: True if chain was replaced, False otherwise.
        """
        neighbours = self.nodes
        new_chain = None
        max_length = len(self.chain)

        for node in neighbours:
            response = send_message(node, {"type": "GET_CHAIN"}, expect_response=True)
            if response and response.get("type") == "CHAIN":
                chain = response.get("chain")
                if chain and len(chain) > max_length and self.valid_chain(chain):
                    max_length = len(chain)
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            print("Our chain was replaced by a longer valid chain from peers.")
            return True

        print("Our chain is authoritative.")
        return False

    def new_block(self, nonce, previous_hash=None, auto_broadcast=True):
        """
        Create a new Block in the Blockchain.
        Before creating the block, update pending transactions to 'success'.
        :param nonce: The proof provided by Proof of Work.
        :param previous_hash: Hash of previous Block.
        :param auto_broadcast: Whether to broadcast this block.
        :return: New Block, or None if no transactions available.
        """
        # Only mine a block if there is at least one pending transaction.
        if not self.current_transactions:
            print("Cannot mine a block with no transactions.")
            return None

        # Mark transactions as successful.
        for tx in self.current_transactions:
            tx['status'] = 'success'

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'nonce': nonce,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        self.chain.append(block)
        self.current_transactions = []

        block_hash = self.hash(block)
        if block_hash not in self.seen_blocks:
            self.seen_blocks.add(block_hash)
            if auto_broadcast:
                broadcast_message(self, {"type": "NEW_BLOCK", "block": block})

        return block

    def new_transaction(self, sender, recipient, amount, auto_broadcast=True):
        """
        Creates a new transaction with an initial status of 'pending'.
        Transactions from sender "0" are not allowed.
        :param sender: Sender address.
        :param recipient: Recipient address.
        :param amount: Amount.
        :param auto_broadcast: Whether to broadcast the transaction.
        :return: The block index that will hold this transaction.
        """
        # Remove transactions from sender "0"
        if sender == "0":
            print("Ignoring transaction from sender '0'.")
            return self.last_block['index'] + 1

        transaction = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'status': 'pending'
        }
        tx_str = json.dumps(transaction, sort_keys=True)
        if tx_str in self.seen_transactions:
            return self.last_block['index'] + 1

        self.current_transactions.append(transaction)
        self.seen_transactions.add(tx_str)

        if auto_broadcast:
            broadcast_message(self, {"type": "NEW_TRANSACTION", "transaction": transaction})

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_nonce):
        nonce = 0
        last_hash = self.hash(self.last_block)
        while not self.valid_proof(last_nonce, nonce, last_hash):
            nonce += 1
        return nonce

    @staticmethod
    def valid_proof(last_nonce, nonce, last_hash):
        guess = f'{last_nonce}{nonce}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

# -----------------------------
# Peer-to-Peer Networking (Sockets)
# -----------------------------
def send_message(peer_address, message, expect_response=False):
    try:
        host, port_str = peer_address.split(":")
        port = int(port_str)
        with socket.create_connection((host, port), timeout=5) as s:
            s.sendall((json.dumps(message) + "\n").encode())
            if expect_response:
                file = s.makefile()
                response_line = file.readline()
                if response_line:
                    return json.loads(response_line)
    except Exception as e:
        print(f"Error sending message to {peer_address}: {e}")
    return None

def handle_client_connection(conn, addr, blockchain, node_identifier):
    try:
        file = conn.makefile(mode="rwb")
        line = file.readline()
        if not line:
            return
        message = json.loads(line.decode())
        msg_type = message.get("type")
        response = {}
        if msg_type == "GET_CHAIN":
            response = {"type": "CHAIN", "chain": blockchain.chain}
        elif msg_type == "REGISTER_NODE":
            new_node = message.get("node")
            if new_node:
                try:
                    blockchain.register_node(new_node)
                    response = {"status": "OK", "message": f"Node {new_node} registered."}
                except ValueError as e:
                    response = {"status": "Error", "message": str(e)}
            else:
                response = {"status": "Error", "message": "No node provided."}
        elif msg_type == "NEW_TRANSACTION":
            transaction = message.get("transaction")
            if not transaction:
                sender = message.get("sender")
                recipient = message.get("recipient")
                amount = message.get("amount")
                if sender and recipient and amount is not None:
                    blockchain.new_transaction(sender, recipient, amount)
                    response = {"status": "OK", "message": "Transaction will be added."}
                else:
                    response = {"status": "Error", "message": "Missing transaction fields."}
            else:
                sender = transaction.get("sender")
                recipient = transaction.get("recipient")
                amount = transaction.get("amount")
                if sender and recipient and amount is not None:
                    blockchain.new_transaction(sender, recipient, amount)
                    response = {"status": "OK", "message": "Transaction will be added."}
                else:
                    response = {"status": "Error", "message": "Invalid transaction data."}
        elif msg_type == "NEW_BLOCK":
            block = message.get("block")
            if block:
                last_block = blockchain.last_block
                if block.get("index") == last_block["index"] + 1 and block.get("previous_hash") == blockchain.hash(last_block):
                    blockchain.chain.append(block)
                    block_tx_set = set(canonical_transaction(tx) for tx in block.get("transactions", []))
                    blockchain.current_transactions = [
                        tx for tx in blockchain.current_transactions 
                        if canonical_transaction(tx) not in block_tx_set
                    ]
                    block_hash = blockchain.hash(block)
                    if block_hash not in blockchain.seen_blocks:
                        blockchain.seen_blocks.add(block_hash)
                        broadcast_message(blockchain, {"type": "NEW_BLOCK", "block": block})
                    response = {"status": "OK", "message": "Block accepted and pending transactions synced."}
                elif block.get("index") > last_block["index"] + 1:
                    print("Block index indicates our chain might be behind. Resolving conflicts...")
                    blockchain.resolve_conflicts()
                    response = {"status": "OK", "message": "Chain synchronized with peers."}
                else:
                    response = {"status": "Error", "message": "Invalid block."}
            else:
                response = {"status": "Error", "message": "No block provided."}
        elif msg_type == "GET_NODES":
            response = {"type": "NODES", "nodes": list(blockchain.nodes)}
        elif msg_type == "GET_PENDING":
            response = {"type": "PENDING", "pending": blockchain.current_transactions}
        else:
            response = {"status": "Error", "message": "Unknown message type."}
        file.write((json.dumps(response) + "\n").encode())
        file.flush()
    except Exception as e:
        print(f"Error handling connection from {addr}: {e}")
    finally:
        conn.close()

def run_server(host, port, blockchain, node_identifier):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"Listening for peers on {host}:{port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client_connection, args=(conn, addr, blockchain, node_identifier), daemon=True).start()

def broadcast_message(blockchain, message):
    for node in blockchain.nodes:
        send_message(node, message)

# -----------------------------
# Advanced Graphical User Interface (Tkinter)
# -----------------------------
class BlockchainGUI:
    def __init__(self, root, blockchain, node_identifier, args):
        self.root = root
        self.blockchain = blockchain
        self.node_identifier = node_identifier
        self.args = args

        ip = socket.gethostbyname(socket.gethostname())
        root.title(f"Blockchain Node: {ip}:{args.port}")

        style = ttk.Style()
        style.theme_use('clam')

        # Header Frame
        header_frame = ttk.Frame(root, padding="10")
        header_frame.pack(side=tk.TOP, fill=tk.X)
        header_label = ttk.Label(header_frame, text=f"Blockchain Node Interface - {ip}:{args.port}", font=("Helvetica", 16))
        header_label.pack(side=tk.LEFT)

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
        # Skip genesis block when showing confirmed transactions
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
            # Check if there is at least one pending (non-coinbase) transaction
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
                self.log("New Block Forged")
                self.block_info_text.delete("1.0", tk.END)
                self.block_info_text.insert(tk.END, json.dumps(block, indent=4))
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

# -----------------------------
# Main Function
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Advanced P2P Blockchain Node with Electrum-like GUI (pure Python)")
    parser.add_argument('--host', default="127.0.0.1", help='Host address of this node')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses in host:port format')
    args = parser.parse_args()

    node_identifier = str(uuid4()).replace('-', '')
    blockchain = Blockchain()

    if args.peers:
        for peer in args.peers.split(','):
            peer = peer.strip()
            if peer:
                try:
                    blockchain.register_node(peer)
                    response = send_message(peer, {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"}, expect_response=True)
                    if response and response.get("status") == "OK":
                        print(f"Registered with peer {peer}: {response.get('message')}")
                    else:
                        print(f"Could not register with peer {peer}.")
                    pending_response = send_message(peer, {"type": "GET_PENDING"}, expect_response=True)
                    if pending_response and pending_response.get("type") == "PENDING":
                        pending_from_peer = pending_response.get("pending", [])
                        for tx in pending_from_peer:
                            tx_str = json.dumps(tx, sort_keys=True)
                            local_tx_strs = [json.dumps(local_tx, sort_keys=True) for local_tx in blockchain.current_transactions]
                            if tx_str not in local_tx_strs:
                                blockchain.current_transactions.append(tx)
                    else:
                        print(f"No pending transactions received from {peer}.")
                except Exception as e:
                    print(f"Error registering with peer {peer}: {e}")

    server_thread = threading.Thread(target=run_server, args=(args.host, args.port, blockchain, node_identifier), daemon=True)
    server_thread.start()
    
    sleep(1)

    root = tk.Tk()
    app = BlockchainGUI(root, blockchain, node_identifier, args)
    root.mainloop()

if __name__ == '__main__':
    main()