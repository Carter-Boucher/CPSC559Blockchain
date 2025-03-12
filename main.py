import argparse
import json
import socket
import threading
from time import sleep
from uuid import uuid4
import tkinter as tk

from blockchain import Blockchain
from network import run_server, send_message
from GUI import BlockchainGUI

def main():
    parser = argparse.ArgumentParser(description="Advanced P2P Blockchain Node with Electrum-like GUI (pure Python)")
    parser.add_argument('--host', default="127.0.0.1", help='Host address of this node')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses in host:port format')
    args = parser.parse_args()

    node_identifier = str(uuid4()).replace('-', '')
    blockchain = Blockchain()

    if args.peers:
        for peer in args.peers.split(','):
            peer = peer.strip()
            if peer:
                try:
                    blockchain.register_node(peer)
                    response = send_message(peer, {"type": "REGISTER_NODE", "node": f"{args.host}:{args.port}"}, expect_response=True)
                    if response and response.get("status") == "OK":
                        print(f"Registered with peer {peer}: {response.get('message')}")
                    else:
                        print(f"Could not register with peer {peer}.")
                    pending_response = send_message(peer, {"type": "GET_PENDING"}, expect_response=True)
                    if pending_response and pending_response.get("type") == "PENDING":
                        pending_from_peer = pending_response.get("pending", [])
                        for tx in pending_from_peer:
                            tx_str = json.dumps(tx, sort_keys=True)
                            local_tx_strs = [json.dumps(local_tx, sort_keys=True) for local_tx in blockchain.current_transactions]
                            if tx_str not in local_tx_strs:
                                blockchain.current_transactions.append(tx)
                    else:
                        print(f"No pending transactions received from {peer}.")
                except Exception as e:
                    print(f"Error registering with peer {peer}: {e}")

    server_thread = threading.Thread(target=run_server, args=(args.host, args.port, blockchain, node_identifier), daemon=True)
    server_thread.start()
    
    sleep(1)

    root = tk.Tk()
    app = BlockchainGUI(root, blockchain, node_identifier, args)
    root.mainloop()

if __name__ == '__main__':
    main()
