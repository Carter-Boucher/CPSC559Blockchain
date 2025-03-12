import argparse
import json
import threading
from time import sleep
from uuid import uuid4
import tkinter as tk
import logging

from blockchain import Blockchain
from network import run_server, send_message
from GUI import BlockchainGUI

# Optional: Try to import miniupnpc for UPnP support.
try:
    import miniupnpc
except ImportError:
    miniupnpc = None

def setup_upnp(port):
    """
    Attempt to set up UPnP port mapping.
    Returns the external IP if mapping is successful, or None otherwise.
    """
    if miniupnpc is None:
        logging.warning("miniupnpc not installed. Skipping UPnP port mapping.")
        return None

    try:
        u = miniupnpc.UPnP()
        u.discoverdelay = 200
        num_devices = u.discover()
        u.selectigd()
        external_ip = u.externalipaddress()
        u.addportmapping(port, 'TCP', u.lanaddr, port, 'Blockchain Node', '')
        logging.info(f"UPnP mapping successful: External IP {external_ip}, Port {port}")
        return external_ip
    except Exception as e:
        logging.warning(f"UPnP port mapping failed: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(
        description="Advanced P2P Blockchain Node with Electrum-like GUI (pure Python)"
    )
    parser.add_argument('--host', default="127.0.0.1", help='Local IP address of this node')
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    parser.add_argument('--peers', default="", help='Comma-separated list of peer addresses (host:port)')
    parser.add_argument('--no-listen', action='store_true', help='Run in outbound-only mode (don\'t accept inbound connections)')
    args = parser.parse_args()

    node_identifier = str(uuid4()).replace('-', '')
    blockchain = Blockchain()

    # If UPnP is available and the node is not in outbound-only mode, try to map the port.
    if not args.no_listen:
        external_ip = setup_upnp(args.port)
        if external_ip:
            # If UPnP mapping succeeded, override the host to the external IP for peer registration.
            logging.info(f"Using external IP for peer registration: {external_ip}")
            args.host = external_ip

    # Register with peers (for outbound connections) if any are provided.
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

    # Start the server if not in outbound-only mode.
    if not args.no_listen:
        server_thread = threading.Thread(
            target=run_server,
            args=(args.host, args.port, blockchain, node_identifier),
            daemon=True
        )
        server_thread.start()
        logging.info(f"Server listening on {args.host}:{args.port}")
    else:
        logging.info("Running in outbound-only mode. Inbound connections will not be accepted.")

    # Allow time for the server (if any) to start.
    sleep(1)

    # Start the GUI.
    root = tk.Tk()
    app = BlockchainGUI(root, blockchain, node_identifier, args)
    root.mainloop()

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    main()
