import argparse

import uvicorn

parser = argparse.ArgumentParser(description="Isolated SAQ QURYLYS local demonstration")
parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
uvicorn.run("local_demo.app:create_local_app", factory=True, host=args.host, port=args.port)
