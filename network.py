import json
import socket
import threading
import logging
from blockchain import canonical_transaction  # your blockchain module

# Configure logging for better debugging output.
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
        # Create a TCP connection to the peer.
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
            # Transaction may come as a nested dict or as separate fields.
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
                # Check if block is the next in sequence.
                if (block.get("index") == last_block["index"] + 1 and
                    block.get("previous_hash") == blockchain.hash(last_block)):
                    blockchain.chain.append(block)
                    # Remove transactions that are now in the block.
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
    
    In a distributed setup, ensure that the node addresses (as "host:port")
    are the actual public IP addresses and ports.
    """
    for node in list(blockchain.nodes):
        send_message(node, message)


# Optional: add a main entry point so you can run this node as a standalone service.
if __name__ == "__main__":
    import argparse
    from blockchain import Blockchain  # make sure your Blockchain class is defined

    parser = argparse.ArgumentParser(description="Distributed Blockchain Node")
    parser.add_argument("--host", default="0.0.0.0", help="IP address to bind the server")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind the server")
    parser.add_argument("--node_id", default="node_1", help="Unique identifier for the node")
    args = parser.parse_args()

    blockchain = Blockchain()
    run_server(args.host, args.port, blockchain, args.node_id)












# import json
# import socket
# import threading
# from blockchain import canonical_transaction

# def send_message(peer_address, message, expect_response=False):
#     try:
#         host, port_str = peer_address.split(":")
#         port = int(port_str)
#         with socket.create_connection((host, port), timeout=5) as s:
#             s.sendall((json.dumps(message) + "\n").encode())
#             if expect_response:
#                 file = s.makefile()
#                 response_line = file.readline()
#                 if response_line:
#                     return json.loads(response_line)
#     except Exception as e:
#         print(f"Error sending message to {peer_address}: {e}")
#     return None

# def handle_client_connection(conn, addr, blockchain, node_identifier):
#     try:
#         file = conn.makefile(mode="rwb")
#         line = file.readline()
#         if not line:
#             return
#         message = json.loads(line.decode())
#         msg_type = message.get("type")
#         response = {}
#         if msg_type == "GET_CHAIN":
#             response = {"type": "CHAIN", "chain": blockchain.chain}
#         elif msg_type == "REGISTER_NODE":
#             new_node = message.get("node")
#             if new_node:
#                 try:
#                     blockchain.register_node(new_node)
#                     response = {"status": "OK", "message": f"Node {new_node} registered."}
#                 except ValueError as e:
#                     response = {"status": "Error", "message": str(e)}
#             else:
#                 response = {"status": "Error", "message": "No node provided."}
#         elif msg_type == "NEW_TRANSACTION":
#             transaction = message.get("transaction")
#             if not transaction:
#                 sender = message.get("sender")
#                 recipient = message.get("recipient")
#                 amount = message.get("amount")
#                 if sender and recipient and amount is not None:
#                     blockchain.new_transaction(sender, recipient, amount)
#                     response = {"status": "OK", "message": "Transaction will be added."}
#                 else:
#                     response = {"status": "Error", "message": "Missing transaction fields."}
#             else:
#                 sender = transaction.get("sender")
#                 recipient = transaction.get("recipient")
#                 amount = transaction.get("amount")
#                 if sender and recipient and amount is not None:
#                     blockchain.new_transaction(sender, recipient, amount)
#                     response = {"status": "OK", "message": "Transaction will be added."}
#                 else:
#                     response = {"status": "Error", "message": "Invalid transaction data."}
#         elif msg_type == "NEW_BLOCK":
#             block = message.get("block")
#             if block:
#                 last_block = blockchain.last_block
#                 if block.get("index") == last_block["index"] + 1 and block.get("previous_hash") == blockchain.hash(last_block):
#                     blockchain.chain.append(block)
#                     block_tx_set = set(canonical_transaction(tx) for tx in block.get("transactions", []))
#                     blockchain.current_transactions = [
#                         tx for tx in blockchain.current_transactions 
#                         if canonical_transaction(tx) not in block_tx_set
#                     ]
#                     block_hash = blockchain.hash(block)
#                     if block_hash not in blockchain.seen_blocks:
#                         blockchain.seen_blocks.add(block_hash)
#                         broadcast_message(blockchain, {"type": "NEW_BLOCK", "block": block})
#                     response = {"status": "OK", "message": "Block accepted and pending transactions synced."}
#                 elif block.get("index") > last_block["index"] + 1:
#                     print("Block index indicates our chain might be behind. Resolving conflicts...")
#                     blockchain.resolve_conflicts()
#                     response = {"status": "OK", "message": "Chain synchronized with peers."}
#                 else:
#                     response = {"status": "Error", "message": "Invalid block."}
#             else:
#                 response = {"status": "Error", "message": "No block provided."}
#         elif msg_type == "GET_NODES":
#             response = {"type": "NODES", "nodes": list(blockchain.nodes)}
#         elif msg_type == "GET_PENDING":
#             response = {"type": "PENDING", "pending": blockchain.current_transactions}
#         else:
#             response = {"status": "Error", "message": "Unknown message type."}
#         file.write((json.dumps(response) + "\n").encode())
#         file.flush()
#     except Exception as e:
#         print(f"Error handling connection from {addr}: {e}")
#     finally:
#         conn.close()

# def run_server(host, port, blockchain, node_identifier):
#     server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     server.bind((host, port))
#     server.listen(5)
#     print(f"Listening for peers on {host}:{port}")
#     while True:
#         conn, addr = server.accept()
#         threading.Thread(target=handle_client_connection, args=(conn, addr, blockchain, node_identifier), daemon=True).start()

# def broadcast_message(blockchain, message):
#     for node in blockchain.nodes:
#         send_message(node, message)
