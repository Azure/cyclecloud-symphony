import json

import logging
from urllib.parse import urlencode
from builtins import str


try:
    import cyclecli
except ImportError:
    import cyclecliwrapper as cyclecli
    

class Cluster:
    
    def __init__(self, cluster_name, provider_config, logger=None):
        self.cluster_name = cluster_name
        self.provider_config = provider_config
        self.logger = logger or logging.getLogger()
    
    def status(self):
        '''pprint.pprint(json.dumps(json.loads(dougs_example)))'''
        return self.get("/clusters/%s/status" % self.cluster_name)

    def add_nodes(self, request):
        response_raw = self.post("/clusters/%s/nodes/create" % self.cluster_name, json=request)
        try:
            return json.loads(response_raw)
        except:
            raise RuntimeError("Could not parse response as json to create_nodes! '%s'" % response_raw)
    
    def all_nodes(self):
        return self.get("/clusters/%s/nodes" % self.cluster_name)

    def nodes(self, request_ids):
        responses = {}
        for request_id in request_ids:
            responses[request_id] = self.get("/clusters/%s/nodes" % self.cluster_name, request_id=request_id)
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
