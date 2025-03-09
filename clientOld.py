import requests
import json

# Default base URL for the node. Change if needed.
BASE_URL = "http://127.0.0.1:5000"

def mine_block():
    """Call the /mine endpoint to mine a new block."""
    url = f"{BASE_URL}/mine"
    response = requests.get(url)
    print("\nMine Response:")
    print(json.dumps(response.json(), indent=4))

def new_transaction():
    """Call the /transactions/new endpoint to create a new transaction."""
    url = f"{BASE_URL}/transactions/new"
    sender = input("Enter sender address: ")
    recipient = input("Enter recipient address: ")
    amount = input("Enter amount: ")
    try:
        amount = float(amount)
    except ValueError:
        print("Invalid amount. Using 0.")
        amount = 0.0

    payload = {
        "sender": sender,
        "recipient": recipient,
        "amount": amount
    }
    response = requests.post(url, json=payload)
    print("\nTransaction Response:")
    print(json.dumps(response.json(), indent=4))

def get_chain():
    """Call the /chain endpoint to retrieve the blockchain."""
    url = f"{BASE_URL}/chain"
    response = requests.get(url)
    print("\nFull Blockchain:")
    print(json.dumps(response.json(), indent=4))

def nodes_list():
    """Call the /nodes/list endpoint to retrieve the list of nodes."""
    url = f"{BASE_URL}/nodes/list"
    response = requests.get(url)
    print("\nNode List:")
    print(json.dumps(response.json(), indent=4))

def register_node():
    """Call the /nodes/register endpoint to add new peer nodes."""
    url = f"{BASE_URL}/nodes/register"
    nodes_str = input("Enter comma-separated list of node URLs to register: ")
    nodes = [node.strip() for node in nodes_str.split(',') if node.strip()]
    payload = {"nodes": nodes}
    response = requests.post(url, json=payload)
    print("\nRegister Node Response:")
    print(json.dumps(response.json(), indent=4))

def resolve_conflicts():
    """Call the /nodes/resolve endpoint to trigger the consensus algorithm."""
    url = f"{BASE_URL}/nodes/resolve"
    response = requests.get(url)
    print("\nResolve Conflicts Response:")
    print(json.dumps(response.json(), indent=4))

def main():
    global BASE_URL
    user_url = input(f"Enter the base URL of your blockchain node (default {BASE_URL}): ").strip()
    if user_url:
        BASE_URL = user_url

    while True:
        print("\n=== Blockchain Client Menu ===")
        print("1. Mine a new block (/mine)")
        print("2. Create a new transaction (/transactions/new)")
        print("3. Get full blockchain (/chain)")
        print("4. Get list of nodes (/nodes/list)")
        print("5. Register new nodes (/nodes/register)")
        print("6. Resolve conflicts (/nodes/resolve)")
        print("7. Exit")
        choice = input("Enter your choice: ")

        if choice == "1":
            mine_block()
        elif choice == "2":
            new_transaction()
        elif choice == "3":
            get_chain()
        elif choice == "4":
            nodes_list()
        elif choice == "5":
            register_node()
        elif choice == "6":
            resolve_conflicts()
        elif choice == "7":
            print("Exiting the client.")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == '__main__':
    main()
