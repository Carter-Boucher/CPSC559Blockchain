import hashlib
import json
from time import time
import threading
import random

debug = True

def canonical_transaction(tx):
    """Return a canonical JSON representation of a transaction, ignoring the 'status' field."""
    return json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True)

class Blockchain:
    def __init__(self, node_id):
        self.node_id = node_id
        self.chain = []
        self.current_transactions = []
        self.nodes = set()
        self.seen_transactions = set()
        self.seen_blocks = set()
        self.current_leader = None  # New attribute for leader election
        
        self.difficulty = 4
        self.block_time_target = 10  # seconds

        genesis_block = self.create_genesis_block()
        self.chain.append(genesis_block)
        self.seen_blocks.add(self.hash(genesis_block))

    def create_genesis_block(self):
        genesis_block = {
            'index': 1,
            'timestamp': 1234567890,  # fixed timestamp for genesis
            'transactions': [],
            'nonce': 100,
            'previous_hash': '1',
            'difficulty': self.difficulty
        }
        return genesis_block

    def register_node(self, address):
        if ":" not in address:
            raise ValueError("Address must be in host:port format")
        self.nodes.add(address)

    def elect_leader(self):
        """
        Leader election based on: https://eprint.iacr.org/2022/993.pdf
        This method uses the hash of the last block as a common seed (Qn). 
        Each candidate computes a VRF value as:
            vrf_output = SHA256(candidate_identifier + Qn)
        where candidate_identifier is the node's unique string (e.g., "IP:port").
        
        The node with the smallest numeric VRF output is elected as leader.
        """
        # Use the hash of the last block as the common seed (Qn)
        #resolved_conflicts before electing leader
        self.resolve_conflicts()
        Qn = self.hash(self.last_block)
        
        # Prepare a list of candidate identifiers.
        # Assume that self.nodes contains addresses in "IP:port" format.
        candidate_addresses = list(self.nodes)
        
        # Include our own address. If a full address (host:port) is available in self.node_address,
        # use it; otherwise, fallback to using self.node_id (which may be just the port).
        if hasattr(self, 'node_address'):
            candidate_addresses.append(self.node_address)
        else:
            candidate_addresses.append(str(self.node_id))
        
        best_candidate = None
        best_value = None
        for candidate in candidate_addresses:
            # Compute a VRF-like output using SHA256 over candidate's identifier and the common seed.
            vrf_output = hashlib.sha256((candidate + Qn).encode()).hexdigest()
            candidate_value = int(vrf_output, 16)
            if best_value is None or candidate_value < best_value:
                best_value = candidate_value
                best_candidate = candidate
        
        self.current_leader = best_candidate
        if debug:
            print(f"New leader elected: {best_candidate} (VRF value: {best_value})")
        return best_candidate


    def valid_chain(self, chain):
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            if block['previous_hash'] != self.hash(last_block):
                return False
            if not self.valid_proof(last_block['nonce'], block['nonce'], self.hash(last_block),
                                    block.get("difficulty", self.difficulty)):
                return False
            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        """
        Consensus algorithm: replace our chain with the longest valid chain.
        In ties, choose the chain with the lowest hash.
        """
        from network import send_message
        neighbours = list(self.nodes)
        new_chain = None
        max_length = len(self.chain)
        current_chain_hash = self.hash_chain()

        for node in neighbours:
            response = send_message(node, {"type": "GET_CHAIN"}, expect_response=True)
            if response and response.get("type") == "CHAIN":
                chain = response.get("chain")
                if chain and self.valid_chain(chain):
                    chain_length = len(chain)
                    chain_hash = self.hash_chain(chain)
                    if chain_length > max_length or (chain_length == max_length and chain_hash < current_chain_hash):
                        max_length = chain_length
                        new_chain = chain
                        current_chain_hash = chain_hash

        if new_chain:
            self.chain = new_chain
            # Remove pending transactions already confirmed in the new chain.
            confirmed = set()
            for block in new_chain:
                for tx in block.get("transactions", []):
                    confirmed.add(canonical_transaction(tx))
            self.current_transactions = [
                tx for tx in self.current_transactions 
                if canonical_transaction(tx) not in confirmed
            ]
            if debug:
                print("Chain replaced via resolve_conflicts.")
            return True

        if debug:
            print("Our chain is authoritative.")
        return False

    def sync_chain(self):
        return self.resolve_conflicts()

    def discover_peers(self):
        from network import send_message
        discovered = False
        for node in list(self.nodes):
            response = send_message(node, {"type": "DISCOVER_PEERS"}, expect_response=True)
            if response and response.get("type") == "PEERS":
                peers = response.get("nodes", [])
                for peer in peers:
                    if peer not in self.nodes:
                        self.nodes.add(peer)
                        discovered = True
            else:
                # Remove the node if no valid response is received
                self.nodes.remove(node)
                discovered = True
        return discovered


    def new_block(self, nonce, previous_hash=None, auto_broadcast=True):
        # Only the leader is allowed to mine and propose blocks.
        if self.node_id != self.current_leader:
            if debug:
                print("Not the leader. Block mining is handled by the leader.")
            return None

        if not self.current_transactions:
            if debug:
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
            'difficulty': self.difficulty
        }

        self.chain.append(block)
        self.current_transactions = []
        block_hash = self.hash(block)
        if block_hash not in self.seen_blocks:
            self.seen_blocks.add(block_hash)
            if auto_broadcast:
                from network import broadcast_message
                broadcast_message(self, {"type": "NEW_BLOCK", "block": block})
        self.adjust_difficulty()
        return block

    def adjust_difficulty(self):
        if len(self.chain) < 2:
            return
        last_block = self.chain[-1]
        prev_block = self.chain[-2]
        time_diff = last_block['timestamp'] - prev_block['timestamp']
        if time_diff < self.block_time_target:
            self.difficulty += 1
            if debug:
                print(f"Difficulty increased to {self.difficulty}")
        elif time_diff > self.block_time_target * 2 and self.difficulty > 4:
            self.difficulty -= 1
            if debug:
                print(f"Difficulty decreased to {self.difficulty}")

    def new_transaction(self, sender, recipient, amount, auto_broadcast=True):
        if sender == "0":
            if debug:
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

    def hash(self, block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def hash_chain(self, chain=None):
        if chain is None:
            chain = self.chain
        canonical = json.dumps(chain, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def valid_proof(self, last_nonce, nonce, last_hash, difficulty):
        guess = f'{last_nonce}{nonce}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:difficulty] == "0" * difficulty

    def proof_of_work(self, last_nonce):
        """
        Simple proof of work to find a nonce satisfying the current difficulty.
        """
        nonce = 0
        while True:
            guess = f'{last_nonce}{nonce}{self.hash(self.last_block)}'.encode()
            guess_hash = hashlib.sha256(guess).hexdigest()
            if guess_hash[:self.difficulty] == "0" * self.difficulty:
                return nonce
            nonce += 1