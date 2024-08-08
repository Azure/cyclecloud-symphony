import json
import time
import logging
from urllib.parse import urlencode
from builtins import str
from copy import deepcopy
from hpc.autoscale.node.nodemanager import new_node_manager
from hpc.autoscale.util import partition


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

        nodearrays = status_json["nodearrays"]
        #log the buckets of nodearray
        debug_nas = self.provider_config.get("debug_nodearrays") or []
        for nodearray_root in nodearrays:
            if debug_nas and nodearray_root.get("name") in debug_nas:
                self.logger.debug("Buckets of nodearray execute %s", nodearray_root.get("name"))
                self.logger.debug(json.dumps(nodearray_root))
        return status_json
    
    def get_buckets(self):
        buckets = self.node_mgr.get_buckets()
        self.logger.debug("Buckets: count=%d", len(buckets))
        for b in buckets:
            self.logger.debug(f"{b.nodearray}/{b.vm_size} available={b.available_count} based on {b.limits} bucket_id={b.bucket_id}")           
        return buckets
    
    def add_nodes_scalelib(self, request, template_id, use_weighted_templates=False, vmTypes={}, capacity_limit_timeout=300, dry_run=False):
        # if true, do new slot based allocation with weighting
        # if false, use vm_size/node based allocation
        if use_weighted_templates:
            self.logger.debug("Using weighted templates")
            self.node_mgr.add_default_resource(selection={}, resource_name="template_id", default_value="node.nodearray")
            self.logger.debug("Current weightings: %s", ", ".join([f"{x}={y}" for x,y in vmTypes.items()]))
            for vm_size, weight in vmTypes.items():
                self.node_mgr.add_default_resource(selection={"node.vm_size": vm_size},
                                            resource_name="weight",
                                            default_value=weight)
        else:    
            self.node_mgr.add_default_resource(selection={}, resource_name="template_id", 
                                        default_value=lambda node: "{node.nodearray + node.vm_size.replace('_', '')}".lower())
            self.node_mgr.add_default_resource(selection={}, resource_name="weight", default_value=1)
        
        # Time in seconds to check waiting period after last capacity failure
        result = self.node_mgr.allocate({"weight": 1, "template_id": template_id, "capacity-failure-backoff": capacity_limit_timeout},
                                slot_count=request['sets'][0]['count'],
                                allow_existing=False)
        self.logger.debug("Result of allocation %s", result)
        
        if dry_run:
            by_vm_size = partition(result.nodes, lambda node: node.vm_size)
            for key,value in by_vm_size.items():
                self.logger.debug("VM Size %s count %s", key, len(value))
                print("Allocation result:")
                print (key, len(value))
            return True
        if result:
            request_id_start = f"{request['requestId']}-start"
            request_id_create = f"{request['requestId']}-create"
            return self.node_mgr.bootup(request_id_start=request_id_start, request_id_create=request_id_create)
        return False
            
    
    def add_nodes(self, request, use_weighted_templates=False, vmTypes={}, capacity_limit_timeout=300, dry_run=False):
        response = self.add_nodes_scalelib(request, template_id=request['sets'][0]['definition']['templateId'],
                                              use_weighted_templates=use_weighted_templates, vmTypes=vmTypes, capacity_limit_timeout=capacity_limit_timeout, dry_run=dry_run)
        return response
    
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
        return all_nodes_json
 
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

            responses[request_id] = []
            if nodes_started: responses[request_id].extend( nodes_started )
            if nodes_created: responses[request_id].extend( nodes_created )
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
        
    def terminate(self, machines):
        machine_ids = [machine["machineId"] for machine in machines]
        response_raw = self.post("/clusters/%s/nodes/terminate" % self.cluster_name, json={"ids": machine_ids})
        try:
            self.logger.info("Terminate Response: %s", response_raw)
            return json.loads(response_raw)
        except:
            raise RuntimeError("Could not parse response as json to terminate! '%s'" % response_raw)
            
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
