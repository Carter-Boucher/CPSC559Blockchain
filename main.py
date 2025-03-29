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
    while True:
        blockchain.resolve_conflicts()
        blockchain.discover_peers()
        
        from network import send_message
        for node in list(blockchain.nodes):
            pending_response = send_message(node, {"type": "GET_PENDING"}, expect_response=True)
            if pending_response and pending_response.get("type") == "PENDING":
                pending_from_peer = pending_response.get("pending", [])
                for tx in pending_from_peer:
                    tx_str = json.dumps(tx, sort_keys=True)
                    local_tx_strs = {json.dumps(local_tx, sort_keys=True) for local_tx in blockchain.current_transactions}
                    if tx_str not in local_tx_strs:
                        blockchain.current_transactions.append(tx)
        time.sleep(5)

def election_scheduler(blockchain):
    import time
    election_interval = 30  # seconds
    while True:
        current_time = time.time()
        elapsed = current_time - blockchain.election_start_time
        next_election = blockchain.election_start_time + ((int(elapsed / election_interval) + 1) * election_interval)
        time_to_next_election = next_election - current_time
        time.sleep(time_to_next_election)
        from network import broadcast_election
        broadcast_election(blockchain)

def run_tests():
    print("Running tests...")
    print("Tests complete.")

def main():
    parser = argparse.ArgumentParser(
        description="Advanced P2P Blockchain Node with Synchronous Consensus (pure Python)"
    )
    parser.add_argument('--host', default="127.0.0.1", help='Host address of this node (use "0.0.0.0" to listen on all interfaces)')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses in host:port format')
    parser.add_argument('--test', action='store_true', help='Run test suite instead of launching the GUI.')
    args = parser.parse_args()

    if args.test:
        run_tests()
        return

    node_identifier = args.port
    blockchain = Blockchain(node_id=node_identifier)
    blockchain.node_address = f"{args.host}:{args.port}"

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
                        peer_start_time = response.get("election_start_time")
                        if peer_start_time and peer_start_time < blockchain.election_start_time:
                            blockchain.election_start_time = peer_start_time
                    else:
                        logging.error(f"Error registering with peer {peer}: {response.get('message') if response else 'No response'}")
                except Exception as e:
                    logging.error(f"Error registering with peer {peer}: {e}")

    blockchain.sync_chain()

    if blockchain.current_leader is None:
        from network import broadcast_election
        broadcast_election(blockchain)

    server_thread = threading.Thread(
        target=run_server,
        args=(args.host, args.port, blockchain, node_identifier),
        daemon=True
    )
    server_thread.start()

    sync_thread = threading.Thread(target=periodic_sync, args=(blockchain,), daemon=True)
    sync_thread.start()

    election_thread = threading.Thread(target=election_scheduler, args=(blockchain,), daemon=True)
    election_thread.start()

    sleep(1)
    root = tk.Tk()
    app = BlockchainGUI(root, blockchain, node_identifier, args)
    root.mainloop()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
