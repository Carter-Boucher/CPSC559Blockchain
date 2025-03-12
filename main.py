import argparse
import json
import threading
from time import sleep
import tkinter as tk
import logging

from blockchain import Blockchain
from network import run_server, send_message
from GUI import BlockchainGUI

def main():
    parser = argparse.ArgumentParser(
        description="Advanced P2P Blockchain Node with Electrum-like GUI (pure Python)"
    )
    parser.add_argument(
        '--host',
        default="127.0.0.1",
        help='Host address of this node (use "0.0.0.0" to listen on all interfaces)'
    )
    parser.add_argument(
        '-p', '--port',
        default=5000,
        type=int,
        help='Port to listen on'
    )
    parser.add_argument(
        '--peers',
        default="",
        help='Comma-separated list of peer addresses in host:port format'
    )
    args = parser.parse_args()

    # For leader election purposes, use the port as the node's numeric ID.
    node_identifier = args.port
    blockchain = Blockchain(node_id=node_identifier)

    # If peer addresses are provided, attempt to register with each one.
    if args.peers:
        for peer in args.peers.split(','):
            peer = peer.strip()
            if peer:
                try:
                    blockchain.register_node(peer)
                    logging.info(f"Attempting to register with peer {peer}...")
                    response = send_message(
                        peer,
                        {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"},
                        expect_response=True
                    )
                    if response and response.get("status") == "OK":
                        logging.info(f"Registered with peer {peer}: {response.get('message')}")
                    else:
                        logging.warning(f"Could not register with peer {peer}. Response: {response}")

                    pending_response = send_message(
                        peer,
                        {"type": "GET_PENDING"},
                        expect_response=True
                    )
                    if pending_response and pending_response.get("type") == "PENDING":
                        pending_from_peer = pending_response.get("pending", [])
                        for tx in pending_from_peer:
                            tx_str = json.dumps(tx, sort_keys=True)
                            local_tx_strs = [json.dumps(local_tx, sort_keys=True) for local_tx in blockchain.current_transactions]
                            if tx_str not in local_tx_strs:
                                blockchain.current_transactions.append(tx)
                    else:
                        logging.info(f"No pending transactions received from {peer}.")
                except Exception as e:
                    logging.error(f"Error registering with peer {peer}: {e}")

    # Start the server thread to listen for incoming peer connections.
    server_thread = threading.Thread(
        target=run_server,
        args=(args.host, args.port, blockchain, node_identifier),
        daemon=True
    )
    server_thread.start()
    
    # Allow the server to initialize.
    sleep(1)

    # Launch the Electrum-like GUI.
    root = tk.Tk()
    app = BlockchainGUI(root, blockchain, node_identifier, args)
    root.mainloop()

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    main()
