import json
import socket
import threading
import logging
from blockchain import canonical_transaction

debug = False
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def send_message(peer_address, message, expect_response=False):
    try:
        host, port_str = peer_address.split(":")
        port = int(port_str)
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.settimeout(5)
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
    try:
        file = conn.makefile(mode="rwb")
        line = file.readline()
        if not line:
            return
        message = json.loads(line.decode("utf-8"))
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
                    response = {
                        "status": "OK",
                        "message": f"Node {new_node} registered.",
                        "election_start_time": blockchain.election_start_time
                    }
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
            transaction = message.get("transaction")
            if transaction:
                # Use the provided transaction directly
                blockchain.new_transaction(None, None, None, auto_broadcast=False, transaction=transaction)
                response = {"status": "OK", "message": "Transaction will be added."}
            else:
                sender = message.get("sender")
                recipient = message.get("recipient")
                amount = message.get("amount")
                if sender and recipient and amount is not None:
                    blockchain.new_transaction(sender, recipient, amount, auto_broadcast=False)
                    response = {"status": "OK", "message": "Transaction will be added."}
                else:
                    response = {"status": "Error", "message": "Missing transaction fields."}



        elif msg_type == "NEW_BLOCK":
            # For backward compatibility, you can keep this handler if needed.
            block = message.get("block")
            if block:
                last_block = blockchain.last_block
                if block.get("index") == last_block["index"] + 1:
                    if block.get("previous_hash") == blockchain.hash(last_block):
                        blockchain.chain.append(block)
                        block_tx_set = set(canonical_transaction(tx) for tx in block.get("transactions", []))
                        blockchain.current_transactions = [
                            tx for tx in blockchain.current_transactions 
                            if canonical_transaction(tx) not in block_tx_set
                        ]
                        block_hash = blockchain.hash(block)
                        if block_hash not in blockchain.seen_blocks:
                            blockchain.seen_blocks.add(block_hash)
                        response = {"status": "OK", "message": "Block accepted and transactions synced."}
                    else:
                        blockchain.resolve_conflicts()
                        response = {"status": "OK", "message": "Chain synchronized with peers."}
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

        elif msg_type == "BLOCK_PROPOSE":
            block = message.get("block")
            if block:
                last_block = blockchain.last_block
                # Validate that the block is the immediate next block
                if (block.get("index") == last_block["index"] + 1 and
                    block.get("previous_hash") == blockchain.hash(last_block) and
                    blockchain.valid_proof(last_block['nonce'], block.get("nonce"), blockchain.hash(last_block),
                                             block.get("difficulty", blockchain.difficulty))):
                    response = {"vote": "approve"}
                else:
                    response = {"vote": "reject"}
            else:
                response = {"vote": "reject", "message": "No block provided."}

        elif msg_type == "BLOCK_COMMIT":
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
                    response = {"status": "committed"}
                else:
                    response = {"status": "error", "message": "Block rejected during commit."}
            else:
                response = {"status": "error", "message": "No block provided."}

        else:
            response = {"status": "Error", "message": "Unknown message type."}

        file.write((json.dumps(response) + "\n").encode("utf-8"))
        file.flush()
    except Exception as e:
        logging.error(f"Error handling connection from {addr}: {e}")
    finally:
        conn.close()

def run_server(host, port, blockchain, node_identifier):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    if debug:
        logging.info(f"Node {node_identifier} listening on {host}:{port}")
    while True:
        conn, addr = server.accept()
        if debug:
            logging.info(f"Accepted connection from {addr}")
        threading.Thread(
            target=handle_client_connection,
            args=(conn, addr, blockchain, node_identifier),
            daemon=True
        ).start()

def broadcast_message(blockchain, message):
    for node in list(blockchain.nodes):
        send_message(node, message)

def broadcast_election(blockchain):
    """
    Broadcast the current leader (after election) to all peers.
    """
    leader = blockchain.elect_leader()
    for node in list(blockchain.nodes):
        send_message(node, {"type": "ELECT_LEADER", "leader": leader})
