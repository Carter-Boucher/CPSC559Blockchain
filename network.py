import json
import socket
import threading
import logging
from blockchain import canonical_transaction  # your blockchain module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def send_message(peer_address, message, expect_response=False):
    """
    Sends a JSON-encoded message to a peer node.
    peer_address: A string in the format "host:port"
    message: A dictionary to send
    expect_response: If True, waits for a JSON response terminated by a newline.
    """
    try:
        host, port_str = peer_address.split(":")
        port = int(port_str)
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall((json.dumps(message) + "\n").encode("utf-8"))
            if expect_response:
                file = sock.makefile()
                response_line = file.readline()
                if response_line:
                    return json.loads(response_line)
    except Exception as e:
        logging.error(f"Error sending message to {peer_address}: {e}")
    return None

def handle_client_connection(conn, addr, blockchain, node_identifier):
    """
    Handles incoming connection from a peer.
    Reads a JSON message, processes it according to the message type,
    and sends back a JSON response.
    """
    try:
        file = conn.makefile(mode="rwb")
        line = file.readline()
        if not line:
            return
        message = json.loads(line.decode("utf-8"))
        msg_type = message.get("type")
        response = {}

        if msg_type == "ELECTION":
            # In random election mode, simply acknowledge the message.
            response = {"status": "OK", "message": "Random election mode: ELECTION message acknowledged."}

        elif msg_type == "PING":
            response = {"status": "OK", "message": "Alive"}

        elif msg_type == "COORDINATOR":
            leader_id = message.get("leader_id")
            blockchain.handle_coordinator_message(leader_id)
            response = {"status": "OK", "message": f"Acknowledged new leader {leader_id}"}

        elif msg_type == "HEARTBEAT":
            leader_id = message.get("leader_id")
            blockchain.handle_heartbeat(leader_id)
            response = {"status": "OK", "message": "Heartbeat received."}

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

        elif msg_type == "NEW_TRANSACTION":
            transaction = message.get("transaction")
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
                if (block.get("index") == last_block["index"] + 1 and
                    block.get("previous_hash") == blockchain.hash(last_block)):
                    blockchain.chain.append(block)
                    block_tx_set = set(canonical_transaction(tx) for tx in block.get("transactions", []))
                    blockchain.current_transactions = [
                        tx for tx in blockchain.current_transactions 
                        if canonical_transaction(tx) not in block_tx_set
                    ]
                    block_hash = blockchain.hash(block)
                    if block_hash not in blockchain.seen_blocks:
                        blockchain.seen_blocks.add(block_hash)
                        broadcast_message(blockchain, {"type": "NEW_BLOCK", "block": block})
                    response = {"status": "OK", "message": "Block accepted and transactions synced."}
                elif block.get("index") > last_block["index"] + 1:
                    logging.info("Our chain might be behind. Resolving conflicts...")
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

        else:
            response = {"status": "Error", "message": "Unknown message type."}

        file.write((json.dumps(response) + "\n").encode("utf-8"))
        file.flush()
    except Exception as e:
        logging.error(f"Error handling connection from {addr}: {e}")
    finally:
        conn.close()

def run_server(host, port, blockchain, node_identifier):
    """
    Starts the server that listens for incoming connections from peers.
    To enable cross-machine communication, you can bind the server to "0.0.0.0".
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    logging.info(f"Node {node_identifier} listening on {host}:{port}")
    while True:
        conn, addr = server.accept()
        logging.info(f"Accepted connection from {addr}")
        threading.Thread(
            target=handle_client_connection,
            args=(conn, addr, blockchain, node_identifier),
            daemon=True
        ).start()

def broadcast_message(blockchain, message):
    """
    Broadcasts a message to all known peer nodes.
    If a node fails to respond 3 times in a row, it is removed.
    """
    for node in list(blockchain.nodes):
        response = send_message(node, message)
        if response is None:
            # Initialize failure_counts if not present.
            if not hasattr(blockchain, "failure_counts"):
                blockchain.failure_counts = {}
            # Increment the failure counter.
            blockchain.failure_counts[node] = blockchain.failure_counts.get(node, 0) + 1
            
            if blockchain.failure_counts[node] >= 3:
                blockchain.nodes.discard(node)
                del blockchain.failure_counts[node]
                logging.info(f"Node {node} removed after 3 consecutive failures.")
        else:
            # Reset failure counter on success.
            if hasattr(blockchain, "failure_counts") and node in blockchain.failure_counts:
                blockchain.failure_counts[node] = 0
