import hashlib
import json
from time import time

def canonical_transaction(tx):
    """Return a canonical JSON representation of a transaction, ignoring the 'status' field."""
    return json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True)

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
        # Import locally to avoid circular dependency.
        from network import send_message  
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
                from network import broadcast_message  # local import to avoid circular dependency
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
            from network import broadcast_message
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
