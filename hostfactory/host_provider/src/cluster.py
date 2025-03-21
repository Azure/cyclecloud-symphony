import version
import json
import requests
from math import ceil, floor
import time
import logging
from util import ConfigError, UserError
from urllib.parse import urlencode
from builtins import str
from allocation_strategy import AllocationStrategy
from hpc.autoscale.node.nodemanager import new_node_manager
from hpc.autoscale.util import partition

try:
    from requests.packages import urllib3
    if hasattr(urllib3, "disable_warnings"):
        urllib3.disable_warnings()
except ImportError:
    pass


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
            self.logger.info(f"{b.nodearray}/{b.vm_size} available={b.available_count} based on {b.limits} bucket_id={b.bucket_id}  (last capacity failure {b.last_capacity_failure})")           
        return buckets

    def configure_node_resources_scalelib(self, use_weighted_templates=False, vm_types=None):
        if not vm_types:
            vm_types = {}

        # if true, do new slot based allocation with weighting
        # if false, use vm_size/node based allocation
        if use_weighted_templates:
            self.logger.debug("Using weighted templates")
            self.node_mgr.add_default_resource(selection={}, resource_name="template_id", default_value="node.nodearray")
            self.logger.debug("Current weightings: %s", ", ".join([f"{x}={y}" for x,y in vm_types.items()]))
            for vm_size, weight in vm_types.items():
                self.node_mgr.add_default_resource(selection={"node.vm_size": vm_size},
                                                   resource_name="weight",
                                                   default_value=weight)
        else:    
            self.node_mgr.add_default_resource(selection={}, resource_name="template_id", 
                                               default_value=lambda node: "{node.nodearray + node.vm_size.replace('_', '')}".lower())
            self.node_mgr.add_default_resource(selection={}, resource_name="weight", default_value=1)

    def add_nodes(self, request_id, template_id, requested_slot_count, use_weighted_templates=False, vm_types={},
                  capacity_limit_timeout=300, autoscaling_strategy="price", dry_run=False):

        # Add custom resources for nodes in scalelib (each pass may be a new process, so do this each time)
        self.configure_node_resources_scalelib(use_weighted_templates, vm_types)

        allocation_strategy = AllocationStrategy(self.node_mgr, self.provider_config, strategy=autoscaling_strategy,
                                                 capacity_limit_timeout=capacity_limit_timeout, logger=self.logger)
        allocation_results = allocation_strategy.allocate_slots(requested_slot_count, template_id, vm_types)

        by_vm_size = partition(self.node_mgr.new_nodes, lambda node: node.vm_size)
        for key,value in by_vm_size.items():
            self.logger.info("Requesting %s nodes of %s", len(value), key)

        if dry_run:
            self.logger.info("Dry run: Would have booted %s nodes", len(self.node_mgr.new_nodes))
            return True
        if allocation_results:
            request_id_start = f"{request_id}-start"
            request_id_create = f"{request_id}-create"
            result = self.node_mgr.bootup(request_id_start=request_id_start, request_id_create=request_id_create)
            return result
        return False


    def all_nodes(self):
        all_nodes_json = self.get(f"/clusters/{self.cluster_name}/nodes")
        count_status = {}
        nodes = all_nodes_json['nodes']
        for node in nodes:
            node_status = node.get("Status")
            if node_status in count_status:
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
                    self.logger.debug("Nodes %s %s", action, affected_nodes)
                    return affected_nodes
                except Exception as e:
                    if "No operation found for request id" in str(e):
                        self.logger.debug("No new nodes have been %s", action)
                        return None 
                    raise
                    
            # : Optional[str]
            request_id_start = f"{request_id}-start"
            request_id_create = f"{request_id}-create"
            nodes_started = _get_nodes_by_request_id(request_id_start, "started")
            nodes_created = _get_nodes_by_request_id(request_id_create, "created")
            if nodes_created is None and nodes_started is None:
                raise RuntimeError(f"Could not find request id {request_id}")

            responses[request_id] = []
            if nodes_started: 
                responses[request_id].extend(nodes_started)
            if nodes_created: 
                responses[request_id].extend(nodes_created)
            self.logger.debug(responses)
        return responses
    
    def nodes_by_operation_id(self, operation_id):
        if not operation_id:
            raise RuntimeError("You must specify operation id!")
        return self.get(f"/clusters/{self.cluster_name}/nodes?operation={operation_id}")
    
    def get_node_id(self,node):
        return node.delayed_node_id.node_id

    def shutdown_nodes(self, machines):
        machine_ids = [machine["machineId"] for machine in machines]
        nodes_to_shutdown = [x for x in self.node_mgr.get_nodes() if x.delayed_node_id.node_id in machine_ids]
        self.node_mgr.shutdown_nodes(nodes_to_shutdown)
        
    def terminate(self, machines):
        machine_ids = [machine["machineId"] for machine in machines]
        response_raw = self.post(f"/clusters/{self.cluster_name}/nodes/terminate", json={"ids": machine_ids})
        try:
            self.logger.info("Terminate Response: %s", response_raw)
            return json.loads(response_raw)
        except Exception as exc:
            raise RuntimeError(f"Could not parse response as json to terminate! '{response_raw}'") from exc
            
    def _session(self):
        config = {"verify_certificates": False,
                  "username": self._get_or_raise("cyclecloud.config.username"),
                  "password": self._get_or_raise("cyclecloud.config.password"),
        }
        retries = 3
        while retries > 0:
            try:
                s = requests.session()
                s.auth = (config["username"], config["password"])
                s.timeout = 60
                s.verify = config["verify_certificates"]  # Should we auto-accept unrecognized certs?
                s.headers = {"X-Cycle-Client-Version": f"cyclecloud-symphony:{version.get_version()}"}
                return s
            except requests.exceptions.SSLError:
                retries = retries - 1
                if retries < 1:
                    raise
    
    def _get_or_raise(self, key):
        value = self.provider_config.get(key)
        if not value:
            #  jetpack.config.get will raise a ConfigError above.
            raise ConfigError(f"Please define key {key} in the provider config.")
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
