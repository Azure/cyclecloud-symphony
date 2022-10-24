import json

import logging
from urllib.parse import urlencode
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
        return self.get("/clusters/%s/status" % self.cluster_name)
    
    #old add nodes function
    # def add_nodes(self, request):
    #     self.logger.debug(request)
    #     response_raw = self.post("/clusters/%s/nodes/create" % self.cluster_name, json=request)
    #     try:
    #         return json.loads(response_raw)
    #     except:
    #         raise RuntimeError("Could not parse response as json to create_nodes! '%s'" % response_raw)
    
    def add_nodes(self,request):
        sku=request['sets'][0]['definition']['machineType']
        selector = {"node.nodearray": request['sets'][0]['nodearray']}
        if sku:
          selector["node.vm_size"] = sku
        self.logger.debug(request)
        r=self.node_mgr.allocate(selector, node_count=request['sets'][0]['count'])
        self.logger.debug("Request id in add nodes %s",request['requestId'])

        request_id_start = f"{request['requestId']}-start"
        request_id_create = f"{request['requestId']}-create"
        bootpup_resp=self.node_mgr.bootup(
            request_id_start=request_id_start, request_id_create=request_id_create
        )
        self.logger.debug("node bootup %s",bootpup_resp)
        self.logger.debug("node bootup requestids %s",bootpup_resp.request_ids)
        return (r)
    
    def all_nodes(self):
        return self.get("/clusters/%s/nodes" % self.cluster_name)
    # old nodes function
    # def nodes(self, request_ids):
    #     responses = {}
    #     for request_id in request_ids:
    #        # responses[request_id] = self.get("/clusters/%s/nodes" % self.cluster_name, request_id=f"{request_id}-start")
    #         responses[request_id]=self.get("/clusters/%s/nodes" % self.cluster_name, request_id=f"{request_id}-create")
    #         self.logger.debug(responses)
    #     return responses
    
    def nodes(self, request_ids):
        responses = {}
        for request_id in request_ids:
          request_id_start = f"{request_id}-start"
          request_id_create = f"{request_id}-create"
          try:
            nodes_started = self.node_mgr.get_nodes_by_request_id(request_id_start)
            try:
               nodes_created = self.node_mgr.get_nodes_by_request_id(request_id_create)
               nodes = nodes_started+nodes_created
               self.logger.debug("Nodes started and created %s",nodes)
               responses[request_id]=nodes
            except Exception as e:
               if "No operation found for request id" in str(e):
                  self.logger.debug("No new nodes have been created")
               self.logger.debug("Nodes started %s",nodes_started)
               responses[request_id]=nodes_started
          except Exception as e:
            if "No operation found for request id" in str(e):
                self.logger.debug("Initially created vm")
                nodes_created = self.node_mgr.get_nodes_by_request_id(request_id_create)
                self.logger.debug("Nodes created %s",nodes_created)
                responses[request_id]=nodes_created
            else:
                raise RuntimeError("Could not find request id %s",request_id)
        self.logger.debug(responses)
        return responses
    
    def nodes_by_operation_id(self, operation_id):
        if not operation_id:
            raise RuntimeError("You must specify operation id!")
        return self.get("/clusters/%s/nodes?operation=%s" % (self.cluster_name, operation_id))

    def terminate(self, machines):
        machine_ids = [machine["machineId"] for machine in machines]
        response_raw = self.post("/clusters/%s/nodes/terminate" % self.cluster_name, json={"ids": machine_ids})
        try:
            self.logger.info("Terminate Response: %s", response_raw)
            return json.loads(response_raw)
        except:
            raise RuntimeError("Could not parse response as json to terminate! '%s'" % response_raw)

        # It appears that the "instance-filter" version NEVER succeeds and often throws
        # kludge: work around
        # if Symphony may have a stale machineId -> hostname mapping, so find the existing instance with that hostname and kill it
        # machine_names = [ machine["name"].split(".")[0] for machine in machines if machine.get("name") ]
        # if machine_names:
        #     self.logger.warning("Terminating the following nodes by machine_names: %s", machine_names)

        #     f = urlencode({"instance-filter": 'HostName in {%s}' % ",".join('"%s"' % x for x in machine_names)})
        #     try:
        #         self.post("/cloud/actions/terminate_node/%s?%s" % (self.cluster_name, f))
        #     except Exception as e:
        #         if "No instances were found matching your query" in str(e):
        #            return
        #         raise
    def deallocate(self,machines):
        machine_ids = [machine["machineId"] for machine in machines]
        for machine_id in machine_ids:
         self.logger.debug("machine id %s",machine_id)
         self.node_mgr.deallocate_nodes([x for x in self.node_mgr.get_nodes() if x.delayed_node_id.node_id==machine_id]);

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
