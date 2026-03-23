#!/bin/bash

uvicorn pt_chat_frontend:app --host 0.0.0.0 --port 3000 --reload --timeout-graceful-shutdown 0
