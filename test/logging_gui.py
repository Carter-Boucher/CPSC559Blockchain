import tkinter as tk
from tkinter import ttk, scrolledtext

class LoggingDashboard:
    def __init__(self, root, nodes):
        """
        Creates a dashboard window for monitoring node information.

        Parameters:
        - root: the main Tkinter window.
        - nodes: a dictionary of nodes keyed by their addresses.
        """
        self.root = root
        self.nodes = nodes
        self.root.title("Node Logging Dashboard")
        
        # Main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel: Treeview listing node summary info.
        self.node_tree = ttk.Treeview(main_frame, columns=("Address", "Chain Length", "Pending TXs", "Difficulty"), show="headings")
        self.node_tree.heading("Address", text="Node Address")
        self.node_tree.heading("Chain Length", text="Chain Length")
        self.node_tree.heading("Pending TXs", text="Pending Transactions")
        self.node_tree.heading("Difficulty", text="Difficulty")
        self.node_tree.column("Address", width=120)
        self.node_tree.column("Chain Length", width=100, anchor=tk.CENTER)
        self.node_tree.column("Pending TXs", width=130, anchor=tk.CENTER)
        self.node_tree.column("Difficulty", width=80, anchor=tk.CENTER)
        self.node_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Right panel: Detailed information for the selected node.
        detail_frame = ttk.Frame(main_frame)
        detail_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        detail_label = ttk.Label(detail_frame, text="Node Details")
        detail_label.pack(anchor=tk.W)
        self.detail_text = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, width=50)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        
        # Refresh button below the panels.
        refresh_btn = ttk.Button(root, text="Refresh", command=self.refresh)
        refresh_btn.pack(pady=5)
        
        # Bind event: When a node is selected, display its details.
        self.node_tree.bind("<<TreeviewSelect>>", self.on_node_select)
        
        # Start auto-refresh (every 2 seconds)
        self.auto_refresh()
    
    def refresh(self):
        """Refresh the node summary table with the latest information."""
        # Clear current entries
        for i in self.node_tree.get_children():
            self.node_tree.delete(i)
        # Insert summary data for each node.
        for address, node in self.nodes.items():
            chain_length = len(node.chain)
            pending_count = len(node.current_transactions)
            difficulty = node.difficulty if hasattr(node, 'difficulty') else 'N/A'
            self.node_tree.insert("", tk.END, values=(address, chain_length, pending_count, difficulty))
    
    def on_node_select(self, event):
        """Display detailed information for the selected node."""
        self.detail_text.delete("1.0", tk.END)
        selected = self.node_tree.selection()
        if selected:
            item = self.node_tree.item(selected[0])
            address = item['values'][0]
            node = self.nodes.get(address)
            if node:
                details = f"Node Address: {address}\n"
                details += f"Chain Length: {len(node.chain)}\n"
                details += f"Difficulty: {node.difficulty}\n"
                details += f"Pending Transactions: {len(node.current_transactions)}\n\n"
                details += "Chain Blocks:\n"
                for block in node.chain:
                    details += f"  Index: {block.get('index')}, Timestamp: {block.get('timestamp')}, Nonce: {block.get('nonce')}\n"
                details += "\nPending Transactions:\n"
                for tx in node.current_transactions:
                    details += f"  {tx}\n"
                self.detail_text.insert(tk.END, details)
    
    def auto_refresh(self):
        """Automatically refresh the dashboard every 2 seconds."""
        self.refresh()
        self.root.after(2000, self.auto_refresh)

# The following test code creates a few dummy nodes to illustrate how the dashboard works.
if __name__ == '__main__':
    from blockchain import Blockchain

    # Create dummy nodes for demonstration purposes.
    dummy_nodes = {}
    for i in range(5):
        node = Blockchain(node_id=5000 + i)
        address = f"127.0.0.1:{5000+i}"
        node.address = address
        # Simulate some activity: add a transaction and mine a block.
        node.new_transaction("Alice", "Bob", 10, auto_broadcast=False)
        last_nonce = node.last_block["nonce"]
        nonce = node.proof_of_work(last_nonce)
        node.new_block(nonce, previous_hash=node.hash(node.last_block), auto_broadcast=False)
        dummy_nodes[address] = node

    root = tk.Tk()
    dashboard = LoggingDashboard(root, dummy_nodes)
    root.mainloop()
