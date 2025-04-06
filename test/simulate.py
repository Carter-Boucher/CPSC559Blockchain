import random
import json
import time
from threading import Thread
from test.compare_chains import compare_chains

from blockchain import Blockchain
import network

# --- Simulation network layer ---

# Global dictionary to keep track of all simulated nodes.
nodes_dict = {}
crashed_nodes = set()
reconnected_nodes = set()

def simulated_send_message(peer_address, message, expect_response=False):
    """Simulate sending a message to a peer by directly calling its message handler.
    If the target node is crashed, the message will be dropped."""
    # Simulate a small network delay
    time.sleep(random.uniform(0.01, 0.05))
    if peer_address in nodes_dict:
        target_node = nodes_dict[peer_address]
        # If the node is crashed, simulate failure.
        if getattr(target_node, "crashed", False):
            return None
        response = simulated_process_message(target_node, message)
        return response if expect_response else None
    return None

def simulated_process_message(blockchain, message):
    """Simulate processing a message on a node.
    This replicates the logic in network.py's handle_client_connection but simplified for simulation."""
    msg_type = message.get("type")
    response = {}

    if msg_type == "PING":
        response = {"status": "OK", "message": "Alive"}

    elif msg_type == "GET_CHAIN":
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

    elif msg_type == "ELECT_LEADER":
        leader = message.get("leader")
        if leader is not None:
            blockchain.current_leader = leader
            response = {"status": "OK", "message": f"Leader set to {leader}"}
        else:
            response = {"status": "Error", "message": "No leader provided."}

    elif msg_type == "NEW_TRANSACTION":
        # Use provided transaction object if available
        transaction = message.get("transaction")
        if transaction:
            blockchain.new_transaction(
                transaction.get("sender"),
                transaction.get("recipient"),
                transaction.get("amount"),
                auto_broadcast=False
            )
            response = {"status": "OK", "message": "Transaction will be added."}
        else:
            sender = message.get("sender")
            recipient = message.get("recipient")
            amount = message.get("amount")
            if sender and recipient and amount is not None:
                blockchain.new_transaction(sender, recipient, amount, auto_broadcast=False)
                response = {"status": "OK", "message": "Transaction will be added."}
            else:
                response = {"status": "Error", "message": "Invalid transaction data."}

    elif msg_type == "NEW_BLOCK":
        block = message.get("block")
        if block:
            last_block = blockchain.last_block
            # Validate if the block follows correctly.
            if block.get("index") == last_block["index"] + 1 and block.get("previous_hash") == blockchain.hash(last_block):
                blockchain.chain.append(block)
                # Remove confirmed transactions from pending pool.
                block_tx_set = {json.dumps(tx, sort_keys=True) for tx in block.get("transactions", [])}
                blockchain.current_transactions = [
                    tx for tx in blockchain.current_transactions 
                    if json.dumps(tx, sort_keys=True) not in block_tx_set
                ]
                response = {"status": "OK", "message": "Block accepted and transactions synced."}
            elif block.get("index") > last_block["index"] + 1:
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

    elif msg_type == "DISCOVER_PEERS":
        response = {"type": "PEERS", "nodes": list(blockchain.nodes)}

    else:
        response = {"status": "Error", "message": "Unknown message type."}

    return response

def simulated_broadcast_message(blockchain, message):
    """Simulate broadcasting a message to all peers in a node's peer list."""
    for peer in list(blockchain.nodes):
        # If a node is crashed, skip sending the message.
        if nodes_dict[peer].crashed:
            continue
        simulated_send_message(peer, message)

def simulated_broadcast_election(blockchain):
    """Simulate a leader election broadcast."""
    leader = blockchain.elect_leader()
    for peer in list(blockchain.nodes):
        simulated_send_message(peer, {"type": "ELECT_LEADER", "leader": leader})

# Monkey-patch network functions for simulation.
network.send_message = simulated_send_message
network.broadcast_message = simulated_broadcast_message
network.broadcast_election = simulated_broadcast_election

# --- Create simulation nodes ---

NUM_NODES = 10
BASE_PORT = 5000
all_addresses = []

# Create 10 Blockchain nodes.
for i in range(NUM_NODES):
    host = "127.0.0.1"
    port = BASE_PORT + i
    node_address = f"{host}:{port}"
    node = Blockchain(node_id=port)
    node.node_address = node_address
    node.crashed = False  # New attribute to simulate a crash
    nodes_dict[node_address] = node
    all_addresses.append(node_address)

# Each node registers all other nodes as peers.
for node in nodes_dict.values():
    for addr in all_addresses:
        if addr != node.node_address:
            node.nodes.add(addr)

# --- New functions to simulate node crashes and reconnections ---

def random_crash_node(crash_probability=0.02):
    """
    With the given probability, randomly select an online node (not already crashed)
    and simulate a crash. When a node crashes, its address is removed from all peers' lists.
    """
    online_nodes = [addr for addr, node in nodes_dict.items() if not node.crashed]
    if online_nodes and random.random() < crash_probability:
        crash_addr = random.choice(online_nodes)
        crashed_node = nodes_dict[crash_addr]
        crashed_node.crashed = True
        # Remove the crashed node from all other nodes' peer lists.
        for node in nodes_dict.values():
            if crash_addr in node.nodes:
                node.nodes.remove(crash_addr)
        #print(f"Node {crash_addr} has crashed!")

def reconnect_node(node_address):
    """
    Reconnect a crashed node by setting its 'crashed' flag to False and
    re-adding its address to all peers' lists so that it starts receiving updates again.
    Also, immediately synchronize its chain with the network.
    """
    if node_address in nodes_dict:
        node = nodes_dict[node_address]
        if node.crashed:
            node.crashed = False
            # Re-add the node to all other nodes' peer lists.
            for addr, other_node in nodes_dict.items():
                if addr != node_address:
                    other_node.nodes.add(node_address)
            # Sync the node's chain with the network upon reconnection.
            node.resolve_conflicts()
            #print(f"Node {node_address} has reconnected and synchronized.")

    reconnected_nodes.add(node_address)

# Optionally, a function to randomly reconnect a crashed node.
def random_reconnect_node(reconnect_probability=0.05):
    """
    With the given probability, randomly select a crashed node and reconnect it.
    """
    crashed_nodes = [addr for addr, node in nodes_dict.items() if node.crashed]
    if crashed_nodes and random.random() < reconnect_probability:
        # print("Node reconnected: ", crashed_nodes)
        reconnect_addr = random.choice(crashed_nodes)
        reconnect_node(reconnect_addr)

# --- Simulation loop ---

# Define possible actions.
ACTIONS = ["new_transaction", "mine_block", "sync"]

# Number of simulation iterations.
NUM_ITERATIONS = 35

def simulate_node_actions():
    """Simulate random actions on each node."""
    for iteration in range(NUM_ITERATIONS):
        
        random_crash_node(crash_probability=0.20)
        # Attempt to randomly reconnect a crashed node.
        random_reconnect_node(reconnect_probability=0.05)
        
        # Progress bar
        print(f" Progress: {iteration+1}/{NUM_ITERATIONS}  Crashed nodes: {[addr for addr, node in nodes_dict.items() if node.crashed]}", end="\r")

        for node in list(nodes_dict.values()):
            # Skip actions for crashed nodes.
            if getattr(node, "crashed", False):
                continue

            action = random.choices(ACTIONS, weights=[0.6, 0.1, 0.3])[0]
            if action == "new_transaction":
                # Create a random transaction.
                sender = node.node_address
                recipient = random.choice(all_addresses)
                while recipient == sender:
                    recipient = random.choice(all_addresses)
                amount = round(random.uniform(1, 100), 2)
                node.new_transaction(sender, recipient, amount, auto_broadcast=True)
            elif action == "mine_block":
                # Only attempt mining if the node is the leader and has pending transactions.
                if node.current_leader == node.node_address and node.current_transactions:
                    last_nonce = node.last_block['nonce']
                    nonce = node.proof_of_work(last_nonce)
                    previous_hash = node.hash(node.last_block)
                    node.new_block(nonce, previous_hash, auto_broadcast=True)
            elif action == "sync":
                node.resolve_conflicts()
                node.discover_peers()
        # Every 10 iterations, simulate a broadcast election from a random node.
        if iteration % 10 == 0:
            random.choice(list(nodes_dict.values())).elect_leader()
            simulated_broadcast_election(random.choice(list(nodes_dict.values())))
        time.sleep(0.01)  # Small delay to simulate time passing

# Run the simulation in a separate thread.
simulation_thread = Thread(target=simulate_node_actions)
simulation_thread.start()
simulation_thread.join()

# --- Output final state ---

simulation_results = {}
for addr, node in nodes_dict.items():
    simulation_results[addr] = {
        "Confirmed Blockchain": node.chain,
        "pending_transactions": node.current_transactions,
    }

with open("simulation_results.json", "w") as f:
    json.dump(simulation_results, f, indent=4)

print("\nSimulation complete. Final state saved to simulation_results.json")
dead_nodes = [addr for addr, node in nodes_dict.items() if node.crashed]
print(f"Crashed nodes: {dead_nodes}")
print(f"Reconnected nodes: {reconnected_nodes}")

compare_chains()
