@REM start python main.py --host 127.0.0.1 --port 5000
@REM start python main.py --host 127.0.0.1 --port 5001 --peers 127.0.0.1:5000



start python main.py --host 127.0.0.1 --port 5000
start python main.py --host 127.0.0.1 --port 5001 --peers "127.0.0.1:5000"
@REM start python main.py --host 127.0.0.1 --port 5002 --peers "127.0.0.1:5000,127.0.0.1:5001"
