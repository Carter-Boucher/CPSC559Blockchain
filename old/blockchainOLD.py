import hashlib
import json
import socket
import threading
from time import time, sleep
from uuid import uuid4
import argparse

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
            # Check that the block's previous hash is correct.
            if block['previous_hash'] != self.hash(last_block):
                return False
            # Check that the Proof of Work is correct.
            if not self.valid_proof(last_block['nonce'], block['nonce'], self.hash(last_block)):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        Consensus Algorithm:
        This resolves conflicts by replacing our chain with the longest one in the network.
        It contacts each peer using our custom TCP protocol.
        :return: True if our chain was replaced, False if not.
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
        Before creating the block, update the status of all pending transactions to 'success'.
        :param nonce: The proof given by the Proof of Work algorithm.
        :param previous_hash: Hash of previous Block.
        :param auto_broadcast: Whether to broadcast this block to all peers.
        :return: New Block.
        """
        # Update each pending transaction to indicate success.
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
        # Clear pending transactions as they have now been included in a block.
        self.current_transactions = []

        # Compute the block hash.
        block_hash = self.hash(block)
        # Broadcast the block if it hasn’t been seen before.
        if block_hash not in self.seen_blocks:
            self.seen_blocks.add(block_hash)
            if auto_broadcast:
                broadcast_message(self, {"type": "NEW_BLOCK", "block": block})

        return block

    def new_transaction(self, sender, recipient, amount, auto_broadcast=True):
        """
        Creates a new transaction with an initial status of 'pending'.
        This transaction will later be updated to 'success' when included in a mined block.
        :param sender: Address of the sender.
        :param recipient: Address of the recipient.
        :param amount: Amount.
        :param auto_broadcast: Whether to broadcast this transaction to all peers.
        :return: The index of the Block that will hold this transaction.
        """

        if sender == "0":
            print("Ignoring transaction from sender '0'.")
            return self.last_block['index'] + 1
        
        transaction = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'status': 'pending'
        }
        # Create a canonical string representation.
        tx_str = json.dumps(transaction, sort_keys=True)
        # Avoid re-adding/broadcasting the same transaction.
        if tx_str in self.seen_transactions:
            return self.last_block['index'] + 1

        self.current_transactions.append(transaction)
        self.seen_transactions.add(tx_str)

        if auto_broadcast:
            broadcast_message(self, {"type": "NEW_TRANSACTION", "transaction": transaction})

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block.
        :param block: Block.
        :return: The hash string.
        """
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        """Returns the last Block in the chain."""
        return self.chain[-1]

    def proof_of_work(self, last_nonce):
        """
        Simple Proof of Work Algorithm:
         - Find a number p' such that hash(last_nonce, p') contains 4 leading zeroes.
         - p is the previous nonce, and p' is the new nonce.
        :param last_nonce: <int>
        :return: <int>
        """
        nonce = 0
        last_hash = self.hash(self.last_block)
        while not self.valid_proof(last_nonce, nonce, last_hash):
            nonce += 1
        return nonce

    @staticmethod
    def valid_proof(last_nonce, nonce, last_hash):
        """
        Validates the Proof: Does hash(last_nonce, nonce, last_hash) contain 4 leading zeroes?
        :param last_nonce: <int> Previous Nonce.
        :param nonce: <int> Current Nonce.
        :param last_hash: <str> Hash of the Previous Block.
        :return: <bool> True if correct, False if not.
        """
        guess = f'{last_nonce}{nonce}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

# -----------------------------
# Peer-to-Peer Networking (Sockets)
# -----------------------------
def send_message(peer_address, message, expect_response=False):
    """
    Send a JSON message to a peer over TCP.
    :param peer_address: string "host:port"
    :param message: dict to send.
    :param expect_response: If True, wait for and return a JSON response.
    :return: The response as a dict if expect_response is True, else None.
    """
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
    """
    Handle incoming connections from peers.
    The protocol expects one JSON message (terminated by newline) per connection.
    """
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
            # Extract the transaction object if sent as a whole.
            transaction = message.get("transaction")
            # If not provided as a whole, fall back to individual fields.
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
                # Unpack transaction details.
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
                # Basic validation: block index and previous_hash must match.
                if block.get("index") == last_block["index"] + 1 and block.get("previous_hash") == blockchain.hash(last_block):
                    blockchain.chain.append(block)
                    # Auto-sync: Remove any pending transactions that are included in the new block.
                    block_tx_set = set(canonical_transaction(tx) for tx in block.get("transactions", []))
                    blockchain.current_transactions = [
                        tx for tx in blockchain.current_transactions 
                        if canonical_transaction(tx) not in block_tx_set
                    ]
                    # Broadcast the new block if not seen.
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
            # Return the list of pending transactions.
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
    """
    Runs a TCP server that listens for incoming peer connections.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"Listening for peers on {host}:{port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client_connection, args=(conn, addr, blockchain, node_identifier), daemon=True).start()

def broadcast_message(blockchain, message):
    """
    Broadcast a message to all known peer nodes.
    """
    for node in blockchain.nodes:
        send_message(node, message)

# -----------------------------
# Command-line Interface for Blockchain
# -----------------------------
def print_menu():
    print("\nBlockchain Menu:")
    print("1. Mine a new block")
    print("2. Create a new transaction")
    print("3. Show ledger")
    print("4. Register a new node")
    print("5. Resolve conflicts (synchronize chain with peers)")
    print("6. Discover new nodes")
    print("7. Exit")

def main():
    parser = argparse.ArgumentParser(description="Simple P2P Blockchain Node (pure Python)")
    parser.add_argument('--host', default="127.0.0.1", help='Host address of this node')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses in host:port format')
    args = parser.parse_args()

    node_identifier = str(uuid4()).replace('-', '')
    blockchain = Blockchain()

    # Register any peers provided on the command line.
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
                    # Fetch pending transactions from the peer.
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

    # Start the server thread.
    server_thread = threading.Thread(target=run_server, args=(args.host, args.port, blockchain, node_identifier), daemon=True)
    server_thread.start()
    
    sleep(1)  # Allow time for the server to start.

    while True:
        print_menu()
        choice = input("Enter your choice (1-7): ").strip()
        
        if choice == '1':
            print("Mining a new block...")
            last_block = blockchain.last_block
            last_nonce = last_block['nonce']
            nonce = blockchain.proof_of_work(last_nonce)
            # Reward the miner.
            blockchain.new_transaction(
                sender="0",
                recipient=node_identifier,
                amount=1,
                auto_broadcast=True
            )
            previous_hash = blockchain.hash(last_block)
            block = blockchain.new_block(nonce, previous_hash, auto_broadcast=True)
            print("New Block Forged:")
            print(json.dumps(block, indent=4))

        elif choice == '2':
            print("Create a new transaction:")
            sender = input("Sender: ").strip()
            recipient = input("Recipient: ").strip()
            amount_input = input("Amount: ").strip()
            try:
                amount = float(amount_input)
            except ValueError:
                print("Invalid amount. Please enter a number.")
                continue
            index = blockchain.new_transaction(sender, recipient, amount, auto_broadcast=True)
            print(f"Transaction will be added to Block {index}")

        elif choice == '3':
            print("Confirmed Blockchain:")
            print(json.dumps(blockchain.chain, indent=4))
            print("Pending Transactions:")
            print(json.dumps(blockchain.current_transactions, indent=4))
            
        elif choice == '4':
            address = input("Enter node address (host:port): ").strip()
            try:
                blockchain.register_node(address)
                print("Node registered locally!")
                response = send_message(address, {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"}, expect_response=True)
                if response:
                    print(f"Response from {address}: {response.get('message')}")
                pending_response = send_message(address, {"type": "GET_PENDING"}, expect_response=True)
                if pending_response and pending_response.get("type") == "PENDING":
                    pending_from_peer = pending_response.get("pending", [])
                    for tx in pending_from_peer:
                        tx_str = json.dumps(tx, sort_keys=True)
                        local_tx_strs = [json.dumps(local_tx, sort_keys=True) for local_tx in blockchain.current_transactions]
                        if tx_str not in local_tx_strs:
                            blockchain.current_transactions.append(tx)
                else:
                    print(f"No pending transactions received from {address}.")
            except ValueError as e:
                print(f"Error: {e}")
            
        elif choice == '5':
            print("Resolving conflicts by querying peers...")
            replaced = blockchain.resolve_conflicts()
            if replaced:
                print("Our chain was replaced by a longer valid chain.")
            else:
                print("Our chain remains authoritative.")
                
        elif choice == '6':
            print("Discovering new nodes from known peers...")
            discovered_nodes = set()
            for node in list(blockchain.nodes):
                response = send_message(node, {"type": "GET_NODES"}, expect_response=True)
                if response and response.get("type") == "NODES":
                    for n in response.get("nodes", []):
                        discovered_nodes.add(n)
            blockchain.nodes.update(discovered_nodes)
            print("Updated node list:")
            print(blockchain.nodes)
        elif choice == '7':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please choose a valid option.")

if __name__ == '__main__':
    main()