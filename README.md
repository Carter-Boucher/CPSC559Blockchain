#### Blockchain Structure and Transactions:
Each block contains an index, timestamp, list of transactions, nonce, previous hash, and its own hash is computed using SHA-256. New transactions are stored until a block is mined, at which point they are added to the new block.


#### Proof of Work and Consensus:
The mining process uses a Proof-of-Work algorithm that requires the hash of a combination of the previous nonce, the new nonce, and the previous block’s hash to have four leading zeroes. The consensus endpoint (/nodes/resolve) checks all registered nodes and replaces the current chain with the longest valid chain.

#### Networking and API Layer:
A Flask API exposes endpoints for:

- GET /mine: Mining a new block.
- POST /transactions/new: Adding new transactions.
- GET /chain: Retrieving the full blockchain.
- GET /nodes/list: List known nodes
- POST /nodes/register: Registering new peer nodes.
- GET /nodes/resolve: Resolving conflicts in the blockchain.

These endpoints allow for peer-to-peer communication and network synchronization.


#### Running code
run startnodes batch file and 