#!/usr/bin/env python3
"""Wrapper to run pipeline and capture output to a file."""
import subprocess
import sys
import os

os.chdir("/home/wahaj/.openclaw/workspace/thrift-cycle")

with open("/home/wahaj/.openclaw/workspace/thrift-cycle/pipeline_output.log", "w") as f:
    result = subprocess.run(
        ["python3", "pipeline.py"],
        stdout=f,
        stderr=subprocess.STDOUT,
        text=True
    )
    f.write(f"\n\nEXIT_CODE: {result.returncode}\n")

print("Pipeline complete. Check pipeline_output.log")
