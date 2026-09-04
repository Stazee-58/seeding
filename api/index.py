import os
import sys

# Thêm thư mục cha vào sys.path để nạp server.py và các module liên quan
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Vercel nhận diện biến `app` là WSGI/ASGI handler
from server import app
