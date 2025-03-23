import argparse
import json
import threading
from time import sleep
import tkinter as tk
import logging

from blockchain import Blockchain
from network import run_server, send_message, broadcast_election
from GUI import BlockchainGUI

def periodic_sync(blockchain):
    import time
    count = 0
    while True:
        blockchain.resolve_conflicts()
        blockchain.discover_peers()
        if count % 6 == 0:
            broadcast_election(blockchain)
        count += 1
        time.sleep(5)

def run_tests():
    print("Running tests...")
    # Here you can add tests for leader election and block proposals.
    print("Tests complete.")

def main():
    parser = argparse.ArgumentParser(
        description="Advanced P2P Blockchain Node with Electrum-like GUI (pure Python)"
    )
    parser.add_argument('--host', default="127.0.0.1", help='Host address of this node (use "0.0.0.0" to listen on all interfaces)')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses in host:port format')
    parser.add_argument('--test', action='store_true', help='Run test suite instead of launching the GUI.')
    args = parser.parse_args()

    if args.test:
        run_tests()
        return

    # Use the port as the node's numeric identifier.
    node_identifier = args.port
    blockchain = Blockchain(node_id=node_identifier)

    # Register with peers if provided.
    if args.peers:
        for peer in args.peers.split(','):
            peer = peer.strip()
            if peer:
                try:
                    blockchain.register_node(peer)
                    logging.info(f"Registering with peer {peer}...")
                    response = send_message(peer, {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"}, expect_response=True)
                    if response and response.get("status") == "OK":
                        logging.info(f"Registered with peer {peer}.")
                except Exception as e:
                    logging.error(f"Error registering with peer {peer}: {e}")

    blockchain.sync_chain()

    # Start the network server thread.
    server_thread = threading.Thread(
        target=run_server,
        args=(args.host, args.port, blockchain, node_identifier),
        daemon=True
    )
    server_thread.start()

    # Start periodic synchronization including leader election.
    sync_thread = threading.Thread(target=periodic_sync, args=(blockchain,), daemon=True)
    sync_thread.start()

    sleep(1)

    # Launch the GUI.
    root = tk.Tk()
    app = BlockchainGUI(root, blockchain, node_identifier, args)
    root.mainloop()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
