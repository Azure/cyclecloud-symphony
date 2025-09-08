from copy import deepcopy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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
        self.new_node_manager = MagicMock(return_value=None)
        self.cluster_name = "mock_cluster"
        self._nodearrays = nodearrays
        self.buckets = []
        # self._nodearrays["nodearrays"].append({"name": "execute",
        #                                        "nodearray": {"Configuration": {"run_list": ["recipe[symphony::execute]"]}}})
        # template -> requestI
        self._nodes = {}
        self.raise_during_termination = False
        self.raise_during_add_nodes = False
        self.raise_during_nodes = False

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
            node['Status'] = 'Started'
            node['PrivateIp'] =  '10.0.0.%s' % instance_count
            
    def nodes(self, request_ids=[]):
        if self.raise_during_nodes:
           raise RuntimeError("raise_during_nodes")
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
                
    def set_buckets(self, buckets):
        self.buckets = buckets
        
    def get_buckets(self):
        return self.buckets
               
class RequestsStoreInMem:
    
    def __init__(self, requests=None):
        self.requests = {} if requests is None else requests
        
    def read(self):
        return self.requests
    
    def write(self, data):
        self.requests = deepcopy(data)
    
    def __enter__(self):
        return self.requests
    
    def __exit__(self, *args):
        pass
    
class NodeBucket:
    def __init__(self, nodearray, available, vm_size, id, resources, vcpu_count, max_count, software_configuration):
        self.nodearray = nodearray
        self.available = available
        self.vm_size = vm_size
        self.id = id
        self.resources = resources
        self.vcpu_count = vcpu_count 
        self.max_count = max_count   
        self.software_configuration = software_configuration
            
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
        output_handler = cyclecloud_provider.JsonOutputHandler(quiet=True)
        provider = cyclecloud_provider.CycleCloudProvider(provider_config, cluster, hostnamer, output_handler,  
                                                          terminate_requests=RequestsStoreInMem(), 
                                                          creation_requests=RequestsStoreInMem(),  
                                                          clock=epoch_clock)
        provider.request_tracker.reset()
        return provider
    
    def _new_provider_scalelib(self, provider_config=None, UserData=""):
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
        provider.request_tracker.reset()
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
        
        # Test for a case when exception raised during status call.
        provider.cluster.raise_during_nodes = True
        request_status = provider.status({'requests': [request1, request2]})
        self.assertEqual(RequestStates.running, request_status["status"])
        request_status1 = find_request_status(request_status, request1)
        request_status2 = find_request_status(request_status, request2)
        self.assertEqual(RequestStates.running, request_status1["status"])
        self.assertEqual(RequestStates.running, request_status2["status"])
        
        provider.cluster.complete_node_startup([request1['requestId'], request2['requestId']])
        
        provider.cluster.raise_during_nodes = False
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
        # self.assertEqual({'status': 'running', 'requests': [{'status': 'running', "message": "Unknown termination request id.", 'requestId': 'delete-missing', 'machines': []}]}, status_response)
        self.assertEqual({'status': 'running', 'requests': [{'status': 'complete_with_error', "message": "Warning: Ignoring unknown termination request id.", 'requestId': 'delete-missing', 'machines': []}]}, status_response)
        
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
        
        # test status is reported as running so that HF keeps requesting status of request.
        provider.cluster.raise_during_termination = True
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-123"}, {"name": "host-231", "machineId": "id-231"}]})
        failed_request_id = term_response["requestId"]
        term_response = provider.terminate_machines({"machines": [{"name": "host-123", "machineId": "id-1234"}]})
        failed_request_id2 = term_response["requestId"]
        status_response = provider.status({"requests": [{"requestId": failed_request_id}, {"requestId": failed_request_id2}]})
        self.assertEqual(status_response["status"], "running")
        self.assertEqual(len(status_response["requests"]), 2)
        self.assertEqual(status_response["requests"][0]["requestId"], failed_request_id)
        self.assertEqual(status_response["requests"][0]["machines"][0]["machineId"], "id-123")
        self.assertEqual(status_response["requests"][0]["machines"][1]["machineId"], "id-231")
        self.assertEqual(len(status_response["requests"][0]["machines"]), 2)
        self.assertEqual(status_response["requests"][0]["status"], "running") 
        self.assertEqual(status_response["requests"][1]["requestId"], failed_request_id2)
        self.assertEqual(status_response["requests"][1]["machines"][0]["machineId"], "id-1234")
        self.assertEqual(len(status_response["requests"][1]["machines"]), 1)
        self.assertEqual(status_response["requests"][1]["status"], "running") 
        
        
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

    def test_bucket_priority(self):
        nodearrays = [{"name": "n1","nodearray":{}}]
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(9999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": None}}]
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(9999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": 9}}]
        self.assertEqual(9000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(8999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": 9.9}}]
        self.assertEqual(9000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(8999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        buckets = [NodeBucket(nodearray="n1", bucket_id="abcd2", priority="9.9"), NodeBucket(nodearray="n1", bucket_id="abcd3", priority=9.9)]
        self.assertEqual(8999, cyclecloud_provider.bucket_priority(buckets, buckets[1]))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": "9"}}]
        self.assertEqual(9000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(8999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": "9.9"}}]
        self.assertEqual(9000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(8999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": 0}}]
        self.assertEqual(0, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(0, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": -4}}]
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(9999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": "-4"}}]
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(9999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": [1,2,3]}}]
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(9999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray": {"Priority": "[1,2,3]"}}]
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(9999, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=1))
        
        nodearrays = [{"name": "n1", "nodearray":{}}, {"name": "n2", "nodearray":{}}]
        self.assertEqual(20000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(10000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[1], b_index=0))
        
        nodearrays = [{"name": "n1", "nodearray":{}}, {"name": "n2", "nodearray": {"Priority": 20}}]
        self.assertEqual(20000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[0], b_index=0))
        self.assertEqual(20000, cyclecloud_provider.bucket_priority(nodearrays, nodearrays[1], b_index=0))
 
    
    def test_validate_templates(self):
        provider = self._new_provider()
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"templates":[]})
            self.assertFalse(provider.validate_template())
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({})
            self.assertFalse(provider.validate_template())
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"templates":[{"templateId":"execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100, "vmTypes":{"A4":2}}]})
            self.assertFalse(provider.validate_template())
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"templates":[{"templateId":"execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100, "vmTypes":{"A4":2}}]})
            self.assertFalse(provider.validate_template())
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"templates":[{"templateId":"execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100}]})
            self.assertFalse(provider.validate_template())
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"templates":[{"templateId":"execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100, "vmTypes":{"A4":1, "A8":1}}, 
                                                                                                       {"templateId":"lp_execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100, "vmTypes":{"A4":1, "A8":1}}]})
            self.assertTrue(provider.validate_template())
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"templates":[{"templateId":"execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100, "vmTypes":{"A4":1, "A8":1}}, 
                                                                                                       {"templateId":"lp_execute","attributes":{"ncores":["Numeric","1"],"ncpus":["Numeric","1"],"mem":["Numeric","1024"],"type":["String","X86_64"]},"maxNumber":100, "vmTypes":{"A4":1}}]})
            self.assertFalse(provider.validate_template())
     
  
    def test_generate_sample_template(self):
        saved_stdout = sys.stdout
        from io import StringIO
        capture_output = StringIO()
        sys.stdout = capture_output
        return_value = [NodeBucket("execute", 50, "A2", "cdcd4c31-3bbf-48af-b266-1c3de4b8a3d4", resources={"ncores":1}, vcpu_count=1, max_count=100, software_configuration={ "autoscaling": {"enabled": True}}),
                        NodeBucket("execute", 50, "A4", "cdcd4c31-3bbf-48af-b266-1c3de4b8a3d4", resources={"ncores":2}, vcpu_count=2, max_count=50, software_configuration={ "autoscaling": {"enabled": True}})]
        provider = self._new_provider()
        provider.cluster.set_buckets(return_value)
        provider.generate_sample_template()
        json_data = json.loads(capture_output.getvalue())
        self.assertEqual(1, len(json_data["templates"]))
        self.assertEqual(2, len(json_data["templates"][0]["vmTypes"]))
        # Check weights
        self.assertEqual(json_data["templates"][0]["vmTypes"]["A2"], 1)
        self.assertEqual(json_data["templates"][0]["vmTypes"]["A4"], 2)
         
        print(json_data["templates"][0], file=saved_stdout)
        # json_data was already parsed from the captured output above; ensure it's truthy
        self.assertTrue(json_data)
        sys.stdout = saved_stdout
        
    
    def test_generate_sample_template_config(self):
        saved_stdout = sys.stdout
        from io import StringIO
        capture_output = StringIO()
        sys.stdout = capture_output
        return_value = [NodeBucket("execute", 50, "A4", "cdcd4c31-3bbf-48af-b266-1c3de4b8a3d4", resources={"ncores":4}, vcpu_count=4, max_count=200, software_configuration={ "autoscaling": {"enabled": True}}),
                        NodeBucket("execute", 50, "A8", "cdcd4c31-3bbf-48af-b266-1c3de4b8a3d4", resources={"ncores":8}, vcpu_count=8, max_count=100, software_configuration={ "autoscaling": {"enabled": True}})]
        config = {"symphony.autoscaling.ncpus": 2, "symphony.autoscaling.nram": 8129}
        provider = self._new_provider(provider_config=config)
        provider.cluster.set_buckets(return_value)
        provider.generate_sample_template()
        json_data = json.loads(capture_output.getvalue())
        self.assertEqual(1, len(json_data["templates"]))
        self.assertEqual(2, len(json_data["templates"][0]["vmTypes"]))
        self.assertEqual(json_data["templates"][0]["attributes"]["ncpus"], ["Numeric", "2"])
        self.assertEqual(json_data["templates"][0]["attributes"]["nram"], ["Numeric", "8129"])
        # Check weights
        self.assertEqual(json_data["templates"][0]["vmTypes"]["A4"], 2) 
        self.assertEqual(json_data["templates"][0]["vmTypes"]["A8"], 4)
        self.assertEqual(json_data["templates"][0]["maxNumber"], 800)
        print(json_data["templates"][0], file=saved_stdout)
        # json_data was already parsed from the captured output above; ensure it's truthy
        self.assertTrue(json_data)
        sys.stdout = saved_stdout
                 

if __name__ == "__main__":
    unittest.main()
