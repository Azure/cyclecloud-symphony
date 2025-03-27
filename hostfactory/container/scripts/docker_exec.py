import os
import sys
import docker


client = docker.from_env()
pro_image_name = os.getenv("PRO_IMAGE_TAG")
pro_script_dir = os.getenv("PRO_SCRIPTDIR")
if "AZURECC_CONTAINER_NAME" not in os.environ:
    print("AZURECC_CONTAINER_NAME not set, using first azurecc container found")   
    container_list = client.containers.list(filters={"ancestor": pro_image_name})
    container_name = container_list[0].name
else:  
    container_name = os.getenv('AZURECC_CONTAINER_NAME')
container = client.containers.get(container_name)
print(container.exec_run( pro_script_dir + "/invoke_provider.sh " + " ".join(sys.argv[1:])))