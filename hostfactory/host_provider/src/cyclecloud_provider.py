import time
import calendar
from collections import OrderedDict
from copy import deepcopy
import difflib
import json
import os
import pprint
import sys
import uuid
from builtins import str
import weighted_template_parse


from symphony import RequestStates, MachineStates, MachineResults
import cluster
from request_tracking_db import RequestTrackingDb
from util import JsonStore, failureresponse
import util
from util import UserError
import symphony
import version


logger = None

PLACEHOLDER_TEMPLATE = {"templateId": "exceptionPlaceholder", 
                        "maxNumber": 1,
                        "attributes": {
                            "mem": ["Numeric", 1024],
                            "ncpus": ["Numeric", 1],
                            "ncores": ["Numeric", 1],
                            "type" : [ "String", "X86_64" ]
                            }
                        }


class InvalidCycleCloudVersionError(RuntimeError):
    pass


def quiet_output():
    '''Return a JsonOutputHandler that does not print to stdout and still can only be invoked once'''
    return JsonOutputHandler(quiet=True)


class CycleCloudProvider:
    
    def __init__(self, config, cluster, hostnamer, stdout_handler, terminate_requests, creation_requests, clock):
        self.config = config
        self.cluster = cluster
        self.hostnamer = hostnamer
        self.stdout_handler = stdout_handler
        self.terminate_json = terminate_requests
        self.creation_json = creation_requests
        self.exit_code = 0
        self.clock = clock
        self.termination_timeout = float(self.config.get("cyclecloud.termination_request_retirement", 120) * 60)
        self.creation_request_ttl = int(self.config.get("symphony.creation_request_ttl", 40 * 60))
        self.node_request_timeouts = float(self.config.get("cyclecloud.machine_request_retirement", 120) * 60)
        self.capacity_limit_timeout = int(self.config.get("cyclecloud.capacity_limit_timeout", 5) * 60)
        self.autoscaling_strategy = self.config.get("symphony.autoscaling.strategy", "price")
        self.symphony_ncpus = int(self.config.get("symphony.autoscaling.ncpus", 1))
        self.symphony_ncores = int(self.config.get("symphony.autoscaling.ncores", 1))
        self.symphony_nram = int(self.config.get("symphony.autoscaling.nram", 4096))
        self.fine = False
        self.request_tracker = RequestTrackingDb(self.config, self.cluster.cluster_name, self.clock)
        self.weighted_template = weighted_template_parse.WeightedTemplates(logger)
        self.dry_run = False

        logger.info("Using %s based autoscaling strategy", self.autoscaling_strategy)
        
    def _escape_id(self, name):
        return name.lower().replace("_", "")
    
     
    # If we return an empty list or templates with 0 hosts, it removes us forever and ever more, so _always_
    # return at least one machine.
    # BUGFIX: exiting non-zero code will make symphony retry.
    def templates(self): 
        try:
            pro_conf_dir = os.getenv('PRO_CONF_DIR', os.getcwd())
            conf_path = os.path.join(pro_conf_dir, "conf", "azureccprov_templates.json")
            with open(conf_path, 'r') as json_file:
                templates_json = json.load(json_file)
            templates_json["message"] = "Get available templates success."   
            return self.stdout_handler.handle(templates_json, debug_output=False)
        except:
            logger.warning("Exiting Non-zero so that symphony will retry")
            logger.exception(f"Could not get azureccprov_templates.json at {conf_path}")
            sys.exit(1) 
    
    def generate_sample_template(self):
        buckets = self.cluster.get_buckets()  
        template_dict = {}
        for bucket in buckets:
            autoscale_enabled = bucket.software_configuration.get("autoscaling", {}).get("enabled", False)
            if not autoscale_enabled:
                print("Autoscaling is disabled in CC for nodearray %s" % bucket.nodearray, file=sys.stderr)
                continue    
            if template_dict.get(bucket.nodearray) is None:
                template_dict[bucket.nodearray] = {}
                template_dict[bucket.nodearray]["templateId"] = bucket.nodearray
                template_dict[bucket.nodearray]["attributes"] = {}
                template_dict[bucket.nodearray]["attributes"]["type"] = ["String", "X86_64"]
                template_dict[bucket.nodearray]["attributes"]["nram"] = ["Numeric", "%d" % self.symphony_nram]
                template_dict[bucket.nodearray]["attributes"]["ncpus"] = ["Numeric","%d" % self.symphony_ncpus]
                template_dict[bucket.nodearray]["attributes"]["ncores"] = ["Numeric", "%d" % self.symphony_ncores]
                template_dict[bucket.nodearray]["vmTypes"] = {}
                if self.config.get("symphony.ncpus_use_vcpus", True):
                    weight = int(bucket.resources.get("ncores", bucket.vcpu_count)/ self.symphony_ncpus)
                else:
                    weight = int(bucket.resources.get("ncores", bucket.pcpu_count)/ self.symphony_ncpus)
                # Here maxNumber is defined based on SKU with lowest weight.
                template_dict[bucket.nodearray]["maxNumber"] = max(template_dict[bucket.nodearray].get("maxNumber", 0), bucket.max_count * bucket.vcpu_count)
                template_dict[bucket.nodearray]["vmTypes"].update({bucket.vm_size: weight})
            else:
                weight = int(bucket.resources.get("ncores", bucket.vcpu_count)/ self.symphony_ncpus)
                template_dict[bucket.nodearray]["vmTypes"].update({bucket.vm_size: weight})
        templates = {"templates": list(template_dict.values())}
        print(json.dumps(templates, indent=4))

            
    @failureresponse({"requests": [], "status": RequestStates.running})
    def create_machines(self, input_json):
        """
        input:
        {'rc_account': 'default',
         'template': {'machineCount': 1, 'templateId': 'execute0'},
         'user_data': {}}

        output:
        {'message': 'Request VM from Azure CycleCloud successful.',
         'requestId': 'req-123'}
        """ 
        request_id = str(uuid.uuid4())
        logger.info("Creating requestId %s", request_id)
        if not self.dry_run:
            try:
                # save the request so we can time it out
                with self.creation_json as requests_store:
                    requests_store[request_id] = {"requestTime": calendar.timegm(self.clock()),
                                                "completedNodes": [],
                                                "allNodes": None,
                                                "completed": False}
            except:
                logger.exception("Could not open creation_json")
                sys.exit(1)    
        try:            
            use_weighted_templates = False
            vmTypes = {}
            if self.config.get("symphony.enable_weighted_templates", True):
                pro_conf_dir = os.getenv('PRO_CONF_DIR', os.getcwd())
                conf_path = os.path.join(pro_conf_dir, "conf", "azureccprov_templates.json")
                with open(conf_path, 'r') as json_file:
                    templates_json = json.load(json_file)
                vmTypes = self.weighted_template.parse_weighted_template(input_json, templates_json["templates"])
                logger.debug("Current weightings: %s", ", ".join([f"{x}={y}" for x,y in vmTypes.items()]))
                use_weighted_templates = True 
                request_set = { 'count': input_json["template"]["machineCount"],
                                 'definition':{'templateId':input_json["template"]["templateId"]}} 
            
            # We are grabbing the lock to serialize this call.
            try:
                with self.creation_json as requests_store:
                    template_id = request_set['definition']['templateId']                    
                    requested_slot_count = request_set['count']
                    add_nodes_response = self.cluster.add_nodes(request_id, template_id, requested_slot_count,
                                                                use_weighted_templates, vmTypes,
                                                                self.capacity_limit_timeout,
                                                                self.autoscaling_strategy, self.dry_run)
                if self.dry_run and add_nodes_response:
                    print("Dry run succeeded")
                    exit(0)
            finally:
                request_set['requestId'] = request_id
                self.request_tracker.add_request(request_set) 
            
            if not add_nodes_response:
                raise ValueError("No nodes were created")
            
            logger.info("Create nodes response status: %s  nodes: %s", add_nodes_response.status, [(n.name, n.vm_size) for n in add_nodes_response.nodes])
            
            with self.creation_json as requests_store:
                requests_store[request_id]["allNodes"] = [self.cluster.get_node_id(x) for x in add_nodes_response.nodes]
            
            return self.stdout_handler.handle({"requestId": request_id, "status": RequestStates.running,
                                               "message": "Request instances success from Azure CycleCloud."})

        except (ValueError, UserError) as e:
            logger.exception("Azure CycleCloud experienced an error and the node creation request failed. %s", e)
            return self.stdout_handler.handle({"requestId": request_id, "status": RequestStates.complete_with_error,
                                               "message": "Azure CycleCloud experienced an error: %s" % str(e)})
        except Exception as e:
            logger.exception("Azure CycleCloud experienced an error, though it may have succeeded: %s", e)
            return self.stdout_handler.handle({"requestId": request_id, "status": RequestStates.running,
                                               "message": "Azure CycleCloud experienced an error, though it may have succeeded: %s" % str(e)})

    @failureresponse({"requests": [], "status": RequestStates.complete_with_error})
    def get_return_requests(self, input_json):
        """
        input:
        {}

        output:
        {
            "message": "Any additional message the caller should know" 
            "requests": [
                # Note: Includes Spot instances and On-Demand instances returned from the management console.
            {
                "machine": "(mandatory)(string) Host name of the machine that must be returned",
                "gracePeriod": "(mandatory)(numeric). Time remaining (in seconds) before this host will be reclaimed by the provider"
            }]
        }
        ex.
        {
            "status" : "complete",
            "message" : "Instances marked for termination retrieved successfully.",
            "requests" : [ {
                "gracePeriod" : 0,
                "machine" : "ip-16-0-1-130.ec2.internal"
            },
            {
                "gracePeriod" : 0,
                "machine" : "ip-16-0-1-160.ec2.internal"
            } ]
        }
        """
        request_status = RequestStates.complete
        sym_existing_hostnames = set([m["name"] for m in input_json["machines"]])
        
        try:
            all_nodes = self.cluster.all_nodes()
        except UserError as e:
            logger.exception("Azure CycleCloud experienced an error and the get return request failed. %s", e)
            return self.stdout_handler.handle({"status": RequestStates.complete_with_error,
                                     "requests": [],
                                     "message": "Azure CycleCloud experienced an error: %s" % str(e)})
        except ValueError as e:
            logger.exception("Azure CycleCloud experienced an error and the get return request failed. %s", e)
            return self.stdout_handler.handle({"status": RequestStates.complete_with_error,
                                     "requests": [],
                                     "message": "Azure CycleCloud experienced an error: %s" % str(e)})
        
        message = ""
        report_failure_states = ["Unavailable", "Failed"]
        response = {"message": message,
                    "requests": []}
        req_return_count = 0
        cc_existing_hostnames = set()
        to_shutdown = []

        for node in all_nodes['nodes']:
            if not node.get("Configuration").get("autoscaling", {}).get("enabled", False):
                continue
            hostname = node.get("Hostname")
            if not hostname:
                try:
                    hostname = self.hostnamer.hostname(node.get("PrivateIp"))
                except Exception:
                    logger.warning("get_return_requests: No hostname set and could not convert ip %s to hostname for \"%s\" VM.", node.get("PrivateIp"), node)
            cc_existing_hostnames.add(hostname)
            machine = {"gracePeriod": 0,
                       "machine": hostname or ""}
            node_status = node.get("Status")
            node_status_msg = node.get("StatusMessage", "Unknown node failure.")

            if node_status in report_failure_states:
                logger.error("Requesting Return for failed node: %s (%s) with State: %s (%s)", hostname, node.get("NodeId") or "", node_status, node_status_msg)
                to_shutdown.append({"name": hostname, "machineId": node.get("NodeId")})
                response["requests"].append(machine)
        # these nodes may not even exist in symphony, so we will just shut them down and then report them
        # to symphony.
        try:
            if to_shutdown:
                logger.debug("Terminating returned machines: %s", to_shutdown)
                self.terminate_machines({"machines": to_shutdown}, quiet_output())
        except:
            logger.exception()
        missing_from_cc = sym_existing_hostnames - cc_existing_hostnames

        if len(response["requests"]) > 0:
            message = "Requesting return for %s failed nodes." % (len(response["requests"]))
        
        for hostname in missing_from_cc:
            if hostname:
                machine = {"gracePeriod": 0,
                           "machine": hostname}
                response["requests"].append(machine)
        if missing_from_cc:
            message = "%s Requesting return for %s previously terminated nodes." % (message, len(missing_from_cc))
            
        response["message"] = message
        response["status"] = request_status
        return self.stdout_handler.handle(response)
            
    @failureresponse({"requests": [], "status": RequestStates.running})
    def _create_status(self, input_json, output_handler=None, update_completed_nodes=True):
        """
        input:
        {'requests': [{'requestId': 'req-123'}, {'requestId': 'req-234'}]}

    
        output:
        {'message': '',
         'requests': [{'machines': [{'launchtime': 1516131665,
                                     'machineId': 'id-123',
                                     'message': '',
                                     'privateDnsAddress': '
                                     'name': 'execute-5',
                                     'privateIpAddress': '10.0.1.23',
                                     'result': 'succeed',
                                     'status': 'running'}],
                       'message': '',
                       'requestId': 'req-123',
                       'status': 'complete'}],
         'status': 'complete'}

        """
        output_handler = output_handler or self.stdout_handler
        request_ids = [r["requestId"] for r in input_json["requests"]]
        
        nodes_by_request_id = {}
        exceptions = []
        # go one by one in case one of the request_ids does not exist in CycleCloud
        for request_id in request_ids:
            try:
                nodes_by_request_id.update(self.cluster.nodes(request_ids=[request_id]))   
                logger.debug("Node list by request id %s",nodes_by_request_id)             
            except Exception as e:
                if "No operation found for request id" in str(e):
                    nodes_by_request_id[request_id] = {"nodes": []}
                elif "Could not find request id" in str(e):
                    nodes_by_request_id[request_id] = []
                else:
                    exceptions.append(e)
                    # send HF request is still running so that it remembers request.
                    logger.exception("Azure CycleCloud experienced an error but reporting status as running %s. %s", request_id, e)
                    return output_handler.handle({"status": RequestStates.running,
                                        "requests": [{"requestId": request_id, "status": RequestStates.running} for request_id in request_ids],
                                        "message": "Azure CycleCloud is still requesting nodes"})

                    

        if not nodes_by_request_id:
            error_messages = " | ".join(list(set([str(e) for e in exceptions])))
            return output_handler.handle({"status": RequestStates.complete_with_error,
                                        "requests": [{"requestId": request_id, "status": RequestStates.complete_with_error} for request_id in request_ids],
                                        "message": "Azure CycleCloud experienced an error: %s" % error_messages})
        
        message = ""
        
        response = {"requests": []}
        
        for request_id, requested_nodes in nodes_by_request_id.items():
            request_status = RequestStates.complete
            unknown_state_count = 0
            requesting_count = 0
            if not requested_nodes:
                # nothing to do.
                logger.warning("No nodes found for request id %s.", request_id)
            
            completed_nodes = []
            # Collect all node ids associated with requestId for recovery of failed request_store operation.
            all_nodes = []
            # Collect nodes that have potential to be fulfilled. Excludes failed, terminating and unavailable.
            valid_nodes = []
            machines = []
            request = {"requestId": request_id,
                        "machines": machines}
            
            response["requests"].append(request)
            
            report_failure_states = ["Unavailable", "Failed"]
            terminate_states = []
            
            if self.config.get("symphony.terminate_failed_nodes", False):
                report_failure_states = ["Unavailable"]
                terminate_states = ["Failed"]
            
            for node in requested_nodes:
                # for new nodes, completion is Ready. For "released" nodes, as long as
                # the node has begun terminated etc, we can just say success.
                # node_status = node.get("State")
                node_status = node.state
                node_target_state = node.target_state
                node_id = self.cluster.get_node_id(node)
                all_nodes.append(node_id)
                valid_nodes.append(node_id)
                machine_status = MachineStates.active
                
                hostname = None
                private_ip_address = None

                
                if not node_target_state:
                    unknown_state_count = unknown_state_count + 1
                    continue
                
                if node_target_state and node_target_state != "Started":
                    valid_nodes.remove(node_id)
                    logger.debug("Node %s target state is not started it is %s", node.get("Name"), node_target_state) 
                    continue
                
                if node_status in report_failure_states:
                    valid_nodes.remove(node_id)
                    machine_result = MachineResults.failed
                    machine_status = MachineStates.error
                    if request_status != RequestStates.running:
                        # message = node.get("StatusMessage", "Unknown error.")
                        request_status = RequestStates.complete_with_error
                        
                elif node_status in terminate_states:
                    # just terminate the node and next iteration the node will be gone. This allows retries of the shutdown to happen, as 
                    # we will report that the node is still booting.
                    unknown_state_count = unknown_state_count + 1
                    machine_result = MachineResults.executing
                    machine_status = MachineStates.building
                    request_status = RequestStates.running

                    hostname = node.hostname
                    if not hostname:
                        try:
                            hostname = self.hostnamer.hostname(node.private_ip)
                        except Exception:                            
                            logger.warning("_create_status: No hostname set and could not convert ip %s to hostname for \"%s\" VM.", node.private_ip, node_status)

                    try:
                        logger.warning("Warning: Cluster status check terminating failed node %s", node)
                        # import traceback
                        #logger.warning("Traceback:\n%s", '\n'.join([line  for line in traceback.format_stack()]))
                        self.cluster.shutdown_nodes([{"machineId": self.cluster.get_node_id(node), "name": hostname}])
                    except Exception:
                        logger.exception("Could not terminate node with id %s" % self.cluster.get_node_id(node))
        
                elif not node.instance_id:
                    requesting_count = requesting_count + 1
                    request_status = RequestStates.running
                    machine_result = MachineResults.executing
                    continue
                
                elif node_status in ["Ready", "Started"]:
                    machine_result = MachineResults.succeed
                    machine_status = MachineStates.active
                    private_ip_address = node.private_ip
                    if not private_ip_address:
                        logger.warning("No ip address found for ready node %s", node.get("Name"))
                        machine_result = MachineResults.executing
                        machine_status = MachineStates.building
                        request_status = RequestStates.running
                    else:
                        hostname = node.hostname
                        if not hostname:
                            try:
                                hostname = self.hostnamer.hostname(node.private_ip)
                                logger.warning("_create_status: Node does not have hostname using %s ", hostname)
                            except Exception:                                
                                # TODO: need to append to completed node somewhere? What do we do?
                                logger.warning("_create_status: No hostname set and could not convert ip %s to hostname for \"%s\" VM.", node.get("PrivateIp"), node)    
                        completed_nodes.append({"hostname": hostname, "nodeid": node_id})
                else:
                    machine_result = MachineResults.executing
                    machine_status = MachineStates.building
                    request_status = RequestStates.running

                
                machine = {
                    "name": hostname or "",
                    "status": machine_status,
                    "result": machine_result,
                    "machineId": self.cluster.get_node_id(node) or "",
                    # launchTime is manditory in Symphony
                    # maybe we can add something so we don"t have to expose this
                    # node["PhaseMap"]["Cloud.AwaitBootup"]["StartTime"]["$date"]
                    "launchtime": int(time.time()),
                   # "launchtime": node.get("LaunchTime") or int(time.time()),
                    "privateIpAddress": private_ip_address or "",
                    "message": ""
                    #"message": node.get("StatusMessage") or ""
                }
                
                machines.append(machine)
            
            with self.creation_json as requests_store:
                if request_id not in requests_store:
                    logger.warning("Unknown request_id %s. Creating a new entry and resetting requestTime", request_id)
                    requests_store[request_id] = {"requestTime": calendar.timegm(self.clock())}
                #set default
                requests_store[request_id]["lastUpdateTime"] = calendar.timegm(self.clock())
                        
                # Bugfix: Periodic cleanup calls this function however nodes reach ready state after symphony has 
                # stopped making status calls should not update this.
                if update_completed_nodes:
                    requests_store[request_id]["completedNodes"] = completed_nodes
                if requests_store[request_id].get("allNodes") is None:
                    requests_store[request_id]["allNodes"] = all_nodes
                requests_store[request_id]["completed"] = len(requested_nodes) == len(completed_nodes)

            active = len([x for x in machines if x["status"] == MachineStates.active])
            building = len([x for x in machines if x["status"] == MachineStates.building])
            failed = len([x for x in machines if x["status"] == MachineStates.error])
            
            logger.info("Machine states for requestId %s: %d active, %d building, %d requesting, %d failed and %d in an unknown state.", 
                        request_id, active, building, requesting_count, failed, unknown_state_count)
            
            request["status"] = request_status
            if request_status == RequestStates.complete:
                logger.info("Request %s is complete.", request_id)
            elif request_status == RequestStates.complete_with_error:
                logger.warning("Request %s completed with error: %s.", request_id, message)
            request["message"] = message
        
        response["status"] = symphony.RequestStates.complete
        
        return output_handler.handle(response)
        
    @failureresponse({"requests": [], "status": RequestStates.running})
    def _terminate_status(self, input_json):
        # can transition from complete -> executing or complete -> complete_with_error -> executing
        # executing is a terminal state.
        
        response = {"requests": []}
        request_status = RequestStates.complete
        # needs to be a [] when we return
        with self.terminate_json as terminate_requests:
            
            self._cleanup_expired_requests(terminate_requests, self.termination_timeout, "terminated")
            
            termination_ids = [r["requestId"] for r in input_json["requests"] if r["requestId"]]
            machines_to_terminate = []
            for termination_id in termination_ids:
                if termination_id in terminate_requests:
                    termination = terminate_requests[termination_id]
                    if not termination.get("terminated"):
                        for machine_id, name in termination["machines"].items():
                            machines_to_terminate.append({"machineId": machine_id, "name": name})
            
            if machines_to_terminate:
                logger.warning("Re-attempting termination of nodes %s", machines_to_terminate)
                try:
                    self.cluster.shutdown(machines_to_terminate)
                except Exception:
                    # Send HF request status as running so it remembers the request
                    logger.exception("Could not terminate machines %s due to an exception, reported status as running", machines_to_terminate)
                    request_status = RequestStates.running
                    response["status"] = request_status
                    response_machines = []

                    for termination_id in termination_ids:
                        response_machines = []
                        # if we don't know the termination_id then we report an empty list of machines
                        request = {"requestId": termination_id,
                                    "machines": response_machines}
                        request["status"] = request_status
                        # report machines are in deleting state so HF remembers the request 
                        if termination_id in terminate_requests:
                                termination_request = terminate_requests.get(termination_id)
                                machines = termination_request.get("machines", {})
                                if machines:
                                   for machine_id, hostname in machines.items():
                                      response_machines.append({"name": hostname,
                                                "status": MachineStates.deleting,
                                                "result": MachineResults.executing,
                                                "machineId": machine_id})  
                        response["requests"].append(request) 
                        
                    return response
                    
                
            for termination_id in termination_ids:
                if termination_id in terminate_requests:
                    termination = terminate_requests[termination_id]
                    termination["terminated"] = True
                                    
            for termination_id in termination_ids:
               
                request_status = RequestStates.complete


                response_machines = []
                request = {"requestId": termination_id,
                           "machines": response_machines}
            
                response["requests"].append(request)
                
                if termination_id in terminate_requests:
                    termination_request = terminate_requests.get(termination_id)
                    termination_request["lastUpdateTime"] = calendar.timegm(self.clock())

                    machines = termination_request.get("machines", {})
                    
                    if machines:
                        logger.info("Terminating machines: %s", [hostname for hostname in machines.values()])
                    else:
                        logger.warning("No machines found for termination request %s. Will retry.", termination_id)
                        request_status = RequestStates.running
                    
                    for machine_id, hostname in machines.items():
                        response_machines.append({"name": hostname,
                                                   "status": MachineStates.deleted,
                                                   "result": MachineResults.succeed,
                                                   "machineId": machine_id})
                else:
                    # we don't recognize this termination request!
                    # this can result in leaked VMs!
                    # logger.error("Unknown termination request %s. You may intervene manually by updating terminate_nodes.json" + 
                    #              " to contain the relevant NodeIds. %s ", termination_id, terminate_requests)
                    
                    # # set to running so symphony will keep retrying, hopefully, until someone intervenes.
                    # request_status = RequestStates.running

                    # we don't recognize this termination request!
                    logger.error("Unknown termination request %s. Nodes MAY be leaked.  " +
                                 "You may intervene manually by checking the following NodesIds in CycleCloud: %s", 
                                 termination_id, terminate_requests)
                    
                    # set to complete so symphony will STOP retrying.  May result in a VM leak...
                    request_status = RequestStates.complete_with_error
                    request["message"] = "Warning: Ignoring unknown termination request id."
               
                request["status"] = request_status

        
        response["status"] = request_status
        
        return response


    def _retry_termination_requests(self):
        with self.terminate_json as terminate_requests:
            machines_to_terminate = []
            try:
                for termination_id in terminate_requests:
                    termination = terminate_requests[termination_id]
                    if not termination.get("terminated"):
                        for machine_id, name in termination["machines"].items():
                            machines_to_terminate.append({"machineId": machine_id, "name": name})
                
                if machines_to_terminate:
                    logger.info("Attempting termination of nodes %s", machines_to_terminate)
                    self.cluster.shutdown_nodes(machines_to_terminate)
                    
                for termination_id in terminate_requests:
                    termination = terminate_requests[termination_id]
                    termination["terminated"] = True
                    termination["lastUpdateTime"] = calendar.timegm(self.clock())
                        
            except Exception:
                logger.exception("Could not terminate nodes with ids %s. Will retry", machines_to_terminate)
        
    def _cleanup_expired_requests(self, requests, retirement, completed_key):
        now = calendar.timegm(self.clock())
        for req_id in list(requests.keys()):
            try:
                request = requests[req_id]
                request_time = request.get("requestTime", -1)
                
                if request.get("lastUpdateTime"):
                    request_time = request["lastUpdateTime"]
                if request_time < 0:
                    logger.info("Request has no requestTime")
                    request["requestTime"] = request_time = now
                
                # in case someone puts in a string manuall
                request_time = float(request_time)
                    
                if (now - request_time) > retirement:
                    if not request.get(completed_key):
                        logger.info("Request has expired but has not completed, ignoring expiration: %s", request)
                        continue
                    logger.info("Found retired request %s", req_id)
                    requests.pop(req_id)
                
            except Exception:
                logger.exception("Could not remove stale request %s", req_id)


                
    @failureresponse({"status": RequestStates.complete_with_error})
    def terminate_machines(self, input_json, output_handler=None):
        """
        input:
        {
            "machines":[ {"name": "host-123", "machineId": "id-123"} ]
        }
        
        output:
        {
            "message" : "Delete VM success.",
            "requestId" : "delete-i-123",
            "status": "complete"
        }
        """
        output_handler = output_handler or self.stdout_handler
        logger.info("Terminate_machines request for : %s", input_json)         
        request_id = "delete-%s" % str(uuid.uuid4())
        request_id_persisted = False
        try:
            try:
                with self.terminate_json as terminations:
                    machines = {}
                    for machine in input_json["machines"]:
                        if "machineId" not in machine:
                            # cluster api can handle invalid machine ids
                            machine["machineId"] = machine["name"]
                        machines[machine["machineId"]] = machine["name"]
                        
                    terminations[request_id] = {"id": request_id, "machines": machines, "requestTime": calendar.timegm(self.clock())}
                request_id_persisted = True
            except:
                # NOTE: Here we will not exit immediately but exit after an attempted shutdown
                logger.exception("Could not open terminate.json")
            
            request_status = RequestStates.complete
            message = "CycleCloud is terminating the VM(s)"

            try:
                self.cluster.shutdown_nodes(input_json["machines"])
                with self.terminate_json as terminations:
                    terminations[request_id]["terminated"] = True
            except Exception:
                # set to running, we will retry on any status call anyways.
                request_status = RequestStates.running
                message = str(message)
                logger.exception("Could not terminate %s", machines.keys())
            
            logger.info("Terminating %d machine(s): %s", len(machines), ",".join(list(machines.keys())))

            # NOTE: we will still respond with a failure here, but at least we attempted the termination
            if not request_id_persisted:
                return sys.exit(1)
            
            return output_handler.handle({"message": message,
                                "requestId": request_id,
                                "status": request_status,
                                "machines": [ {
                                    "name": machine["name"],
                                    "message": message,
                                    "privateIpAddress": None,
                                    "publicIpAddress": None,
                                    "rcAccount": None,
                                    "requestId": request_id,
                                    "returnId": request_id,
                                    "template": None,
                                    "status": request_status
                                } for machine in input_json["machines"] ]
            })

        except Exception as e:
            logger.exception(str(e))
            if request_id_persisted:
                return output_handler.handle({"status": RequestStates.running, "requestId": request_id})
            return output_handler.handle({"status": RequestStates.complete_with_error, "requestId": request_id, "message": str(e)})
        
    def status(self, input_json):
        '''
        Kludge: can't seem to get provider.json to reliably call the correct request action.
        '''
        creates = [x for x in input_json["requests"] if not x["requestId"].startswith("delete-")]
        deletes = [x for x in input_json["requests"] if x["requestId"].startswith("delete-")]
        create_response = {}
        delete_response = {}
        if creates:
            create_response = self._create_status({"requests": creates}, quiet_output())
            assert "status" in create_response

        if deletes:
            delete_response = self._terminate_status({"requests": deletes})
            assert "status" in delete_response

        # Update request tracking
        if 'requests' in create_response:
            for cr in create_response['requests']:
                if cr['status'] in [ RequestStates.complete ]:
                    self.request_tracker.request_completed(cr)

        create_status = create_response.get("status", RequestStates.complete)
        delete_status = delete_response.get("status", RequestStates.complete)
        
        # if either are still running, then we need to mark it as running so this will continued
        # to be called
        if RequestStates.running in [create_status, delete_status]:
            combined_status = RequestStates.running
        # if one completed with error, then they both did.
        elif RequestStates.complete_with_error in [create_status, delete_status]:
            combined_status = RequestStates.complete_with_error
        else:
            combined_status = RequestStates.complete

        response = {"status": combined_status,
                    "requests": create_response.get("requests", []) + delete_response.get("requests", [])
                    }
        return self.stdout_handler.handle(response)

    def _terminate_expired_requests(self):

        # if a request is made but no subsequent status call is ever made, we won't have any information stored about the request.
        # this forces a status call of those before moving on.
        # Note we aren't in the creation_json lock here, as status will grab the lock.
        never_queried_requests = []
        for request_id, request in self.creation_json.read().items():
            if request["allNodes"] is None:
                never_queried_requests.append(request_id)
        if never_queried_requests:
            try:
                unrecoverable_request_ids = []
                response = self._create_status({"requests": [{"requestId": r} for r in never_queried_requests]}, 
                                               quiet_output(), 
                                               update_completed_nodes=False)

                for request in response["requests"]:
                    #setting _recoverable_ to false so we don't retry indefinitely
                    if request["status"] == RequestStates.complete_with_error and not request.get("_recoverable_", False):
                        unrecoverable_request_ids.append(request["requestId"])

                # if we got a 404 on the request_id (a failed nodes/create call), set allNodes to an empty list so that we don't retry indefinitely. 
                with self.creation_json as creation_requests:
                    for request_id in unrecoverable_request_ids:
                        creation_requests[request_id]["allNodes"] = []

            except Exception:
                logger.exception("Could not request status of creation quests.")
        
        requests_store = self.creation_json.read()
        to_update_status = []
        # find all requests that are not completed but have expired
        for request_id, request in requests_store.items():
                if request.get("completed"):
                    continue
                created_timestamp = request["requestTime"]
                now = calendar.timegm(self.clock())
                delta = now - created_timestamp

                if delta > self.creation_request_ttl:
                    to_update_status.append(request_id)
        if not to_update_status:
            return
        
        self._create_status({"requests": [{"requestId": r} for r in to_update_status]},
                              quiet_output(), 
                              # We need to terminate nodes that were not ready by the time the request expired
                              # We will terminate nodes that converge after timeout
                              update_completed_nodes=False)

        with self.creation_json as requests_store:
            to_shutdown = []
            to_mark_complete = []
            
            for request_id in to_update_status:
                request = requests_store[request_id]
                if request.get("completed"):
                    continue

                if request.get("allNodes") is None:
                    logger.warning("Yet to find any NodeIds for RequestId %s", request_id)
                    continue

                completed_node_ids = [x["nodeid"] for x in request["completedNodes"]]
                failed_to_start = set(request["allNodes"]) - set(completed_node_ids)
                if failed_to_start:
                    to_shutdown.extend(set(request["allNodes"]) - set(completed_node_ids))
                    logger.warning("Expired creation request found - %s. %d out of %d completed.", request_id, 
                        len(completed_node_ids), len(request["allNodes"]))
                to_mark_complete.append(request)

            if not to_mark_complete:
                return

            if to_shutdown:
                self.terminate_machines({"machines": [{"machineId": x, "name": x} for x in to_shutdown]}, quiet_output())

            for request in to_mark_complete:
                request["lastUpdateTime"] = calendar.timegm(self.clock())
                request["completed"] = True

    def periodic_cleanup(self):
        try:
            self._retry_termination_requests()
        except Exception:
            logger.exception("Could not retry termination")

        try:
            self._terminate_expired_requests()
        except Exception:
            logger.exception("Could not terminate expired requests")

        try:
            with self.terminate_json as terminate_requests:
                self._cleanup_expired_requests(terminate_requests, self.termination_timeout, "terminated")

            with self.creation_json as creation_requests:
                self._cleanup_expired_requests(creation_requests, self.termination_timeout, "completed")

        except Exception:
            logger.exception("Could not cleanup old requests")
    
    def debug_completed_nodes(self):
        all_nodes = self.cluster.all_nodes()
        actual_completed_nodes = set()
        for node in all_nodes['nodes']:
            if node.get("Status") in ["Ready", "Started"]:
                actual_completed_nodes.add(node.get("NodeId"))
        internal_completed_nodes = set()
        with self.creation_json as request_store:
            for request in request_store.values():
                internal_completed_nodes.update(set(request.get("completedNodes")))
        incomplete_nodes = actual_completed_nodes - internal_completed_nodes
        print(incomplete_nodes)
    
    def validate_template(self):
        cluster_status = self.cluster.status()
        nodearrays = cluster_status["nodearrays"]
        pro_conf_dir = os.getenv('PRO_CONF_DIR', os.getcwd())
        conf_path = os.path.join(pro_conf_dir, "conf", "azureccprov_templates.json")
        with open(conf_path, 'r') as json_file:
            templates_json = json.load(json_file)
        if "templates" not in templates_json:
            print("List templates not present in azureccprov_templates.json", file=sys.stderr)
            return False
        templates_json = templates_json["templates"]
        if len(templates_json) == 0:
            print("Length of list templates is 0", file=sys.stderr)
            return False
        template_name_found = False
        for template in templates_json:
           for nodearray_root in nodearrays:
               template_name_found = False
               if template["templateId"].strip() == nodearray_root.get("name").strip():
                   template_name_found = True
                   bucket_machineType = [bucket.get("definition")["machineType"].strip() for bucket in nodearray_root.get("buckets")]
                   if "vmTypes" not in template:
                       print("Template validation failed", file=sys.stderr)  
                       print("vmTypes not present in template %s" % template["templateId"], file=sys.stderr)
                       return False
                   vmTypes = [key.strip() for key in template["vmTypes"].keys()]
                   bucket_machineType = set(bucket_machineType)
                   vmTypes = set(vmTypes)
                   diff = bucket_machineType.symmetric_difference(vmTypes)
                   if len(diff) > 0:
                       print("Template validation failed", file=sys.stderr)   
                       print(f"Difference in vmTypes and buckets {diff} for template {template['templateId']}", file=sys.stderr)
                       return False
                   break
           if not template_name_found:
               print("Template validation failed", file=sys.stderr)
               print("Template %s does not exist in nodearray" % template["templateId"], file=sys.stderr)
               return False
        print("Template validation passed")
        return True
    

class JsonOutputHandler:
    def __init__(self, quiet=False) -> None:
        self.written = False
        self.quiet = quiet
        
    def handle(self, data, debug_output=True):  # pragma: no cover
        assert not self.written 
        self.written = True
        data_str = json.dumps(data)
        if debug_output:
            logger.debug("Response: %s", data_str)
        if not self.quiet:
            print(data_str)
        return data
    
    def try_handle(self, data, debug_output=True):
        if self.written:
            return
        return self.handle(data, debug_output)


def true_gmt_clock():  # pragma: no cover
    import time
    return time.gmtime()


def main(argv=sys.argv):  # pragma: no cover
    operation_id = int(time.time())
    try:
        
        global logger
        # every command has the format cmd -f input.json        
        cmd, ignore, input_json_path = argv[1:]
        provider_config, logger, fine = util.provider_config_from_environment()
        
        data_dir = os.getenv('PRO_DATA_DIR', os.getcwd())
        conf_dir = os.getenv('PRO_CONF_DIR', os.getcwd())
        hostnamer = util.Hostnamer(provider_config.get("cyclecloud.hostnames.use_fqdn", True))
        cluster_name = provider_config.get("cyclecloud.cluster.name")
        
        provider = CycleCloudProvider(config=provider_config,
                                      cluster=cluster.Cluster(cluster_name, provider_config, logger),
                                      hostnamer=hostnamer,
                                      stdout_handler=JsonOutputHandler(quiet=False),
                                      terminate_requests=JsonStore("terminate_requests.json", data_dir),
                                      creation_requests=JsonStore("create_requests.json", data_dir),
                                      clock=true_gmt_clock)
        
        provider.fine = fine
        
        input_json = util.load_json(input_json_path)
        
        
        logger.info("BEGIN %s %s - %s %s", operation_id, cmd, ignore, input_json_path)
        logger.debug("Input: %s", json.dumps(input_json))
        
        if cmd == "validate_templates" or input_json.get("dry-run"):
            provider.validate_template()
            provider.dry_run = True  
        if cmd == "generate_templates":
            provider.generate_sample_template()     
        
                
        if cmd == "templates":
            logger.info("Using azurecc version %s", version.get_version())
            provider.templates()
        elif cmd == "create_machines":
            provider.create_machines(input_json)
        elif cmd in ["create_status"]:
            if "requests" in input_json:
                # provider.status handles both create_status and terminate_status calls.
                provider.status(input_json)
            else:
                # should be impossible
                raise RuntimeError("Unexpected input json for cmd %s" % (input_json, cmd))
        elif cmd == "get_return_requests":
            provider.get_return_requests(input_json)
        elif cmd == "terminate_machines":
            provider.terminate_machines(input_json)
        elif cmd == "debug_completed_nodes":
            provider.debug_completed_nodes()
        

        
        # best effort cleanup.
        provider.periodic_cleanup()
            
    except ImportError as e:
        logger.exception(str(e))

    except Exception as e:
        if logger:
            logger.exception(str(e))
        else:
            import traceback
            traceback.print_exc()
        logger.warning("Exiting Non-zero so that symphony will retry")
        sys.exit(1) 
    finally:
        logger.info("END %s %s - %s %s", operation_id, cmd, ignore, input_json_path)       

if __name__ == "__main__":
    main()  # pragma: no cover
else:
    logger = util.init_logging()
