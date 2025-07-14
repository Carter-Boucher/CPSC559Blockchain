import hashlib
import json
from time import time
import uuid
import threading
import random
import ecdsa
import base64

debug = False

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
        self.current_leader = None  # Leader election attribute
        
        self.difficulty = 4
        self.block_time_target = 10  # seconds

        # Set the election start time (when the first node starts)
        self.election_start_time = time()

        self.ecdsa_private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.ecdsa_public_key = self.ecdsa_private_key.get_verifying_key()

        genesis_block = self.create_genesis_block()
        self.chain.append(genesis_block)
        self.seen_blocks.add(self.hash(genesis_block))

        self.node_address = None  # Node address for leader election

    def create_genesis_block(self):
        genesis_block = {
            'index': 1,
            'timestamp': 1234567890,
            'transactions': [],
            'nonce': 100,
            'previous_hash': '1',
            'difficulty': self.difficulty
        }
        return genesis_block

    def register_node(self, address):
        if ":" not in address:
            raise ValueError("Address must be in host:port format")
        if hasattr(self, "node_address") and address == self.node_address:
            return
        self.nodes.add(address)

    def elect_leader(self):
        """Elect a leader using a VRF-like approach (ECDSA sign + hash)."""
        from network import send_message
        
        # Sync with peers so we have the latest chain
        self.resolve_conflicts()

        # The seed is the hash of our last block
        Qn = self.hash(self.last_block)

        # Build the list of candidates
        candidate_addresses = list(self.nodes)
        if self.node_address is not None:
            candidate_addresses.append(self.node_address)
        else:
            candidate_addresses.append(str(self.node_id))

        # Ping each candidate to ensure it's alive
        reachable_candidates = []
        for candidate in candidate_addresses:
            if candidate == self.node_address:
                reachable_candidates.append(candidate)
            else:
                response = send_message(candidate, {"type": "PING"}, expect_response=True)
                if response and response.get("status") == "OK":
                    reachable_candidates.append(candidate)
                else:
                    self.nodes.discard(candidate)

        # Everyone (including me) signs the seed and broadcasts
        # We'll store a local "vrf_submissions" dict keyed by candidate
        vrf_submissions = {}

        # Function to sign the seed with our private key, 
        # then produce a base64-encoded signature
        def sign_seed(seed: str):
            signature_bytes = self.ecdsa_private_key.sign(seed.encode('utf-8'))
            return base64.b64encode(signature_bytes).decode('utf-8')
        
        if(debug): print(f"Node {self.node_address} signing seed {Qn} with private key.")

        # My own submission
        my_signature_b64 = sign_seed(Qn)
        my_pubkey_b64 = base64.b64encode(self.ecdsa_public_key.to_string()).decode('utf-8')
        my_output_hash = hashlib.sha256(base64.b64decode(my_signature_b64)).hexdigest()

        vrf_submissions[self.node_address] = {
            "public_key": my_pubkey_b64,
            "signature": my_signature_b64,
            "output_hash": my_output_hash,
            "candidate": self.node_address
        }

        # Ask each reachable candidate for their VRF submission
        for candidate in reachable_candidates:
            if candidate == self.node_address:
                continue
            # Send a request for VRF data
            response = send_message(candidate, {
                "type": "LEADER_ELECTION_VRF",
                "seed": Qn  # so they know what to sign
            }, expect_response=True)
            if response and response.get("status") == "OK" and "submission" in response:
                submission = response["submission"]
                vrf_submissions[candidate] = submission

        # Verify each candidate’s submission
        valid_candidates = []
        for cand, sub in vrf_submissions.items():
            pubkey_raw = base64.b64decode(sub["public_key"])
            signature_raw = base64.b64decode(sub["signature"])
            output_hash = sub["output_hash"]
            try:
                vk = ecdsa.VerifyingKey.from_string(pubkey_raw, curve=ecdsa.SECP256k1)
                # Verify the signature
                vk.verify(signature_raw, Qn.encode('utf-8'))

                # Check the output_hash
                check_hash = hashlib.sha256(signature_raw).hexdigest()
                if check_hash != output_hash:
                    if debug:
                        print(f"Candidate {cand} gave invalid output_hash.")
                    continue

                # If we reach here, submission is valid
                valid_candidates.append((cand, output_hash))
            except Exception as e:
                if debug:
                    print(f"Candidate {cand} signature verification failed: {e}")
                continue

        if not valid_candidates:
            # If no valid submissions, fallback to "None"
            self.current_leader = None
            if debug:
                print("No valid leader submissions found!")
            return self.current_leader

        # Pick the smallest output_hash
        valid_candidates.sort(key=lambda x: x[1])  # sort by output_hash
        best_candidate, best_hash = valid_candidates[0]

        self.current_leader = best_candidate
        if debug:
            print(f"New leader elected: {best_candidate} (lowest VRF hash: {best_hash})")

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

    def cumulative_work(self, chain=None):
        if chain is None:
            chain = self.chain
        sums = sum(block.get("difficulty", self.difficulty) for block in chain)
        if(debug): print(f"Cumulative work: {sums}")
        return sums

    def resolve_conflicts(self):
        from network import send_message
        neighbours = list(self.nodes)
        new_chain = None
        current_work = self.cumulative_work()

        for node in neighbours:
            response = send_message(node, {"type": "GET_CHAIN"}, expect_response=True)
            if response and response.get("type") == "CHAIN":
                chain = response.get("chain")
                if chain and self.valid_chain(chain):
                    chain_work = self.cumulative_work(chain)
                    if chain_work > current_work:
                        current_work = chain_work
                        new_chain = chain

        if new_chain:
            self.chain = new_chain
            confirmed = set()
            for block in new_chain:
                for tx in block.get("transactions", []):
                    confirmed.add(canonical_transaction(tx))
            self.current_transactions = [
                tx for tx in self.current_transactions 
                if canonical_transaction(tx) not in confirmed
            ]
            if debug:
                print("Chain replaced via resolve_conflicts with higher cumulative work.")
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
                    if hasattr(self, "node_address") and peer == self.node_address:
                        continue
                    # Add liveness check: only add if the peer responds to a PING
                    ping_response = send_message(peer, {"type": "PING"}, expect_response=True)
                    if ping_response and ping_response.get("status") == "OK":
                        if peer not in self.nodes:
                            self.nodes.add(peer)
                            discovered = True
                    else:
                        continue
            else:
                self.nodes.discard(node)
                discovered = True
        return discovered


    def new_block(self, nonce, previous_hash=None, auto_broadcast=True):
        # Only the leader is allowed to mine and propose blocks.
        if self.current_leader != self.node_address:
            if debug:
                print(f"Current leader {self.current_leader} not equal to node address {self.node_address}.")
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
            'transactions': self.current_transactions.copy(),
            'nonce': nonce,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
            'difficulty': self.difficulty
        }

        if auto_broadcast:
            committed_block = self.propose_block(block)
            return committed_block
        else:
            self.chain.append(block)
            self.current_transactions = []
            block_hash = self.hash(block)
            if block_hash not in self.seen_blocks:
                self.seen_blocks.add(block_hash)
            self.adjust_difficulty()
            return block

    def propose_block(self, block):
        from network import send_message
        approvals = 1  # Leader's own vote
        total_nodes = len(self.nodes) + 1  # including self
        quorum_threshold = total_nodes // 2 + 1
        for node in list(self.nodes):
            response = send_message(node, {"type": "BLOCK_PROPOSE", "block": block}, expect_response=True)
            if response and response.get("vote") == "approve":
                approvals += 1
        if approvals >= quorum_threshold:
            for node in list(self.nodes):
                send_message(node, {"type": "BLOCK_COMMIT", "block": block})
            self.chain.append(block)
            self.current_transactions = []
            block_hash = self.hash(block)
            if block_hash not in self.seen_blocks:
                self.seen_blocks.add(block_hash)
            if debug:
                print("Block committed with consensus. Approvals:", approvals)
            self.adjust_difficulty()
            return block
        else:
            if debug:
                print("Block proposal rejected by consensus. Approvals:", approvals, "of", quorum_threshold, "required.")
            return None

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

    def new_transaction(self, sender, recipient, amount, auto_broadcast=True, transaction=None):
        if sender == "0":
            if debug:
                print("Ignoring transaction from sender '0'.")
            return self.last_block['index'] + 1

        if transaction is None:
            transaction = {
                'id': str(uuid.uuid4()),  # Unique identifier for each transaction
                'sender': sender,
                'recipient': recipient,
                'amount': amount,
                'status': 'pending'
            }

        # If the transaction has already been processed (seen), skip adding it.
        if transaction.get("id") in self.seen_transactions:
            if debug:
                print("Transaction already processed (seen).")
            return self.last_block['index'] + 1

        # Check if a transaction with the same ID is already pending.
        if any(tx.get("id") == transaction.get("id") for tx in self.current_transactions):
            return self.last_block['index'] + 1

        self.current_transactions.append(transaction)

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
        nonce = 0
        while True:
            guess = f'{last_nonce}{nonce}{self.hash(self.last_block)}'.encode()
            guess_hash = hashlib.sha256(guess).hexdigest()
            if guess_hash[:self.difficulty] == "0" * self.difficulty:
                return nonce
            nonce += 1

    def cleanup_pending_transactions(self):
        """
        Remove transactions from the pending list if their id is found in any block of the chain.
        """
        # Gather all transaction ids from the confirmed blocks in the ledger.
        confirmed_ids = {tx.get("id") for block in self.chain for tx in block.get("transactions", [])}
        original_count = len(self.current_transactions)
        # Keep only transactions that have not been confirmed.
        self.current_transactions = [tx for tx in self.current_transactions if tx.get("id") not in confirmed_ids]
        if debug:
            removed = original_count - len(self.current_transactions)
            if removed > 0:
                if(debug): print(f"Cleaned up {removed} confirmed pending transaction(s).")

