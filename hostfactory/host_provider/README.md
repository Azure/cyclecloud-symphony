## Creating a virtualenv for azurecc testing

```bash
    python3 -m venv ~/.virtualenvs/azurecc/
    . ~/.virtualenvs/azurecc/bin/activate

    # Get a copy of scalelib and install
    git clone https://github.com/Azure/cyclecloud-scalelib.git

    # Check the scalelib README for latest instructions on adding scalelib
    # to the venv
    pushd ./cyclecloud-scalelib
    
    # If Cyclecloud is installed on the current machine:
    # cp /opt/cycle_server/tools/cyclecloud_api*.whl .
    # pip install cyclecloud_api-8.6.5-py2.py3-none-any.whl

    pip install -r ./dev-requirements.txt
    pip install ./cyclecloud_api*.whl
    python setup.py build
    pip install -e .
    popd

    pip install concurrent_log_handler

```

## Running the tests
```bash
    . ~/.virtualenvs/azurecc/bin/activate

    export PYTHONPATH=$( pwd )/test:$( pwd )/src:$( pwd ):$PYTHONPATH 

    ./run_tests.sh test/cluster_test.py

```