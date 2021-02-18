from copy import deepcopy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import cyclecloud_provider
from symphony import RequestStates, MachineStates, MachineResults
# import test_json_source_helper
# from util import JsonStore
import util


MACHINE_TYPES = {
    "A4": {"Name": "A4", "vcpuCount": 4, "memory": 1., "Location": "ukwest", "Quota": 10},
    "A8": {"Name": "A8", "vcpuCount": 8, "memory": 2., "Location": "ukwest", "Quota": 20}
}


class MockClock:
    
    def __init__(self, now):
        self.now = now
        
    def __call__(self):
        return self.now
    
    
class MockHostnamer:
    
    def hostname(self, private_ip_address):
        return "ip-" + private_ip_address.replace(".", "-")
    

class MockCluster:
    def __init__(self, nodearrays):
        self.cluster_name = "mock_cluster"
        self._nodearrays = nodearrays
        self._nodearrays["nodearrays"].append({"name": "execute",
                                               "nodearray": {"Configuration": {"run_list": ["recipe[symphony::execute]"]}}})
        # template -> requestI
        self._nodes = {}
        self.raise_during_termination = False
        self.raise_during_add_nodes = False

        # {<MachineType>: <ActualCapacity != MaxCount>} 
        # {'standard_a8': 1} => max of 1 VM will be returned by add_nodes regardless of requested count
        self.limit_capacity = {}

    def status(self):
        return self._nodearrays

    def add_nodes(self, request_all):
        '''
                self.cluster.add_node({'Name': nodearray_name,
                                'TargetCount': machine_count,
                                'MachineType': machine_type,
                                "RequestId": request_id,
                                "Configuration": {"symphony": {"user_data": json.dumps(user_data)}}
                                })
        '''
        if self.raise_during_add_nodes:
            raise RuntimeError("raise_during_add_nodes")
        request = request_all["sets"][0]
        nodearray = request["nodearray"]
        request_id = request_all["requestId"]
        count = request["count"]
        machine_type = request["definition"]["machineType"]
        node_attrs = request["nodeAttributes"]
        
        if nodearray not in self._nodes:
            self._nodes[nodearray] = []
            
        node_list = self._nodes[nodearray]

        if machine_type in self.limit_capacity:
            available_capacity = self.limit_capacity[machine_type]
            if count > available_capacity:
                print("Capacity Limited! <%s>  Requested: <%d>  Available Capacity: <%d>" % (machine_type, count, available_capacity))
                count = available_capacity

        for i in range(count):
            node_index = len(node_list) + i + 1
            node = {"Name": "%s-%d" % (nodearray, node_index),
                    "NodeId": "%s-%d_id" % (nodearray, node_index),
                    "RequestId": request_id,
                    "machineType": MACHINE_TYPES[machine_type],
                    "Status": "Allocating",
                    "TargetState": "Started"
            }
            node.update(node_attrs)
            node_list.append(node)


    def complete_node_startup(self, request_ids=[]):
        instance_count = 0
        for node in self.inodes(RequestId=request_ids):
            node['InstanceId'] = '%s_%s' % (node["RequestId"], instance_count)
            node['State'] = 'Started'
            node['PrivateIp'] =  '10.0.0.%s' % instance_count
            
    def nodes(self, request_ids=[]):
        ret = {}
        
        for request_id in request_ids:
            ret[request_id] = {"nodes": []}
            
        for node in self.inodes(RequestId=request_ids):
            ret[node["RequestId"]]["nodes"].append(node)
        return ret
            
    def inodes(self, **attrs):
        '''
        Just yield each node that matches the attrs specified. If the value is a 
        list or set, use 'in' instead of ==
        '''
        
        def _yield_nodes(**attrs):
            for nodes_for_template in self._nodes.values():
                for node in nodes_for_template:
                    all_match = True                                        
                    for key, value in attrs.items():
                        if isinstance(value, list) or isinstance(value, set):
                            all_match = all_match and node[key] in value
                        else:
                            all_match = all_match and node[key] == value
                    if all_match:
                        yield node
        return list(_yield_nodes(**attrs))
    
    def terminate(self, machines):
        if self.raise_during_termination:
            raise RuntimeError("raise_during_termination")
        
        for node in self.inodes():
            for machine in machines:
                if node.get("NodeId") == machine["machineId"]:
                    node["Status"] = "TerminationPreparation"
                    node["TargetState"] = "Terminated"
                
                
class RequestsStoreInMem:
    
    def __init__(self, requests=None):
        self.requests = {} if requests is None else requests
        
    def read(self):
        return self.requests
    
    def __enter__(self):
        return self.requests
    
    def __exit__(self, *args):
        pass
    
    
def json_writer(data, debug_output=False):
    return data
            
            
class TestHostFactory(unittest.TestCase):

    def test_simple_lifecycle(self):
        provider = self._new_provider()
        provider.cluster._nodearrays["nodearrays"][0]["buckets"].pop(1)
        
        templates = provider.templates()["templates"]
        
        self.assertEqual(3, len(templates))
        self.assertEqual("executea4", templates[0]["templateId"])
        # WARNING: LSF does not quote Numerics and Symphony does (Symphony will likely upgrade to match LSF eventually)
        self.assertEqual(["Numeric", '4'], templates[0]["attributes"]["ncores"])
        self.assertEqual(["Numeric", '1'], templates[0]["attributes"]["ncpus"])
        
        provider.cluster._nodearrays["nodearrays"][0]["buckets"].append({"maxCount": 2, "definition": {"machineType": "A8"}, "virtualMachine": MACHINE_TYPES["A8"]})
        
        templates = provider.templates()["templates"]
        
        self.assertEqual(4, len(templates))
        a4 = [t for t in templates if t["templateId"] == "executea4"][0]
        a8 = [t for t in templates if t["templateId"] == "executea8"][0]
        lpa4 = [t for t in templates if t["templateId"] == "lpexecutea4"][0]
        lpa8 = [t for t in templates if t["templateId"] == "lpexecutea8"][0]
        
        self.assertEqual(["Numeric", '4'], a4["attributes"]["ncores"])
        self.assertEqual(["Numeric", '1'], a4["attributes"]["ncpus"])
        self.assertEqual(["Numeric", '1024'], a4["attributes"]["mem"])
        self.assertEqual(["String", "X86_64"], a4["attributes"]["type"])
        
        self.assertEqual(["Numeric", '8'], a8["attributes"]["ncores"])
        self.assertEqual(["Numeric", '1'], a8["attributes"]["ncpus"])
        self.assertEqual(["Numeric", '2048'], a8["attributes"]["mem"])
        self.assertEqual(["String", "X86_64"], a8["attributes"]["type"])


        self.assertEqual(["Boolean", "0"], a4["attributes"]["azurecclowprio"])
        self.assertEqual(["Boolean", "0"], a8["attributes"]["azurecclowprio"])
        self.assertEqual(["Boolean", "1"], lpa4["attributes"]["azurecclowprio"])
        self.assertEqual(["Boolean", "1"], lpa8["attributes"]["azurecclowprio"])
        
        
        request = provider.create_machines(self._make_request("executea4", 1))
        
        def run_test(node_status="Allocation", node_target_state="Started", expected_machines=1, instance={"InstanceId": "i-123", "PrivateIp": "10.0.0.1"},
                     expected_request_status=RequestStates.running, expected_node_status=None,
                     expected_machine_status=MachineStates.building, expected_machine_result=MachineResults.executing,
                     node_status_message=None, status_type="create"):
            if expected_node_status is None:
                expected_node_status = node_status
                
            mutable_node = provider.cluster.inodes(Name="execute-1")
            mutable_node[0]["State"] = node_status
            mutable_node[0]["TargetState"] = node_target_state
            mutable_node[0]["Instance"] = instance
            mutable_node[0]["InstanceId"] = instance["InstanceId"] if instance else None
            mutable_node[0]["StatusMessage"] = node_status_message
            mutable_node[0]["PrivateIp"] = (instance or {}).get("PrivateIp")
            
            if status_type == "create":
                statuses = provider.status({"requests": [{"requestId": request["requestId"], 'sets': [request]}]})
            else:
                statuses = provider.status({"requests": [{"requestId": request["requestId"], 'sets': [request]}]})
                
            request_status_obj = statuses["requests"][0]
            self.assertEqual(expected_request_status, request_status_obj["status"])
            machines = request_status_obj["machines"]
            self.assertEqual(expected_machines, len(machines))
            self.assertEqual(expected_node_status, mutable_node[0]["State"])

            if expected_machines == 0:
                return
            
            for n, m in enumerate(machines):
                if m["privateIpAddress"]:
                    self.assertEqual(MockHostnamer().hostname(m["privateIpAddress"]), m["name"])
                self.assertEqual("execute-%d_id" % (n + 1), m["machineId"])
                self.assertEqual(expected_machine_status, m["status"])
                self.assertEqual(expected_machine_result, m["result"])
            
            if node_status == "Failed" and provider.config.get("symphony.terminate_failed_nodes", False):
                mutable_node = provider.cluster.inodes(Name="execute-1")
                self.assertEqual(mutable_node[0].get("TargetState"), "Terminated")
            else:
                mutable_node = provider.cluster.inodes(Name="execute-1")
                self.assertEqual(mutable_node[0].get("TargetState"), node_target_state)
            
        # no instanceid == no machines
        run_test(instance=None, expected_machines=0)

        # has an instance
        run_test(expected_machines=1)
        
        # has an instance, but Failed
        run_test(expected_machines=1, node_status="Failed", node_status_message="fail for tests",
                 expected_request_status=RequestStates.complete_with_error,
                 expected_machine_status=MachineStates.error,
                 expected_machine_result=MachineResults.failed)

        # has an instance, but Failed and we're configured to Terminate Failed nodes
        provider.config.set("symphony.terminate_failed_nodes", True)
        run_test(expected_machines=1, node_status="Failed", node_status_message="fail for tests",
                 expected_request_status=RequestStates.running,
                 expected_machine_status=MachineStates.building,
                 expected_machine_result=MachineResults.executing)

                
        # node is ready to go
        run_test(node_status="Started", expected_machine_result=MachineResults.succeed, 
                                      expected_machine_status=MachineStates.active,
                                      expected_request_status=RequestStates.complete)
        
        # someone somewhere else changed the target state
        run_test(expected_machines=0, node_status="Off", node_target_state="Off",
                 expected_request_status=RequestStates.complete)
        
    def _new_provider(self, provider_config=None, UserData=""):
        provider_config = provider_config or util.ProviderConfig({}, {})
        a4bucket = {"maxCount": 2, "activeCount": 0, "definition": {"machineType": "A4"}, "virtualMachine": MACHINE_TYPES["A4"]}
        a8bucket = {"maxCoreCount": 24, "activeCount": 0, "definition": {"machineType": "A8"}, "virtualMachine": MACHINE_TYPES["A8"]}
        cluster = MockCluster({"nodearrays": [{"name": "execute",
                                               "UserData": UserData,                                               
                                               "nodearray": {"machineType": ["a4", "a8"], "Interruptible": False, "Configuration": {"autoscaling": {"enabled": True}, "symphony": {"autoscale": True}}},
                                               "buckets": [a4bucket, a8bucket]},
                                               {"name": "lp_execute",
                                               "UserData": UserData,
                                               "nodearray": {"machineType": ["a4", "a8"], "Interruptible": True, "Configuration": {"autoscaling": {"enabled": True}, "symphony": {"autoscale": True}}},
                                               "buckets": [a4bucket, a8bucket]}]})
        epoch_clock = MockClock((1970, 1, 1, 0, 0, 0))
        hostnamer = MockHostnamer()
        provider = cyclecloud_provider.CycleCloudProvider(provider_config, cluster, hostnamer, json_writer, RequestsStoreInMem(), RequestsStoreInMem(), epoch_clock)
        provider.capacity_tracker.reset()
        return provider
    
    def _make_request(self, template_id, machine_count, rc_account="default", user_data={}):
        return {"user_data": user_data,
               "rc_account": rc_account,
               "template": {"templateId": template_id,
                            "machineCount": machine_count
                }
            }

    def test_create(self):
        provider = self._new_provider()
        provider.templates()
        request1 = provider.create_machines(self._make_request("executea4", 1))
        self.assertEqual(RequestStates.running, request1["status"])

        request2 = provider.create_machines(self._make_request("executea4", 4))
        self.assertEqual(RequestStates.running, request2["status"])

        # Order of statuses is undefined
        def find_request_status(request_status, request):
            for rqs in request_status['requests']:
                if rqs['requestId'] == request['requestId']:
                    return rqs
            return None

        request_status = provider.status({'requests': [request1, request2]})
        self.assertEqual(RequestStates.complete, request_status["status"])
        request_status1 = find_request_status(request_status, request1)
        request_status2 = find_request_status(request_status, request2)
        self.assertEqual(RequestStates.running, request_status1["status"])
        self.assertEqual(0, len(request_status1["machines"]))
        self.assertEqual(RequestStates.running, request_status2["status"])
        self.assertEqual(0, len(request_status2["machines"]))

        provider.cluster.complete_node_startup([request1['requestId'], request2['requestId']])

        request_status = provider.status({'requests': [request1, request2]})
        self.assertEqual(RequestStates.complete, request_status["status"])
        request_status1 = find_request_status(request_status, request1)
        request_status2 = find_request_status(request_status, request2)
        self.assertEqual(RequestStates.complete, request_status1["status"])
        self.assertEqual(1, len(request_status1["machines"]))
        self.assertEqual(RequestStates.complete, request_status2["status"])
        self.assertEqual(4, len(request_status2["machines"]))

    def test_capacity_limited_create(self):
        provider = self._new_provider()
        a4bucket, a8bucket = provider.cluster._nodearrays["nodearrays"][0]["buckets"]
        
        # we can _never_ return an empty list, so in the case of no remaining capacity, return placeholder
        # a8bucket["maxCoreCount"] = 0  
        # self.assertEqual(cyclecloud_provider.PLACEHOLDER_TEMPLATE, provider.templates()["templates"][0])
        
        # CC thinks there are up to 50 VMs available
        a4bucket["maxCount"] = 50
        templates = provider.templates()
        self.assertEqual(50, templates["templates"][0]["maxNumber"])

        # Request 10 VMs, but get 1 due to out-of-capacity 
        provider.cluster.limit_capacity[a4bucket['definition']['machineType']] = 1
        request = provider.create_machines(self._make_request("executea4", 10))
        self.assertEqual(RequestStates.running, request["status"])

        provider.cluster.complete_node_startup([request['requestId']])

        request_status = provider.status({'requests': [request]})
        self.assertEqual(RequestStates.complete, request_status["status"])
        self.assertEqual(RequestStates.complete, request_status["requests"][0]["status"])
        self.assertEqual(1, len(request_status["requests"][0]["machines"]))

        # IMPORTANT: 
        # Since numRequested < MaxCount and numCreated < numRequested, we're going to assume 
        # that remaining Capacity for this bucket is 0!


        
    def test_terminate(self):
        provider = self._new_provider()
        term_requests = provider.terminate_json
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-123"}]})
        
        self.assertEqual(term_response["status"], "complete")
        self.assertTrue(term_response["requestId"] in term_requests.requests)
        self.assertEqual({"id-123": "host-123"}, term_requests.requests[term_response["requestId"]]["machines"])
        
        status_response = provider.status({"requests": [{"requestId": term_response["requestId"]}]})
        self.assertEqual(1, len(status_response["requests"]))
        self.assertEqual(1, len(status_response["requests"][0]["machines"]))
        
        status_response = provider.status({"requests": [{"requestId": "missing"}]})
        self.assertEqual({'status': 'complete', 'requests': [{'status': 'complete', 'message': '', 'requestId': 'missing', 'machines': []}]}, status_response)
        
        status_response = provider.status({"requests": [{"requestId": "delete-missing"}]})
        self.assertEqual({'status': 'running', 'requests': [{'status': 'running', "message": "Unknown termination request id.", 'requestId': 'delete-missing', 'machines': []}]}, status_response)
        
    def test_terminate_status(self):
        provider = self._new_provider()
        term_requests = provider.terminate_json
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-123"}]})
        
        self.assertEqual(term_response["status"], "complete")
        self.assertTrue(term_response["requestId"] in term_requests.requests)
        self.assertEqual({"id-123": "host-123"}, term_requests.requests[term_response["requestId"]]["machines"])
        
        status_response = provider.terminate_status({"machines": [{"machineId": "id-123", "name": "host-123"}]})
        self.assertEqual(1, len(status_response["requests"]))
        self.assertEqual(1, len(status_response["requests"][0]["machines"]))
        
        status_response = provider.terminate_status({"machines": [{"machineId": "missing", "name": "missing-123"}]})
        self.assertEqual({'requests': [], 'status': 'complete'}, status_response)
        
    def test_terminate_error(self):
        provider = self._new_provider()
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-123"}]})
        self.assertEqual(term_response["status"], RequestStates.complete)
        
        # if it raises an exception, don't mark the request id as successful.
        provider.cluster.raise_during_termination = True
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-123"}]})
        self.assertEqual(RequestStates.running, term_response["status"])
        failed_request_id = term_response["requestId"]
        self.assertNotEquals(True, provider.terminate_json.read()[term_response["requestId"]].get("terminated"))
        
        # if it raises an exception, don't mark the request id as successful.
        provider.cluster.raise_during_termination = False
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-123"}]})
        self.assertEqual(RequestStates.complete, term_response["status"])
        self.assertEqual(True, provider.terminate_json.read()[term_response["requestId"]].get("terminated"))
        
        provider.status({"requests": [{"requestId": failed_request_id}]})
        self.assertEqual(True, provider.terminate_json.read()[failed_request_id].get("terminated"))
        
    # def test_json_store_lock(self):
    #     json_store = JsonStore("test.json", "/tmp")
        
    #     json_store._lock()
    #     self.assertEqual(101, subprocess.call([sys.executable, test_json_source_helper.__file__, "test.json", "/tmp"]))
        
    #     json_store._unlock()
    #     self.assertEqual(0, subprocess.call([sys.executable, test_json_source_helper.__file__, "test.json", "/tmp"]))
        
    def test_templates(self):
        provider = self._new_provider()
        a4bucket, a8bucket = provider.cluster._nodearrays["nodearrays"][0]["buckets"]
        nodearray = {"MaxCoreCount": 100}
        self.assertEqual(2, provider._max_count('execute', nodearray, 4, {"maxCount": 2, "definition": {"machineType": "A$"}}))
        self.assertEqual(3, provider._max_count('execute', nodearray, 8, {"maxCoreCount": 24, "definition": {"machineType": "A$"}}))
        self.assertEqual(3, provider._max_count('execute', nodearray, 8, {"maxCoreCount": 25, "definition": {"machineType": "A$"}}))
        self.assertEqual(3, provider._max_count('execute', nodearray, 8, {"maxCoreCount": 31, "definition": {"machineType": "A$"}}))
        self.assertEqual(4, provider._max_count('execute', nodearray, 8, {"maxCoreCount": 32, "definition": {"machineType": "A$"}}))
        
        # simple zero conditions
        self.assertEqual(0, provider._max_count('execute', nodearray, 8, {"maxCoreCount": 0, "definition": {"machineType": "A$"}}))
        self.assertEqual(0, provider._max_count('execute', nodearray, 8, {"maxCount": 0, "definition": {"machineType": "A$"}}))
        
        # error conditions return -1
        nodearray = {}
        self.assertEqual(-1, provider._max_count('execute', nodearray, -100, {"maxCoreCount": 32, "definition": {"machineType": "A$"}}))
        self.assertEqual(-1, provider._max_count('execute', nodearray, -100, {"maxCount": 32, "definition": {"machineType": "A$"}}))
        self.assertEqual(-1, provider._max_count('execute', nodearray, 4, {"definition": {"machineType": "A$"}}))
        self.assertEqual(-1, provider._max_count('execute', nodearray, 4, {"maxCount": -100, "definition": {"machineType": "A$"}}))
        self.assertEqual(-1, provider._max_count('execute', nodearray, 4, {"maxCoreCount": -100, "definition": {"machineType": "A$"}}))
        
        a4bucket["maxCount"] = 0
        a8bucket["maxCoreCount"] = 0  # we can _never_ return an empty list
        self.assertEqual(cyclecloud_provider.PLACEHOLDER_TEMPLATE, provider.templates()["templates"][0])
        
        a8bucket["maxCoreCount"] = 24
        self.assertEqual(3, provider.templates()["templates"][-1]["maxNumber"])
        a8bucket["maxCoreCount"] = 0
        
        a4bucket["maxCount"] = 100
        self.assertEqual(100, provider.templates()["templates"][0]["maxNumber"])


    def test_reprioritize_template(self):
        provider = self._new_provider()
        
        def any_template(template_name):
            return [x for x in provider.templates()["templates"] if x["templateId"].startswith(template_name)][0]

        def templates_by_prio():
            return 
        
        provider.config.set("templates.default.attributes.custom", ["String", "custom_default_value"])
        provider.config.set("templates.execute.attributes.custom", ["String", "custom_override_value"])
        provider.config.set("templates.execute.attributes.custom2", ["String", "custom_value2"])
        provider.config.set("templates.other.maxNumber", 0)
        
        # a4 overrides the default and has custom2 defined as well
        attributes = any_template("execute")["attributes"]
        self.assertEqual(["String", "custom_override_value"], attributes["custom"])
        self.assertEqual(["String", "custom_value2"], attributes["custom2"])
        self.assertEqual(["Numeric", '1024'], attributes["mem"])
        
    def test_errors(self):
        provider = self._new_provider()
        provider.cluster.raise_during_add_nodes = True
        provider.templates()
        response = provider.create_machines(self._make_request("executea4", 1))
        self.assertEqual('Azure CycleCloud experienced an error, though it may have succeeded: raise_during_add_nodes', response["message"])
        self.assertEqual(RequestStates.running, response["status"])
        self.assertNotEquals(None, response.get("requestId"))
        
        provider.cluster.raise_during_termination = True
        term_response = provider.terminate_machines({"machines": [{"machineId": "mach123", "name": "n-1-123"}]})
        self.assertEqual(RequestStates.running, term_response["status"])
                                                     
    def test_missing_template_in_request(self):
        provider = self._new_provider()
        provider.templates_json.requests.clear()
        request = provider.create_machines(self._make_request("executea4", 1))
        self.assertEqual(RequestStates.complete_with_error, request["status"])
        
    def test_expired_terminations(self):
        provider = self._new_provider()
        term_response = provider.terminate_machines({"machines": [{"machineId": "id-123", "name": "e-1-123"},
                                                                  {"machineId": "id-124", "name": "e-2-234"}]})
        self.assertEqual(RequestStates.complete, term_response["status"])
        stat_response = provider.status({"requests": [{"requestId": term_response["requestId"]}]})
        self.assertEqual(RequestStates.complete, stat_response["requests"][0]["status"])
        self.assertIn(term_response["requestId"], provider.terminate_json.read())
        
        # expires after 2 hours, so this is just shy of 2 hours
        provider.clock.now = (1970, 1, 1, 1.99, 0, 0)
        
        expired_request = term_response["requestId"]
        
        term_response = provider.terminate_machines({"machines": [{"machineId": "id-234", "name": "n-1-123"}]})
        stat_response = provider.status({"requests": [{"requestId": term_response["requestId"]}]})
        self.assertEqual(RequestStates.complete, stat_response["requests"][0]["status"])
        self.assertIn(expired_request, provider.terminate_json.read())
        
        # just over 2 hours, it will be gone.
        provider.clock.now = (1970, 1, 1, 2.01, 0, 0)
        with provider.terminate_json as requests:
            for _, request in requests.items():
                request["terminated"] = False
        stat_response = provider.status({"requests": [{"requestId": term_response["requestId"]}]})
        self.assertIn(expired_request, provider.terminate_json.read())
        
        with provider.terminate_json as requests:
            for _, request in requests.items():
                request["terminated"] = True
        stat_response = provider.status({"requests": [{"requestId": term_response["requestId"]}]})
        self.assertNotIn(expired_request, provider.terminate_json.read())
        
    def test_disable_but_do_not_delete_missing_buckets(self):
        provider = self._new_provider()
        templates = provider.templates()["templates"]
        
        def _maxNumber(name):
            ret = [t for t in templates if t["templateId"] == name]
            self.assertEqual(1, len(ret))
            return ret[0]["maxNumber"]
        
        self.assertTrue(_maxNumber("executea4") > 0)
        self.assertTrue(_maxNumber("executea8") > 0)
        
        provider.cluster._nodearrays["nodearrays"][0]["buckets"] = [{"maxCount": 2, "definition": {"machineType": "A4"}, "virtualMachine": MACHINE_TYPES["A4"]}]
        templates = provider.templates()["templates"]
        
        self.assertTrue(_maxNumber("executea4") > 0)
        self.assertTrue(_maxNumber("executea8") == 0)
        
    def test_override_template(self):
        provider = self._new_provider()
        other_array = deepcopy(provider.cluster._nodearrays["nodearrays"][0])
        other_array["name"] = "other"
        provider.cluster._nodearrays["nodearrays"].append(other_array)
        
        def any_template(template_name):
            return [x for x in provider.templates()["templates"] if x["templateId"].startswith(template_name)][0]
        
        provider.config.set("templates.default.attributes.custom", ["String", "custom_default_value"])
        provider.config.set("templates.execute.attributes.custom", ["String", "custom_override_value"])
        provider.config.set("templates.execute.attributes.custom2", ["String", "custom_value2"])
        provider.config.set("templates.other.maxNumber", 0)
        
        # a4 overrides the default and has custom2 defined as well
        attributes = any_template("execute")["attributes"]
        self.assertEqual(["String", "custom_override_value"], attributes["custom"])
        self.assertEqual(["String", "custom_value2"], attributes["custom2"])
        self.assertEqual(["Numeric", '1024'], attributes["mem"])
        
        # a8 only has the default
        attributes = any_template("other")["attributes"]
        self.assertEqual(["String", "custom_default_value"], attributes["custom"])
        self.assertNotIn("custom2", attributes)
        self.assertEqual(0, any_template("other")["maxNumber"])
        
    def test_invalid_template(self):
        provider = self._new_provider()
        response = provider.create_machines(self._make_request("nonsense", 1))
        self.assertEqual(RequestStates.complete_with_error, response["status"])
        
    def test_provider_config_from_env(self):
        tempdir = tempfile.mkdtemp()
        confdir = os.path.join(tempdir, "conf")
        os.makedirs(confdir)
        try:
            with open(os.path.join(confdir, "azureccprov_config.json"), "w") as fw:
                json.dump({}, fw)
                
            with open(os.path.join(confdir, "azureccprov_templates.json"), "w") as fw:
                json.dump({"templates": 
                           [{"templateId": "default", "attributes": {"custom": ["String", "VALUE"]}}]}, fw)
            
            config, _logger, _fine = util.provider_config_from_environment(tempdir)
            provider = self._new_provider(provider_config=config)
            for template in provider.templates()["templates"]:
                self.assertIn(template["templateId"], ["executea4", "executea8", "lpexecutea4", "lpexecutea8"])
                assert "custom" in template["attributes"]
                self.assertEqual(["String", "VALUE"], template["attributes"]["custom"])
            
        except Exception:
            shutil.rmtree(tempdir, ignore_errors=True)
            raise
        
    def test_custom_env(self):
        config = util.ProviderConfig({}, {})
        provider = self._new_provider(config)
        
        config.set("templates.default.UserData", "abc=123;def=1==1")
        provider_templates = provider.templates()
        self.assertEqual({"abc": "123", "def": "1==1"}, provider_templates["templates"][0]["UserData"]["symphony"]["custom_env"])
        self.assertEqual("abc def", provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env_names"])
        
        config.set("templates.default.UserData", "abc=123;def=1==1;")
        self.assertEqual({"abc": "123", "def": "1==1"}, provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env"])
        self.assertEqual("abc def", provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env_names"])
        
        config.set("templates.default.UserData", "abc=123;def=1==1;bad_form")
        
        self.assertEqual({"abc": "123", "def": "1==1"}, provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env"])
        self.assertEqual("abc def", provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env_names"])
        
        config.set("templates.default.UserData", "abc=123;def=1==1;good_form=234;bad_form_123")
        self.assertEqual({"abc": "123", "def": "1==1", "good_form": "234"}, provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env"])
        self.assertEqual("abc def good_form", provider.templates()["templates"][0]["UserData"]["symphony"]["custom_env_names"])
        
        def assert_no_user_data():
            templates = provider.templates()
            self.assertNotIn("custom_env", templates["templates"][0]["UserData"]["symphony"])
            self.assertNotIn("custom_env_names", templates["templates"][0]["UserData"]["symphony"])
            
        config.set("templates.default.UserData", ";")
        assert_no_user_data()
        
        config.set("templates.default.UserData", None)
        assert_no_user_data()
        
        config.set("templates.default.UserData", "all;around;bad")
        assert_no_user_data()


if __name__ == "__main__":
    unittest.main()
