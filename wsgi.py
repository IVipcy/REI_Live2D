# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from application import application, socketio

if __name__ == "__main__":
    socketio.run(application, debug=False, host='0.0.0.0', port=5000)
