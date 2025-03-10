@REM start python blockchain.py --host 127.0.0.1 --port 5000
@REM start python blockchain.py --host 127.0.0.1 --port 5001 --peers 127.0.0.1:5000


@echo off
REM ================================================================
REM This batch file launches two blockchain nodes and simulates
REM interaction with the blockchain network.
REM Node 1: Runs on port 5000.
REM Node 2: Runs on port 5001 and registers Node 1 as a peer.
REM ================================================================

echo Starting Blockchain Node 1 on port 5000...
start "Blockchain Node 1" cmd /k "python blockchain.py --host 127.0.0.1 --port 5000"

REM Wait a few seconds to allow Node 1 to initialize.
timeout /t 3 > nul

echo Starting Blockchain Node 2 on port 5001 with peer 127.0.0.1:5000...
start "Blockchain Node 2" cmd /k "python blockchain.py --host 127.0.0.1 --port 5001 --peers 127.0.0.1:5000"

echo.
echo Both nodes have been started.
echo.
echo You can interact with each node using their on-screen menu:
echo  - Option 1: Mine a new block
echo  - Option 2: Create a new transaction
echo  - Option 3: Show the ledger
echo  - Option 4: Register a new node
echo  - Option 5: Resolve conflicts with peers
echo  - Option 6: Discover new nodes
echo  - Option 7: Exit the node
echo.
pause
