#!/bin/bash
source ~/.bashrc
cd "$(dirname "$0")"
venv/bin/python invoice.py
