start python blockchain.py --host 127.0.0.1 --port 5000 --peers "http://127.0.0.1:5001,http://127.0.0.1:5002"
start python blockchain.py --host 127.0.0.1 --port 5001 --peers "http://127.0.0.1:5000,http://127.0.0.1:5002"
::start python blockchain.py --host 127.0.0.1 --port 5002 --peers "http://127.0.0.1:5000,http://127.0.0.1:5001"
