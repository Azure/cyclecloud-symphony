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


from symphony import RequestStates, MachineStates, MachineResults, SymphonyRestClient
import cluster
from cluster import OutOfCapacityError
from capacity_tracking_db import CapacityTrackingDb
from util import JsonStore, failureresponse
import util
import symphony
import version
from cyclecliwrapper import UserError


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


class CycleCloudProvider:
    
    def __init__(self, config, cluster, hostnamer, json_writer, terminate_requests, creation_requests, templates, clock):
        self.config = config
        self.cluster = cluster
        self.hostnamer = hostnamer
        self.json_writer = json_writer
        self.terminate_json = terminate_requests
        self.templates_json = templates
        self.creation_json = creation_requests
        self.exit_code = 0
        self.clock = clock
        self.termination_timeout = float(self.config.get("cyclecloud.termination_request_retirement", 120) * 60)
        self.creation_request_ttl = int(self.config.get("symphony.creation_request_ttl", 40 * 60))
        self.node_request_timeouts = float(self.config.get("cyclecloud.machine_request_retirement", 120) * 60)
        self.fine = False
        self.capacity_tracker = CapacityTrackingDb(self.config, self.cluster.cluster_name, self.clock)
        
    def _escape_id(self, name):
        return name.lower().replace("_", "")
    
    def example_templates(self):
        self._example_templates(self.templates()["templates"], [sys.stdout])
        
    def _example_templates(self, templates, writers):
        
        example = OrderedDict()
        nodearrays = []
        for template in templates["templates"]:
            nodearray = template["attributes"]["nodearray"][1]
            if nodearray not in nodearrays:
                nodearrays.append(nodearray)
        
        for nodearray in nodearrays:
            example[nodearray] = {"templateId": nodearray,
                                  "attributes": {"custom": ["String", "custom_value"]}}
            
        for writer in writers:
            json.dump(example, writer, indent=2, separators=(',', ': '))
            
    def _check_for_zero_capacity(self, buckets):
        at_least_one_available_bucket = False
        for bucket in buckets:
            autoscale_enabled = bucket.software_configuration.get("autoscaling", {}).get("enabled", False)
            if not autoscale_enabled:
               continue
            if bucket.available_count == 0:
                logger.debug("Bucket %s has 0 availableCount.", bucket)
                continue
            max_count = bucket.max_count
            is_paused = self.capacity_tracker.is_paused(bucket.nodearray, bucket.vm_size)
            if is_paused:
                max_count = 0
            at_least_one_available_bucket = at_least_one_available_bucket or max_count > 0  
        return not at_least_one_available_bucket
     
    # Regenerate templates (and potentially reconfig HostFactory) without output, so 
    #  this method is safe to call from other API calls
    def _update_templates(self, do_REST=False):
        """
        input (ignored):
        []
        
        output:
        {'templates': [{'attributes': {'azurecchost': ['Boolean', '1'],
                               'mem': ['Numeric', '2048'],
                               'ncores': ['Numeric', '4'],
                               'ncpus': ['Numeric', '1'],
                               'type': ['String', 'X86_64'],
                               'zone': ['String', 'southeastus']},
                'instanceTags': 'group=project1',
                'maxNumber': 10,
                'pgrpName': None,
                'priority': 0,
                'templateId': 'execute0'},
               {'attributes': {'azurecchost': ['Boolean', '1'],
                               'mem': ['Numeric', '4096'],
                               'ncores': ['Numeric', '8'],
                               'ncpus': ['Numeric', '1'],
                               'rank': ['Numeric', '0'],
                               'priceInfo': ['String', 'price:0.1,billingTimeUnitType:prorated_hour,billingTimeUnitNumber:1,billingRoundoffType:unit'],
                               'type': ['String', 'X86_64'],
                               'zone': ['String', 'southeastus']},
                'instanceTags': 'group=project1',
                'maxNumber': 10,
                'pgrpName': None,
                'priority': 0,
                'templateId': 'execute1'}]}
        """
        at_least_one_available_bucket = False
        templates_store = self.templates_json.read()
        
        prior_templates_str = json.dumps(templates_store, indent=2, sort_keys=True)  

        buckets = self.cluster.get_buckets()
        
        # We cannot report to Symphony that we have 0 capacity on all VMs. If we detect this we
        # simply reset any temporary capacity constraints.
        if self._check_for_zero_capacity(buckets):
            logger.warning("All buckets have 0 capacity. Resetting capacity tracker.")
            self.capacity_tracker.reset()
        
        currently_available_templates = set()
            
        for bucket in buckets:

            
            autoscale_enabled = bucket.software_configuration.get("autoscaling", {}).get("enabled", False)
            if not autoscale_enabled:
                continue
            # Symphony hates special characters
            template_id = "%s%s" % (bucket.nodearray, bucket.vm_size)
            template_id = self._escape_id(template_id)
            currently_available_templates.add(template_id)
            
            max_count = bucket.max_count
            is_low_prio = bucket.spot
            at_least_one_available_bucket = at_least_one_available_bucket or max_count > 0
            memory = bucket.memory.convert_to("m").value

            ngpus = 0
            try:
                ngpus = int(bucket.software_configuration.get("symphony", {}).get("ngpus", bucket.gpu_count))
            except ValueError:
                logger.exception("Ignoring symphony.ngpus for nodearray %s" % bucket.nodearray)
            # Check previous maxNumber setting - we NEVER lower maxNumber, only raise it.
            previous_max_count = 0
            if template_id in templates_store:
                previous_max_count = templates_store[template_id].get("maxNumber", max_count)
            if max_count < previous_max_count:
                logger.info("Rejecting attempt to lower maxNumber from %s to %s for %s", previous_max_count, max_count, template_id)
                max_count = previous_max_count
            base_priority = bucket_priority(buckets, bucket)
            # Symphony
            # - uses nram rather than mem
            # - uses strings for numerics         
            record = {
                "maxNumber": max_count,
                "templateId": template_id,
                "priority": base_priority,
                "attributes": {
                    "zone": ["String", bucket.location],
                    "mem": ["Numeric", "%d" % memory],
                    "nram": ["Numeric", "%d" % memory],
                    # NOTE:
                    #  ncpus == num_sockets == ncores / cores_per_socket
                    #  Since we don't generally know the num_sockets,
                    #      just set ncpus = 1 for all skus (1 giant CPU with N cores)
                    #"ncpus": ["Numeric", "%d" % machine_type.get("???physical_socket_count???")],
                    "ncpus": ["Numeric", "%d" % bucket.resources.get("ncpus", 1)],  
                    "ncores": ["Numeric", "%d" % bucket.resources.get("ncores", bucket.vcpu_count)],
                    "ngpus": ["Numeric", ngpus],                            
                    "azurecchost": ["Boolean", "1"],
                    'rank': ['Numeric', '0'],
                    'priceInfo': ['String', 'price:0.1,billingTimeUnitType:prorated_hour,billingTimeUnitNumber:1,billingRoundoffType:unit'],                               'type': ['String', 'X86_64'],
                    "type": ["String", "X86_64"],
                    "machinetypefull": ["String", bucket.vm_size],
                    "machinetype": ["String", bucket.vm_size],
                    "nodearray": ["String", bucket.nodearray],
                    "azureccmpi": ["Boolean", "0"],
                    "azurecclowprio": ["Boolean", "1" if is_low_prio else "0"]
                }
            }
            
            # deepcopy so we can pop attributes
            
            for override_sub_key in ["default", bucket.nodearray]:
                overrides = deepcopy(self.config.get("templates.%s" % override_sub_key, {}))
                attribute_overrides = overrides.pop("attributes", {})
                record.update(overrides)
                record["attributes"].update(attribute_overrides)
            
            attributes = self.generate_userdata(record)
            
            custom_env = self._parse_UserData(record.pop("UserData", "") or "")
            record["UserData"] = {"symphony": {}}
            
            if custom_env:
                record["UserData"]["symphony"] = {"custom_env": custom_env,
                                                "custom_env_names": " ".join(sorted(custom_env))}
            
            record["UserData"]["symphony"]["attributes"] = attributes
            record["UserData"]["symphony"]["attribute_names"] = " ".join(sorted(attributes))

            record["pgrpName"] = None
            
            is_paused_capacity = self.capacity_tracker.is_paused(bucket.nodearray, bucket.vm_size)

            if is_paused_capacity:
                record["priority"] = 0
                
            templates_store[template_id] = record
        
        # for templates that are no longer available, advertise them but set priority = 0
        # NOTE: do not modify "maxNumber" - Symphony HF does not respond well to lowering maxNumber while jobs may be runni
        for symphony_template in templates_store.values():
            if symphony_template["templateId"] not in currently_available_templates:
                if self.fine:
                    logger.debug("Ignoring old template %s vs %s", symphony_template["templateId"], currently_available_templates)
                symphony_template["priority"] = 0
                
        new_templates_str = json.dumps(templates_store, indent=2, sort_keys=True)
        symphony_templates = list(templates_store.values())
        symphony_templates = sorted(symphony_templates, key=lambda x: -x["priority"])
        #if new_templates_str != prior_templates_str and len(prior_templates) > 0: this probably was here to avoid a deadlock, but here we are avoiding with do_REST
        if new_templates_str != prior_templates_str:
            generator = difflib.context_diff(prior_templates_str.splitlines(), new_templates_str.splitlines())
            difference = "\n".join([str(x) for x in generator])
            new_template_order = ", ".join(["%s:%s" % (x.get("templateId", "?"), x.get("maxNumber", "?")) for x in symphony_templates])
            logger.warning("Templates have changed - new template priority order: %s", new_template_order)
            logger.warning("Diff:\n%s", str(difference))
            persist_templates = not do_REST #we always persist if not doing REST call, otherwise only persist on succesful REST call
            if do_REST:
                try:
                    rest_client = SymphonyRestClient(self.config, logger)  
                    rest_client.update_hostfactory_templates({"templates": symphony_templates, "message": "Get available templates success."})
                    persist_templates = True
                except:
                    logger.exception("Ignoring failure to update cluster templates via Symphony REST API. (Is REST service running?)")
            if persist_templates:        
                self.templates_json.write(templates_store)
               
        # Note: we aren't going to store this, so it will naturally appear as an error during allocation.
        if not at_least_one_available_bucket:
            symphony_templates.insert(0, PLACEHOLDER_TEMPLATE)

        return symphony_templates
        
    # If we return an empty list or templates with 0 hosts, it removes us forever and ever more, so _always_
    # return at least one machine.
    # BUGFIX: exiting non-zero code will make symphony retry.
    def templates(self):
        try:
            symphony_templates = self._update_templates()
            return self.json_writer({"templates": symphony_templates, "message": "Get available templates success."}, debug_output=False)
        except:
            logger.warning("Exiting Non-zero so that symphony will retry")
            logger.exception("Could not get template_json")
            sys.exit(1)

    def generate_userdata(self, template):
        ret = {}
        
        for key, value_array in template.get("attributes", {}).items():
            if len(value_array) != 2:
                logger.error("Invalid attribute %s %s", key, value_array)
                continue
            if value_array[0].lower() == "boolean":
                ret[key] = str(value_array[1] != "0").lower()
            else:
                ret[key] = value_array[1]
        
        if template.get("customScriptUri"):
            ret["custom_script_uri"] = template.get("customScriptUri")
            
        return ret
        
    def _parse_UserData(self, user_data):
        ret = {}
        
        user_data = (user_data or "").strip()
        
        if not user_data:
            return ret
        
        key_values = user_data.split(";")
        
        # kludge: this can be overridden either at the template level
        # or during a creation request. We always want it defined in userdata
        # though.
        
        for kv in key_values:
            try:
                key, value = kv.split("=", 1)
                ret[key] = value
            except ValueError:
                logger.error("Invalid UserData entry! '%s'", kv)
        return ret


    def is_capacity_limited(self, bucket):
        return False
    
    def _max_count(self, nodearray_name, nodearray, machine_cores, bucket):
        if machine_cores < 0:
            logger.error("Invalid number of machine cores - %s.", machine_cores)
            return -1

        max_count = bucket.get("maxCount")
        
        if max_count is not None:
            max_count = max(-1, max_count)
            logger.debug("Using maxCount %s for %s", max_count, bucket)
        else:
            max_core_count = bucket.get("maxCoreCount")
            if max_core_count is None:
                if nodearray.get("maxCoreCount") is None:
                    logger.error("Need to define either maxCount or maxCoreCount! %s", pprint.pformat(bucket))
                    return -1
                max_core_count = nodearray.get("maxCoreCount")
                logger.debug("Using maxCoreCount %s for nodearray %s and bucket %s", max_core_count, nodearray_name, bucket)
            
            max_core_count = max(-1, max_core_count)
        
            max_count = max_core_count / machine_cores

        # We handle unexpected Capacity failures (Spot)  by zeroing out capacity for a timed duration
        # machine_type_name = bucket["definition"]["machineType"]
        
        return int(max_count)
    
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
        try:
            # save the request so we can time it out
            with self.creation_json as requests_store:
                requests_store[request_id] = {"requestTime": calendar.timegm(self.clock()),
                                            "completedNodes": [],
                                            "allNodes": None,
                                            "completed": False,
                                            "lastNumNodes": input_json["template"]["machineCount"]}
        except:
            logger.exception("Could not open creation_json")
            sys.exit(1)    
        try:
            template_store = self.templates_json.read()
        
            # same as nodearrays - Cloud.Node joined with MachineType
            template_id = input_json["template"]["templateId"]
            template = template_store.get(template_id)
            
            if not template:
                available_templates = template_store.keys()
                return self.json_writer({"requestId": request_id, "status": RequestStates.complete_with_error, 
                                        "message": "Unknown templateId %s. Available %s" % (template_id, available_templates)})
                
            machine_count = input_json["template"]["machineCount"]
            
            def _get(name):
                return template["attributes"].get(name, [None, None])[1]
            
            rc_account = input_json.get("rc_account", "default")
            
            user_data = template.get("UserData")

            if rc_account != "default":
                if "symphony" not in user_data:
                    user_data["symphony"] = {}
                
                if "custom_env" not in user_data["symphony"]:
                    user_data["symphony"]["custom_env"] = {}
                    
                user_data["symphony"]["custom_env"]["rc_account"] = rc_account
                user_data["symphony"]["custom_env_names"] = " ".join(sorted(user_data["symphony"]["custom_env"].keys()))
            
            nodearray = _get("nodearray")
            
            machinetype_name = _get("machinetypefull")
            
            request_set = { 'count': machine_count,                       
                            'definition': {'machineType': machinetype_name},
                            'nodeAttributes': {'Tags': {"rc_account": rc_account},
                                                'Configuration': user_data},
                            'nodearray': nodearray }
            if template["attributes"].get("placementgroup"):
                request_set["placementGroupId"] = template["attributes"].get("placementgroup")[1]
            
            # We are grabbing the lock to serialize this call.
            try:
                with self.creation_json as requests_store:                   
                        add_nodes_response = self.cluster.add_nodes({'requestId': request_id,
                                                        'sets': [request_set]}, template.get("maxNumber"))
            finally:
                request_set['requestId'] = request_id
                self.capacity_tracker.add_request(request_set)
        
            
            
            if not add_nodes_response:
                raise ValueError("No nodes were created")
            
            logger.info("Create nodes response: %s", add_nodes_response)
            
            with self.creation_json as requests_store:
                 requests_store[request_id]["allNodes"] = [self.cluster.get_node_id(x) for x in add_nodes_response.nodes]

            if template["attributes"].get("placementgroup"):
                logger.info("Requested %s instances of machine type %s in placement group %s for nodearray %s.", machine_count, machinetype_name, _get("placementgroup"), _get("nodearray"))
            else:
                logger.info("Requested %s instances of machine type %s in nodearray %s.", machine_count, machinetype_name, _get("nodearray"))
            
            return self.json_writer({"requestId": request_id, "status": RequestStates.running,
                                     "message": "Request instances success from Azure CycleCloud."})
        except UserError as e:
            logger.exception("Azure CycleCloud experienced an error and the node creation request failed. %s", e)
            return self.json_writer({"requestId": request_id, "status": RequestStates.complete_with_error,
                                     "message": "Azure CycleCloud experienced an error: %s" % str(e)})
        except ValueError as e:
            logger.exception("Azure CycleCloud experienced an error and the node creation request failed. %s", e)
            return self.json_writer({"requestId": request_id, "status": RequestStates.complete_with_error,
                                     "message": "Azure CycleCloud experienced an error: %s" % str(e)})
        except OutOfCapacityError as e:
            logger.warning("Request Id %s failed with out of capacity %s", request_id, e)
            return self.json_writer({"requestId": request_id, "status": RequestStates.running,
                                     "message": "Azure CycleCloud does not currently have capacity %s" % str(e)})
        except Exception as e:
            logger.exception("Azure CycleCloud experienced an error, though it may have succeeded: %s", e)
            return self.json_writer({"requestId": request_id, "status": RequestStates.running,
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
            return self.json_writer({"status": RequestStates.complete_with_error,
                                     "requests": [],
                                     "message": "Azure CycleCloud experienced an error: %s" % str(e)})
        except ValueError as e:
            logger.exception("Azure CycleCloud experienced an error and the get return request failed. %s", e)
            return self.json_writer({"status": RequestStates.complete_with_error,
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
                self.terminate_machines({"machines": to_shutdown})
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
        return self.json_writer(response)
            
    @failureresponse({"requests": [], "status": RequestStates.running})
    def _create_status(self, input_json, json_writer=None):
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
        json_writer = json_writer or self.json_writer
        
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
                    return json_writer({"status": RequestStates.running,
                                        "requests": [{"requestId": request_id, "status": RequestStates.running} for request_id in request_ids],
                                        "message": "Azure CycleCloud is still requesting nodes"})

                    

        if not nodes_by_request_id:
            error_messages = " | ".join(list(set([str(e) for e in exceptions])))
            return json_writer({"status": RequestStates.complete_with_error,
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
                actual_machine_cnt = len(valid_nodes)
                if not requests_store[request_id].get("lastNumNodes") :
                    requests_store[request_id]["lastNumNodes"] = actual_machine_cnt
                if actual_machine_cnt < requests_store[request_id]["lastNumNodes"]:
                    request_envelope = self.capacity_tracker.get_request(request_id)
                    if not request_envelope:
                        logger.warning("No request envelope maybe all buckets have hit capacity issue")
                        logger.debug("No request envelope found for request id %s", request_id)
                    else:
                        reqs = request_envelope.get('sets', [])
                        if not reqs:
                            continue
                        assert len(reqs) == 1
                        req = reqs[0]
                        nodearray_name = req['nodearray']
                        machine_type = req['definition']['machineType']
                        logger.warning("Out-of-capacity condition detected for machine_type %s in nodearray %s", machine_type, nodearray_name)
                        self.capacity_tracker.pause_capacity(nodearray_name=nodearray_name, machine_type=machine_type)
                        requests_store[request_id]["lastNumNodes"] = actual_machine_cnt
                        
                requests_store[request_id]["completedNodes"] = completed_nodes
                if requests_store[request_id].get("allNodes") is None:
                    requests_store[request_id]["allNodes"] = all_nodes
                requests_store[request_id]["completed"] = len(nodes_by_request_id) == len(completed_nodes)

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
        
        return json_writer(response)
        
    @failureresponse({"requests": [], "status": RequestStates.running})
    def _deperecated_terminate_status(self, input_json):
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
                        
                    return self.json_writer(response)
                    
                
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
        
        return self.json_writer(response)
    
    @failureresponse({"status": RequestStates.running})
    def terminate_status(self, input_json):
        ids_to_hostname = {}
    
        for machine in input_json["machines"]:
            ids_to_hostname[machine["machineId"]] = machine["name"]
        
        with self.terminate_json as term_requests:
            requests = {}
            for node_id, hostname in ids_to_hostname.items():
                machine_record = {"machineId": node_id, "name": hostname}
                found_a_request = False
                for request_id, request in term_requests.items():
                    if node_id in request["machines"]:
                        
                        found_a_request = True
                        
                        if request_id not in requests:
                            requests[request_id] = {"machines": []}
                        
                        requests[request_id]["machines"].append(machine_record)
                
                if not found_a_request:
                    logger.warning("No termination request found for machine %s", machine_record)
                    # logger.warning("Forcing termination request for machine %s", machine_record)
                    # import traceback
                    # logger.warning("Traceback:\n%s" % '\n'.join([line  for line in traceback.format_stack()]))
                    # terminate_request = { "machines": [ machine_record ]}
                    # self.terminate_machines( terminate_request, lambda x: x )
            
            deprecated_json = {"requests": [{"requestId": request_id, "machines": requests[request_id]["machines"]} for request_id in requests]}
            return self._deperecated_terminate_status(deprecated_json)

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
    def terminate_machines(self, input_json, json_writer=None):
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
        json_writer = json_writer or self.json_writer
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
            
            return json_writer({"message": message,
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
                return json_writer({"status": RequestStates.running, "requestId": request_id})
            return json_writer({"status": RequestStates.complete_with_error, "requestId": request_id, "message": str(e)})
        
    def status(self, input_json):
        '''
        Kludge: can't seem to get provider.json to reliably call the correct request action.
        '''
        json_writer = self.json_writer
        self.json_writer = lambda x: x
        creates = [x for x in input_json["requests"] if not x["requestId"].startswith("delete-")]
        deletes = [x for x in input_json["requests"] if x["requestId"].startswith("delete-")]
        create_response = {}
        delete_response = {}
        
        if creates:
            create_response = self._create_status({"requests": creates})
            assert "status" in create_response

        if deletes:
            delete_response = self._deperecated_terminate_status({"requests": deletes})
            assert "status" in delete_response

        # Update capacity tracking
        if 'requests' in create_response:
            for cr in create_response['requests']:
                if cr['status'] in [ RequestStates.complete ]:
                    self.capacity_tracker.request_completed(cr)

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
        
        # if the Capacity limits have changed, templates will be updated at the end of this call.
        # -> HostFactory rarely  (if ever) calls getAvailableTemplates after startup

        response = {"status": combined_status,
                    "requests": create_response.get("requests", []) + delete_response.get("requests", [])
                    }
        return json_writer(response)

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

                response = self._create_status({"requests": [{"requestId": r} for r in never_queried_requests]}, lambda input_json, **ignore: input_json)

                for request in response["requests"]:
                    if request["status"] == RequestStates.complete_with_error and not request.get("_recoverable_", True):
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
                              lambda input_json, **ignore: input_json)

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
                original_writer = self.json_writer
                self.json_writer = lambda data, debug_output=True: 0
                self.terminate_machines({"machines": [{"machineId": x, "name": x} for x in to_shutdown]})
                self.json_writer = original_writer

            for request in to_mark_complete:
                request["lastUpdateTime"] = calendar.timegm(self.clock())
                request["completed"] = True

    def periodic_cleanup(self, skip_templates=False):
        try:
            # skip_templates should always be true when HF calls getAvailableTemplates 
            # To avoid an infinite loop / internal deadlock in HF caused if we do a REST call.
            if not skip_templates:
                self._update_templates(do_REST=True)
        except Exception:
            logger.exception("Could not update templates")

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

def bucket_priority(buckets, bucket_nodearray):
    nodearrays = list(dict.fromkeys(bucket.nodearray for bucket in buckets))
    filter_bucket_nodearray = [bucket for bucket in buckets if bucket.nodearray == bucket_nodearray.nodearray]
    b_index = next((i for i, bucket in enumerate(filter_bucket_nodearray) if bucket.bucket_id == bucket_nodearray.bucket_id), None)
    reveresed_nodearrays = nodearrays[::-1]
    return _bucket_priority(reveresed_nodearrays, bucket_nodearray, b_index)

def _bucket_priority(nodearrays, bucket_nodearray, b_index):
    prio = bucket_nodearray.priority
    if isinstance(prio, str):
        try:
            prio = int(float(prio))
        except Exception:
            prio = None
    if isinstance(prio, float):
        prio = int(prio)
    if isinstance(prio, int):
        if prio < 0:
            prio = None
    if prio is not None and not isinstance(prio, int):
        prio = None    
    if prio is None:
        prio = (nodearrays.index(bucket_nodearray.nodearray) + 1) * 10
    if prio > 0:
        return prio * 1000 - b_index
    assert prio == 0, f'Unexpected prio {prio} - should ALWAYS be >= 0.'
    return prio   

def simple_json_writer(data, debug_output=True):  # pragma: no cover
    data_str = json.dumps(data)
    if debug_output:
        logger.debug("Response: %s", data_str)
    print(data_str)
    return data


def true_gmt_clock():  # pragma: no cover
    import time
    return time.gmtime()


def main(argv=sys.argv, json_writer=simple_json_writer):  # pragma: no cover
    try:
        
        global logger
        provider_config, logger, fine = util.provider_config_from_environment()
        
        data_dir = os.getenv('PRO_DATA_DIR', os.getcwd())
        hostnamer = util.Hostnamer(provider_config.get("cyclecloud.hostnames.use_fqdn", True))
        cluster_name = provider_config.get("cyclecloud.cluster.name")
        
        provider = CycleCloudProvider(config=provider_config,
                                      cluster=cluster.Cluster(cluster_name, provider_config, logger),
                                      hostnamer=hostnamer,
                                      json_writer=json_writer,
                                      terminate_requests=JsonStore("terminate_requests.json", data_dir),
                                      creation_requests=JsonStore("create_requests.json", data_dir),
                                      templates=JsonStore("templates.json", data_dir, formatted=True),
                                      clock=true_gmt_clock)
        provider.fine = fine

        # every command has the format cmd -f input.json        
        cmd, ignore, input_json_path = argv[1:]

        input_json = util.load_json(input_json_path)
        operation_id = int(time.time())
        logger.info("BEGIN %s %s - %s %s", operation_id, cmd, ignore, input_json_path)
        logger.debug("Input: %s", json.dumps(input_json))
                
        if cmd == "templates":
            logger.info("Using azurecc version %s", version.get_version())
            provider.templates()
        elif cmd == "create_machines":
            provider.create_machines(input_json)
        elif cmd in ["status", "create_status", "terminate_status"]:
            if "requests" in input_json:
                # provider.status handles both create_status and deprecated terminate_status calls.
                provider.status(input_json)
            elif cmd == "terminate_status":
                # doesn't pass in a requestId but just a list of machines.
                provider.terminate_status(input_json)
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
        provider.periodic_cleanup(skip_templates=(cmd == "templates"))
            
    except ImportError as e:
        logger.exception(str(e))

    except Exception as e:
        if logger:
            logger.exception(str(e))
        else:
            import traceback
            traceback.print_exc()
    finally:
        logger.info("END %s %s - %s %s", operation_id, cmd, ignore, input_json_path)       

if __name__ == "__main__":
    main()  # pragma: no cover
else:
    logger = util.init_logging()
