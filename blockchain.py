import hashlib
import json
from time import time
import threading
import time as ttime  # to avoid conflict with time() function
import random

def canonical_transaction(tx):
    """Return a canonical JSON representation of a transaction, ignoring the 'status' field."""
    return json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True)

class Blockchain:
    def __init__(self, node_id):
        # Node ID is used for leader election (assume integer, e.g. the port number)
        self.node_id = node_id
        self.chain = []
        self.current_transactions = []
        self.nodes = set()
        self.seen_transactions = set()
        self.seen_blocks = set()
        
        # Leader election and heartbeat state
        self.current_leader = None
        self.is_leader = False
        self.leader_last_heartbeat = ttime.time()
        self.election_in_progress = False

        # Lock for synchronizing election-related updates
        self.election_lock = threading.Lock()

        # Timing parameters (in seconds)
        self.heartbeat_interval = 5           # Leader sends heartbeat every 5 seconds
        self.election_timeout = 15            # If no heartbeat in 15 sec, trigger election
        self.periodic_election_interval = 60  # Force a new election every 60 seconds

        # Create and append the fixed genesis block.
        genesis_block = self.create_genesis_block()
        self.chain.append(genesis_block)
        self.seen_blocks.add(self.hash(genesis_block))

        # Start background threads for heartbeat, fault detection, and periodic elections.
        self._start_heartbeat_thread()
        self._start_fault_detection_thread()
        self._start_periodic_election_thread()

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
        if not self.is_leader:
            print("Only the leader can mine a new block.")
            return None

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
                from network import broadcast_message
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

    # ---------------------------
    # Leader Election and Heartbeats
    # ---------------------------
    def start_election(self):
        """
        Random Election with Live-Check:
        1. Mark election_in_progress = True.
        2. Build a candidate list including self and only those registered nodes that respond to a PING.
        3. Randomly select one candidate from the alive list.
        4. Broadcast a COORDINATOR message with the chosen leader.
        """
        with self.election_lock:
            if self.election_in_progress:
                return  # Election already in progress
            self.election_in_progress = True

        print(f"[Node {self.node_id}] Starting random election for decentralization.")

        # Start a timer to reset election state if no coordinator message is received
        def reset_election_state():
            ttime.sleep(self.election_timeout)
            with self.election_lock:
                if self.election_in_progress:
                    print(f"[Node {self.node_id}] Election timeout reached, resetting election state.")
                    self.election_in_progress = False

        threading.Thread(target=reset_election_state, daemon=True).start()

        # Optional: Add a small random delay to reduce simultaneous elections across nodes.
        ttime.sleep(random.uniform(0.1, 0.5))

        from network import broadcast_message
        alive_candidates = [self.node_id]  # Self is always alive.
        for node_addr in list(self.nodes):
            node_id = self._node_id_from_addr(node_addr)
            try:
                response = self.send_message_with_failure_tracking(node_addr, {"type": "PING"}, expect_response=True)
                if response and response.get("status") == "OK":
                    alive_candidates.append(node_id)
                else:
                    print(f"[Node {self.node_id}] No ping response from node {node_addr}.")
            except Exception as e:
                print(f"[Node {self.node_id}] Error pinging node {node_addr}: {e}")

        alive_candidates = list(set(alive_candidates))
        if not alive_candidates:
            alive_candidates = [self.node_id]

        chosen_leader = random.choice(alive_candidates)
        print(f"[Node {self.node_id}] Randomly selected leader: {chosen_leader}")

        broadcast_message(self, {
            "type": "COORDINATOR",
            "leader_id": chosen_leader
        })

        # Immediately update our own state.
        self.handle_coordinator_message(chosen_leader)

    def become_leader(self):
        self.is_leader = True
        self.current_leader = self.node_id
        with self.election_lock:
            self.election_in_progress = False
        print(f"[Node {self.node_id}] Became the leader.")
        from network import broadcast_message
        broadcast_message(self, {
            "type": "COORDINATOR",
            "leader_id": self.node_id
        })

    def handle_coordinator_message(self, leader_id):
        with self.election_lock:
            self.current_leader = leader_id
            self.is_leader = (self.node_id == leader_id)
            self.election_in_progress = False
        self.leader_last_heartbeat = ttime.time()
        print(f"[Node {self.node_id}] Acknowledges new leader: {leader_id}")

    def handle_heartbeat(self, leader_id):
        if leader_id == self.current_leader:
            self.leader_last_heartbeat = ttime.time()
        else:
            with self.election_lock:
                self.current_leader = leader_id
                self.is_leader = (self.node_id == leader_id)
                self.election_in_progress = False
            self.leader_last_heartbeat = ttime.time()

    def _start_heartbeat_thread(self):
        def heartbeat_loop():
            from network import broadcast_message
            while True:
                if self.is_leader:
                    broadcast_message(self, {
                        "type": "HEARTBEAT",
                        "leader_id": self.node_id
                    })
                ttime.sleep(self.heartbeat_interval)
        t = threading.Thread(target=heartbeat_loop, daemon=True)
        t.start()

    def _start_fault_detection_thread(self):
        def fault_detection_loop():
            while True:
                if not self.is_leader:
                    if ttime.time() - self.leader_last_heartbeat > self.election_timeout:
                        print(f"[Node {self.node_id}] Suspects leader {self.current_leader} failed.")
                        self.start_election()
                ttime.sleep(1)
        t = threading.Thread(target=fault_detection_loop, daemon=True)
        t.start()

    def _start_periodic_election_thread(self):
        def election_loop():
            while True:
                ttime.sleep(self.periodic_election_interval)
                print(f"[Node {self.node_id}] Initiating periodic election for decentralization.")
                self.start_election()
        t = threading.Thread(target=election_loop, daemon=True)
        t.start()

    def _node_id_from_addr(self, addr):
        """
        Extract a node's ID from its address.
        Here we assume the node's ID is the port number.
        """
        try:
            host, port = addr.split(':')
            return int(port)
        except Exception:
            return 0

    def send_message_with_failure_tracking(self, node, message, expect_response=False):
        """
        Wrapper for sending a message to a node.
        Increments a failure counter if the message fails.
        Removes the node from self.nodes after 3 consecutive failures.
        """
        from network import send_message
        response = send_message(node, message, expect_response)
        
        if response is None:
            if not hasattr(self, "failure_counts"):
                self.failure_counts = {}
            self.failure_counts[node] = self.failure_counts.get(node, 0) + 1
            
            if self.failure_counts[node] >= 3:
                self.nodes.discard(node)
                del self.failure_counts[node]
                print(f"[Node {self.node_id}] Removed node {node} after 3 consecutive failures.")
        else:
            if hasattr(self, "failure_counts") and node in self.failure_counts:
                self.failure_counts[node] = 0
        return response
