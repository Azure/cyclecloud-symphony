#!/bin/bash -x

export PYTHONPATH=$( pwd )/test:$( pwd )/src:$( pwd ):$PYTHONPATH 


python test/cyclecloud_provider_test.py "$@"
