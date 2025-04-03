import os
import sys
import docker
import json


client = docker.from_env()
pro_image_name = os.getenv("PRO_IMAGE_TAG")
pro_script_dir = os.getenv("PRO_SCRIPTDIR")
if "AZURECC_CONTAINER_NAME" not in os.environ:
    container_list = client.containers.list(filters={"ancestor": pro_image_name})
    container_name = container_list[0].name
else:  
    container_name = os.getenv('AZURECC_CONTAINER_NAME')
container = client.containers.get(container_name)
result = container.exec_run( pro_script_dir + "/invoke_provider.sh " + " ".join(sys.argv[1:]))

# Store the output
output = result.output.decode('utf-8')

# Parse the JSON output
try:
    json_output = json.loads(output)
    print(json.dumps(json_output, indent=4))  # Pretty print the JSON
except json.JSONDecodeError as e:
    print(f"Failed to parse JSON: {e}")