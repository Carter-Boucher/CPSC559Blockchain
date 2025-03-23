import json
import hashlib

def canonical_chain(chain):
    """
    Return a canonical JSON representation of the chain with sorted keys.
    """
    return json.dumps(chain, sort_keys=True)

def hash_chain(chain):
    """
    Compute a SHA-256 hash of the canonical representation of the chain.
    """
    canonical = canonical_chain(chain)
    return hashlib.sha256(canonical.encode()).hexdigest()

def compare_chains():
    # Load simulation results from the JSON file.
    with open("simulation_results.json", "r") as f:
        data = json.load(f)
    
    # Dictionary to store each node's chain hash.
    chain_hashes = {}
    
    # Iterate over each node's data.
    for address, node in data.items():
        chain = node.get("chain", [])
        chain_hash = hash_chain(chain)
        chain_hashes[address] = chain_hash
    
    # Print summary information: each node's chain hash.
    print("Chain hashes for each node:")
    for address, chash in chain_hashes.items():
        print(f"  {address}: {chash}")
    
    # Compare the hashes.
    unique_hashes = set(chain_hashes.values())
    
    if len(unique_hashes) == 1:
        print("\nAll nodes have identical chains.")
    else:
        print("\nNodes have differing chains:")
        # Group nodes by chain hash.
        hash_groups = {}
        for address, chash in chain_hashes.items():
            hash_groups.setdefault(chash, []).append(address)
        for chash, addresses in hash_groups.items():
            print(f"  Chain hash {chash} found in nodes: {addresses}")

if __name__ == "__main__":
    compare_chains()
