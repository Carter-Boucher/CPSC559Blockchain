### Usage
Once the node is running, you’ll see an interactive menu with options:

1. Mine a New Block:
Initiates mining by performing the Proof of Work, adds a mining reward transaction, creates a new block, and broadcasts it.

2. Create a New Transaction:
Prompts for the sender, recipient, and amount to create and broadcast a new transaction.

3. Show Ledger:
Displays the confirmed blockchain and any pending transactions.

4. Register a New Node:
Allows you to register additional nodes into your network and fetch their pending transactions.

5. Resolve Conflicts:
Invokes the consensus algorithm to check for and replace the local chain with a longer valid chain from peers if needed.

6. Discover New Nodes:
Queries known peers for additional node addresses and updates your node list.

7. Exit:
Exits the application.

### Code Explanation
- Genesis Block:
The blockchain starts with a fixed genesis block. This block is hardcoded with preset values to initialize the chain.

- Transactions:
Transactions are initially marked as 'pending' and then updated to 'success' once they are included in a block. A canonical JSON representation is used for consistent verification across nodes.

- Proof of Work:
A simple Proof of Work algorithm is used. The goal is to find a nonce that, when combined with the last nonce and the hash of the last block, produces a SHA-256 hash with 4 leading zeroes.

- P2P Networking:
The system uses TCP sockets for node-to-node communication. Nodes exchange JSON-formatted messages to share blocks, transactions, and node information. This enables decentralized consensus and network expansion.

- Consensus and Conflict Resolution:
If a node discovers a longer valid chain from its peers, it will replace its local chain to maintain consistency with the majority of the network.

