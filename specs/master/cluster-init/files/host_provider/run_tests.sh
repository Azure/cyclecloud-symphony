#!/bin/bash

export PYTHONPATH=$( pwd )/src:$PYTHONPATH 

python test/cyclecloud_provider_test.py
