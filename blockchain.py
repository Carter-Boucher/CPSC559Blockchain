import hashlib
import json
import socket
import threading
from time import time, sleep
from uuid import uuid4
from urllib.parse import urlparse
import argparse

# -----------------------------
# Blockchain and Block Classes
# -----------------------------
class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()
        # Create the genesis block (first block)
        self.new_block(previous_hash='1', nonce=100)

    def register_node(self, address):
        """
        Add a new node to the list of nodes.
        :param address: Address of node, e.g., "127.0.0.1:5001"
        """
        # Expect address in "host:port" format.
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

    def new_block(self, nonce, previous_hash=None):
        """
        Create a new Block in the Blockchain.
        :param nonce: The proof given by the Proof of Work algorithm.
        :param previous_hash: Hash of previous Block.
        :return: New Block.
        """
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'nonce': nonce,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        
        # Reset the current list of transactions.
        self.current_transactions = []
        
        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block.
        :param sender: Address of the sender.
        :param recipient: Address of the recipient.
        :param amount: Amount.
        :return: The index of the Block that will hold this transaction.
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })
        
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
                # Use a file-like object to read a full line
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
            sender = message.get("sender")
            recipient = message.get("recipient")
            amount = message.get("amount")
            if sender and recipient and amount is not None:
                index = blockchain.new_transaction(sender, recipient, amount)
                response = {"status": "OK", "message": f"Transaction will be added to Block {index}"}
            else:
                response = {"status": "Error", "message": "Missing transaction fields."}
        elif msg_type == "NEW_BLOCK":
            block = message.get("block")
            if block:
                last_block = blockchain.last_block
                # Basic validation: block index and previous_hash must match.
                if block.get("index") == last_block["index"] + 1 and block.get("previous_hash") == blockchain.hash(last_block):
                    blockchain.chain.append(block)
                    # (Optionally, remove transactions that appear in the block from current_transactions.)
                    response = {"status": "OK", "message": "Block accepted."}
                else:
                    response = {"status": "Error", "message": "Invalid block."}
            else:
                response = {"status": "Error", "message": "No block provided."}
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
    print("3. Show blockchain")
    print("4. Register a new node")
    print("5. Resolve conflicts (synchronize chain with peers)")
    print("6. Exit")

def main():
    parser = argparse.ArgumentParser(description="Simple P2P Blockchain Node (pure Python)")
    parser.add_argument('--host', default="127.0.0.1", help='Host address of this node')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses in host:port format')
    args = parser.parse_args()

    node_identifier = str(uuid4()).replace('-', '')
    blockchain = Blockchain()

    # If peers were provided on the command line, register them locally and tell them about us.
    if args.peers:
        for peer in args.peers.split(','):
            peer = peer.strip()
            if peer:
                try:
                    blockchain.register_node(peer)
                    # Inform the peer about this node
                    response = send_message(peer, {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"}, expect_response=True)
                    if response and response.get("status") == "OK":
                        print(f"Registered with peer {peer}: {response.get('message')}")
                    else:
                        print(f"Could not register with peer {peer}.")
                except Exception as e:
                    print(f"Error registering with peer {peer}: {e}")

    # Start the server thread to listen for incoming peer messages.
    server_thread = threading.Thread(target=run_server, args=(args.host, args.port, blockchain, node_identifier), daemon=True)
    server_thread.start()
    
    sleep(1)  # Brief pause to ensure the server is up before showing the menu.

    while True:
        print_menu()
        choice = input("Enter your choice (1-6): ").strip()
        
        if choice == '1':
            print("Mining a new block...")
            last_block = blockchain.last_block
            last_nonce = last_block['nonce']
            nonce = blockchain.proof_of_work(last_nonce)
            
            # Reward the miner (sender "0" means that this node mined a new coin)
            blockchain.new_transaction(
                sender="0",
                recipient=node_identifier,
                amount=1,
            )
            
            previous_hash = blockchain.hash(last_block)
            block = blockchain.new_block(nonce, previous_hash)
            print("New Block Forged:")
            print(json.dumps(block, indent=4))
            # Broadcast the new block to peers.
            broadcast_message(blockchain, {"type": "NEW_BLOCK", "block": block})
            
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
            index = blockchain.new_transaction(sender, recipient, amount)
            print(f"Transaction will be added to Block {index}")
            # Optionally broadcast the new transaction to peers.
            broadcast_message(blockchain, {
                "type": "NEW_TRANSACTION",
                "sender": sender,
                "recipient": recipient,
                "amount": amount
            })
            
        elif choice == '3':
            print("Full Blockchain:")
            print(json.dumps(blockchain.chain, indent=4))
            
        elif choice == '4':
            address = input("Enter node address (host:port): ").strip()
            try:
                blockchain.register_node(address)
                print("Node registered locally!")
                # Inform the new node about us.
                response = send_message(address, {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"}, expect_response=True)
                if response:
                    print(f"Response from {address}: {response.get('message')}")
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
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please choose a valid option.")

if __name__ == '__main__':
    main()
