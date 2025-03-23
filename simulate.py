import random
import json
import time
from blockchain import Blockchain
from compare_chains import compare_chains

# Simulation parameters
NUM_NODES = 20
NUM_ITERATIONS = 80   # total simulation iterations
# Action probabilities (they need not sum to 1 because random.choices accepts weights)
TRANSACTION_PROB = 0.8  
MINE_PROB = 0.1
SYNC_PROB = 0.1

def mine_block_for_node(node):
    """
    Compute a valid nonce for the node's next block.
    It iterates until node.valid_proof returns True.
    """
    last_block = node.last_block
    last_nonce = last_block['nonce']
    last_hash = node.hash(last_block)
    difficulty = node.difficulty
    nonce = 0
    while not node.valid_proof(last_nonce, nonce, last_hash, difficulty):
        nonce += 1
    return nonce

def propagate_block(leader, nodes):
    """
    Simulate network propagation of a new block mined by the leader.
    For simplicity, if a node's chain is shorter than the leader's,
    we replace it with a copy of the leader's chain.
    Also, remove from pending transactions those that are confirmed.
    """
    new_block = leader.chain[-1]
    for node in nodes.values():
        if len(node.chain) < len(leader.chain):
            # Copy the leader's chain (using a shallow copy for each block)
            node.chain = [block.copy() for block in leader.chain]
            # Remove confirmed transactions from pending list.
            confirmed = set()
            for block in node.chain:
                for tx in block.get("transactions", []):
                    # Use canonical representation ignoring status.
                    confirmed.add(json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True))
            node.current_transactions = [
                tx for tx in node.current_transactions 
                if json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True) not in confirmed
            ]

def propagate_transaction(tx, nodes):
    """
    Simulate broadcasting a new transaction to all nodes.
    Each node uses its new_transaction method with auto_broadcast turned off.
    """
    for node in nodes.values():
        node.new_transaction(tx['sender'], tx['recipient'], tx['amount'], auto_broadcast=False)

def sync_all_nodes(nodes):
    """
    Simulate a network-wide chain synchronization.
    Finds the longest chain among all nodes and updates nodes with shorter chains.
    """
    longest_chain = None
    max_length = 0
    for node in nodes.values():
        if len(node.chain) > max_length:
            longest_chain = node.chain
            max_length = len(node.chain)
    if longest_chain is not None:
        for node in nodes.values():
            if len(node.chain) < max_length:
                node.chain = [block.copy() for block in longest_chain]
                confirmed = set()
                for block in node.chain:
                    for tx in block.get("transactions", []):
                        confirmed.add(json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True))
                node.current_transactions = [
                    tx for tx in node.current_transactions 
                    if json.dumps({k: v for k, v in tx.items() if k != 'status'}, sort_keys=True) not in confirmed
                ]

def main():
    random.seed(42)  # for reproducibility

    # Create 100 nodes with node_ids starting at 5000 (addresses: 127.0.0.1:5000, …, 127.0.0.1:5099)
    nodes = {}
    base_port = 5000
    for i in range(NUM_NODES):
        port = base_port + i
        address = f"127.0.0.1:{port}"
        node = Blockchain(node_id=port)
        nodes[address] = node

    # Register peers: each node learns about all other nodes.
    addresses = list(nodes.keys())
    for node in nodes.values():
        for addr in addresses:
            # Avoid self-registration.
            if f":{node.node_id}" != addr:
                node.register_node(addr)
        # Each node runs a simple leader election. Given our method,
        # they will all agree on the node with the smallest node_id as leader.
        node.elect_leader()

    # Simulation loop: at each iteration, choose a random action.
    for _ in range(NUM_ITERATIONS):
        action = random.choices(
            ["transaction", "mine", "sync"],
            weights=[TRANSACTION_PROB, MINE_PROB, SYNC_PROB],
            k=1
        )[0]

        #format: Progress: current_iteration/total_iterations, {current action}
        print(f"\rProgress: {_}/{NUM_ITERATIONS}, {action}", end="")

        if action == "transaction":
            # Randomly choose sender and recipient (they must differ)
            sender_addr = random.choice(addresses)
            recipient_addr = random.choice(addresses)
            while recipient_addr == sender_addr:
                recipient_addr = random.choice(addresses)
            amount = round(random.uniform(1, 100), 2)
            tx = {
                "sender": sender_addr,
                "recipient": recipient_addr,
                "amount": amount,
                "status": "pending"
            }
            propagate_transaction(tx, nodes)

        elif action == "mine":
            # Only the leader is allowed to mine.
            # With our election, the leader is the node with the lowest node_id.
            leader_addr = f"127.0.0.1:{base_port}"
            leader = nodes[leader_addr]
            # Mine a block only if there are pending transactions.
            if leader.current_transactions:
                nonce = mine_block_for_node(leader)
                leader.new_block(nonce, auto_broadcast=False)
                propagate_block(leader, nodes)

        elif action == "sync":
            # Simulate a synchronization event.
            sync_all_nodes(nodes)

        # A brief pause to mimic asynchronous behavior.
        time.sleep(0.01)

    # Prepare final results in the expected format.
    results = {}
    for addr, node in nodes.items():
        results[addr] = {
            "node_id": node.node_id,
            "chain": node.chain,
            "pending_transactions": node.current_transactions,
            "nodes": list(node.nodes),
            "difficulty": node.difficulty
        }

    # Write simulation results to JSON file.
    with open("simulation_results.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
    print("\nSimulation complete. Results saved to simulation_results.json.")
    compare_chains()

