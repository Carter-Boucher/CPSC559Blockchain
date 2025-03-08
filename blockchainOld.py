import hashlib
import json
from time import time
from uuid import uuid4
from flask import Flask, jsonify, request
import requests
from urllib.parse import urlparse
import threading
import time as ttime

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
        :param address: Address of node. Eg. 'http://192.168.0.5:5000'
        """
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.scheme + "://" + parsed_url.netloc)
        elif parsed_url.path:
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError("Invalid URL")
    
    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid.
        :param chain: A blockchain (list of blocks)
        :return: True if valid, False if not
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
        :return: True if our chain was replaced, False if not
        """
        neighbours = self.nodes
        new_chain = None
        
        # Look for chains longer than ours.
        max_length = len(self.chain)
        
        # Grab and verify the chains from all the nodes in our network.
        for node in neighbours:
            try:
                response = requests.get(f'{node}/chain')
                if response.status_code == 200:
                    length = response.json()['length']
                    chain = response.json()['chain']
                    
                    if length > max_length and self.valid_chain(chain):
                        max_length = length
                        new_chain = chain
            except Exception as e:
                print(f"Could not connect to node {node}: {e}")
        
        # Replace our chain if we discovered a new, valid chain longer than ours.
        if new_chain:
            self.chain = new_chain
            return True
        
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
# Instantiate the Node and Flask App
# -----------------------------
app = Flask(__name__)

# Generate a globally unique address for this node.
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain.
blockchain = Blockchain()

# -----------------------------
# API Endpoints
# -----------------------------
@app.route('/mine', methods=['GET'])
def mine():
    """
    Mine a new block by:
      1. Calculating the Proof of Work.
      2. Rewarding the miner with a new transaction.
      3. Creating a new Block and adding it to the chain.
    """
    last_block = blockchain.last_block
    last_nonce = last_block['nonce']
    nonce = blockchain.proof_of_work(last_nonce)

    # Reward the miner (sender "0" means that this node has mined a new coin)
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(nonce, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'nonce': block['nonce'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    """
    Create a new transaction.
    Expects JSON with 'sender', 'recipient', and 'amount'.
    """
    values = request.get_json()

    required = ['sender', 'recipient', 'amount']
    if not values or not all(k in values for k in required):
        return 'Missing values', 400

    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    """
    Return the full blockchain.
    """
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

@app.route('/nodes/list', methods=['GET'])
def list_nodes():
    """
    Endpoint to list all known nodes.
    """
    response = {
        'nodes': [f'http://{node}' for node in blockchain.nodes]
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    """
    Register a list of new nodes. Expects a JSON payload with a list of nodes.
    """
    values = request.get_json()
    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    """
    Resolve conflicts across nodes by replacing our chain with the longest one in the network.
    """
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }
    return jsonify(response), 200

# -----------------------------
# Auto-Register Peers on Startup
# -----------------------------
def auto_register_peers(my_address, peers):
    """
    Automatically registers this node with a list of peer nodes.
    It sends a POST request to each peer's /nodes/register endpoint.
    """
    # Wait briefly to ensure the server is running.
    ttime.sleep(1)
    for peer in peers:
        try:
            url = f"{peer}/nodes/register"
            payload = {"nodes": [my_address]}
            response = requests.post(url, json=payload)
            if response.status_code == 201:
                print(f"Successfully registered with peer: {peer}")
            else:
                print(f"Failed to register with peer: {peer}, response: {response.text}")
            # Also add the peer to our own node list
            blockchain.register_node(peer)
        except Exception as e:
            print(f"Error registering with peer {peer}: {e}")

# -----------------------------
# Running the Node
# -----------------------------
if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    parser.add_argument('--host', default="127.0.0.1", help='host address of the node')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer node URLs (e.g., "http://127.0.0.1:5001,http://127.0.0.1:5002")')
    args = parser.parse_args()

    port = args.port
    my_address = f"http://{args.host}:{port}"

    # If peers are provided, start a background thread to auto-register with them.
    if args.peers:
        peer_list = [peer.strip() for peer in args.peers.split(',') if peer.strip()]
        thread = threading.Thread(target=auto_register_peers, args=(my_address, peer_list))
        thread.start()

    print(f"Starting node at {my_address}")
    app.run(host=args.host, port=port)
