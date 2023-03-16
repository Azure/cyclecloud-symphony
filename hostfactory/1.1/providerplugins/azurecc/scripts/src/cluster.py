import json

import logging

from builtins import str
from hpc.autoscale.node.nodemanager import new_node_manager

try:
    import cyclecli
except ImportError:
    import cyclecliwrapper as cyclecli
    

class Cluster:
    

    def __init__(self, cluster_name, provider_config, logger=None):
        self.cluster_name = cluster_name
        self.provider_config = provider_config
        self.logger = logger or logging.getLogger()
        CC_CONFIG = {}
        CC_CONFIG["url"] = self.provider_config.get("cyclecloud.config.web_server")
        CC_CONFIG["username"] = self.provider_config.get("cyclecloud.config.username")
        CC_CONFIG["password"] = self.provider_config.get("cyclecloud.config.password")
        CC_CONFIG["cluster_name"] = self.cluster_name
        self.node_mgr = new_node_manager(CC_CONFIG)
    
    def status(self):
        status_json = self.get("/clusters/%s/status" % self.cluster_name)
        #log the buckets, maxcorecount in nodearray
        nodearrays = status_json["nodearrays"]
        for nodearray_root in nodearrays:
            nodearray = nodearray_root.get("nodearray")
            if nodearray_root.get("name") == 'execute':
                self.logger.debug("maxCount %s maxCoreCount %s  of nodearray", nodearray_root.get("maxCount"), nodearray_root.get("maxCoreCount"))
                self.logger.debug("MaxCoreCount in nodearray execute %s", nodearray.get("MaxCoreCount"))
                self.logger.debug("Buckets of nodearray execute")
                self.logger.debug(json.dumps(nodearray_root.get("buckets")))
        return status_json

    def add_nodes(self, request, max_count):
        sku = request['sets'][0]['definition']['machineType']
        selector = {"node.nodearray": request['sets'][0]['nodearray']}
        if sku:
           selector["node.vm_size"] = sku
        selector_list = [selector]
        alloc_result = self.node_mgr.allocate(constraints=selector_list, node_count=request['sets'][0]['count'], allow_existing=False)
        filtered_nodes = [n for n in alloc_result.nodes if int(n.name.split("-")[-1]) <= max_count]
        exceeded_nodes = list(set(alloc_result.nodes) - set(filtered_nodes))
        if len(exceeded_nodes) > 0:
            self.logger.warning("In the allocation result %s nodes exceeded %s", len(exceeded_nodes), str(exceeded_nodes))
            for node in self.node_mgr.get_nodes():
                self.logger.debug("Node name %s Node state %s Node targetstate %s", node.name, node.state, node.target_state)
        # This was one method to fix it but its still causing the bug in customer environment.
        # curr_node_count = len(self.node_mgr.get_nodes())
        # for node in self.node_mgr.get_nodes():
        #     if node.state == "Deallocated":
        #         curr_node_count-=1
        # allowed_count = max_count - curr_node_count
        # request_count = request['sets'][0]['count']
        # self.logger.debug("Allowed count in add nodes %s max count %s curr_node_count %s", allowed_count, max_count, curr_node_count)
        # if request_count > allowed_count:   
        #     exceeded_count = max_count - request_count
        #     self.logger.warning("Max count is exceeded by %s Limiting the allowed additional nodes to %s", exceeded_count, allowed_count)
        #     request_count = allowed_count
        #alloc_result = self.node_mgr.allocate(constraints=selector_list, node_count=request_count, allow_existing=False)
        
        self.logger.debug("Request id in add nodes %s",request['requestId'])    
        request_id_start = f"{request['requestId']}-start"
        request_id_create = f"{request['requestId']}-create"
        bootpup_resp = self.node_mgr.bootup(nodes=alloc_result.nodes,
            request_id_start=request_id_start, request_id_create=request_id_create
        )
        self.logger.debug("node bootup %s",bootpup_resp)
        self.logger.debug("node bootup requestids %s",bootpup_resp.request_ids)
        if bootpup_resp.nodes is None or []:
            return False
        return (bootpup_resp)
    
    def all_nodes(self):
        all_nodes_json = self.get("/clusters/%s/nodes" % self.cluster_name)
        count_status = {}
        nodes = all_nodes_json['nodes']
        for node in nodes:
            node_status = node.get("Status")
            if  node_status in count_status:
                count_status[node_status] = count_status[node_status] + 1
            else:
                count_status[node_status] = 1
        self.logger.debug("Count of status in all nodes")
        self.logger.debug(count_status)
        # count by status
        return self.get("/clusters/%s/nodes" % self.cluster_name)
 
    def nodes(self, request_ids):
        responses = {}
        for request_id in request_ids:
            def _get_nodes_by_request_id(req_id, action):
                try:
                    affected_nodes = self.node_mgr.get_nodes_by_request_id(req_id)
                    self.logger.debug(f"Nodes %s %s", action, affected_nodes)
                    return affected_nodes
                except Exception as e:
                    if "No operation found for request id" in str(e):
                        self.logger.debug("No new nodes have been %s", action)
                    return None
            # : Optional[str]
            request_id_start = f"{request_id}-start"
            request_id_create = f"{request_id}-create"
            nodes_started = _get_nodes_by_request_id(request_id_start, "started")
            nodes_created = _get_nodes_by_request_id(request_id_create, "created")
            if nodes_created is None and nodes_started is None:
                raise RuntimeError("Could not find request id %s", request_id)
            responses[request_id] = (nodes_started or []) + (nodes_created or [])
        self.logger.debug(responses)
        return responses
    
    def nodes_by_operation_id(self, operation_id):
        if not operation_id:
            raise RuntimeError("You must specify operation id!")
        return self.get("/clusters/%s/nodes?operation=%s" % (self.cluster_name, operation_id))
    
    def get_node_id(self,node):
        return node.delayed_node_id.node_id

    def shutdown_nodes(self, machines):
        machine_ids = [machine["machineId"] for machine in machines]
        nodes_to_shutdown = [x for x in self.node_mgr.get_nodes() if x.delayed_node_id.node_id in machine_ids]
        self.node_mgr.shutdown_nodes(nodes_to_shutdown)

    def _session(self):
        config = {"verify_certificates": False,
                  "username": self._get_or_raise("cyclecloud.config.username"),
                  "password": self._get_or_raise("cyclecloud.config.password"),
                  "cycleserver": {
                      "timeout": 60
                  }
        }
        return cyclecli.get_session(config=config)
    
    def _get_or_raise(self, key):
        value = self.provider_config.get(key)
        if not value:
            #  jetpack.config.get will raise a ConfigError above.
            raise cyclecli.ConfigError("Please define key %s in the provider config." % key)
        return value
    
    def post(self, url, data=None, json=None, **kwargs):
        root_url = self._get_or_raise("cyclecloud.config.web_server")
        self.logger.debug("POST %s with data %s json %s kwargs %s", root_url + url, data, json, kwargs)
        session = self._session()
        response = session.post(root_url + url, data, json, **kwargs)
        response_content = response.content
        if response_content is not None and isinstance(response_content, bytes):
            response_content = response_content.decode()
        if response.status_code < 200 or response.status_code > 299:
            raise ValueError(response_content)
        return response_content
        
    def get(self, url, **params):
        root_url = self._get_or_raise("cyclecloud.config.web_server")
        self.logger.debug("GET %s with params %s", root_url + url, params)
        session = self._session()
        response = session.get(root_url + url, params=params)
        response_content = response.content
        if response_content is not None and isinstance(response_content, bytes):
            response_content = response_content.decode()

        if response.status_code < 200 or response.status_code > 299:
            raise ValueError(response_content)
        return json.loads(response_content)
