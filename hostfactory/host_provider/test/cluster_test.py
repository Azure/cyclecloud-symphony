import unittest
import cluster
import logging
from unittest.mock import MagicMock
from unittest.mock import patch


class MockResult:
    def __init__(self, node_list):
        self.nodes = node_list
class MockNodeMgr:
    
    def __init__(self, expect=[], expected_new_nodes_list=[]):
        self.expect = expect
        self.expected_new_nodes_list = expected_new_nodes_list
    
    def allocate(self,
        constraints,
        node_count = None,
        slot_count = None,
        allow_existing = True,
        all_or_nothing = False,
        assignment_id = None,
        node_namer = None):
        list_args = []
        list_args.append(constraints)
        list_args.append(slot_count)
        list_args.append(allow_existing)
        expected_args = self.expect.pop(0)
        assert expected_args == list_args, f"Expected {list_args} got {expected_args}"
        if not self.expected_new_nodes_list:
           result = MockResult([])
        else:
           result = MockResult(self.expected_new_nodes_list)
        
        return result
        
    def expect(self, *args):
        self.expect.append(args)
        
    def get_new_nodes(self):        
        return self.expected_new_nodes_list
    
def set_node_list(node_name, node_count, weight=1):
    # concatenate node_name with a number to create a list of nodes
    return([MockNode(node_name + str(i), weight) for i in range(node_count)])
class MockNode:
    def __init__(self,node_name, weight):
       self.name = node_name
       self.resources = {"weight": weight}
    
 
class TestCluster(unittest.TestCase):
    
    def test_limit_request_by_available_count(self):
        pass
        #self.provider.config.set("symphony.disable_active_count_fix", True)
        cluster_name = "TestCluster"
        provider_config = {"User" : "abcd"}
        cluster.new_node_manager = MagicMock(return_value=None)
        cluster_test = cluster.Cluster(cluster_name, provider_config, logging)
        def make_new_request(machine_count=1):
            request_set = {'count': machine_count,                       
                        'requestId': "abcd",
                        'definition': {'machineType': "Standard_D2_v2"},
                        'nodeAttributes': {'Tags': {"foo": "bar"},
                                            'Configuration': "user_data"},
                        'nodearray': 'execute'}
            request = {'requestId': "abcd",'sets': [request_set]}
            return request
        
        status ={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                        "machineType": "Standard_D2_v2"
                    },"availableCount":100}]} ]}
        
            
        def run_test(request_count, expected_count, disable_active_count_fix=False):
            req = make_new_request(request_count)
            if disable_active_count_fix:
                cluster_test.provider_config["symphony.disable_active_count_fix"] = True
            limited_req = cluster_test.limit_request_by_available_count(status, req, logging)
            self.assertEqual(limited_req["sets"][0]["count"], expected_count)  
        
        def run_test_zero_available(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                "machineType": "Standard_D2_v2"
            },"availableCount":0}]} ]}
            self.assertRaises(RuntimeError, cluster_test.limit_request_by_available_count, status, req, logging) 
               
        def run_test_nodearray_removed(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute2", "buckets": [{"definition": {
                "machineType": "Standard_D2_v2"
            },"availableCount":100}]} ]}
            self.assertRaises(RuntimeError, cluster_test.limit_request_by_available_count, status, req, logging) 

        def run_test_machine_type_removed(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                "machineType": "Standard_D1_v2"
            },"availableCount":100}]} ]}
            self.assertRaises(RuntimeError, cluster_test.limit_request_by_available_count, status, req, logging)       
        
        #Test if requested count is less than equal to available count                    
        run_test(1, 1)
        run_test(99, 99)
        run_test(100, 100)
        #Test if requested count is more than available count
        run_test(101, 100)  
        #Test runtime errors
        run_test_zero_available(10)
        run_test_nodearray_removed(10)
        run_test_machine_type_removed(10)
        #Test if active count fix is disabled
        run_test(101, 101, True)  
        
class TestAllocationStrategy(unittest.TestCase):
    def test_new_allocation_strategy(self):
        logger = logging.getLogger("test")
        
        # Test capacity based distribution and no remaining slots
        vm_dist = {"A":9, "B":8}
        expected_node_list = []
        for vm, c in vm_dist.items():
            expected_node_list.extend(set_node_list(vm, c, 1))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 9, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 8, False],
            ], expected_new_nodes_list=expected_node_list) 
        
        result = cluster.allocation_strategy(mymock, logger, "whatever", 17, 500, {"A": 1, "B": 1}, vm_dist)
        self.assertEqual(result.nodes, expected_node_list)
        
        # Test Empty list of nodes
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 9, False],
            [{"weight": 1, "template_id": "whatever", "capacity-failure-backoff": 500}, 17, False]], expected_new_nodes_list=[]) 
        
        result = cluster.allocation_strategy(mymock, logger, "whatever", 17, 500, {"A": 1, "B": 1}, vm_dist)
        self.assertEqual(result, None)
        
        # Test weighted distribution and remaining slots
        vm_dist = {"A":17, "B":0, "C": 7}
        expected_node_list = []
        for vm, c in vm_dist.items():
            expected_node_list.extend(set_node_list(vm, c, 1))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 17, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 7, False],
            [{"weight": 1, "template_id": "whatever", "capacity-failure-backoff": 500}, 11, False]],  expected_new_nodes_list=expected_node_list) 
        result = cluster.allocation_strategy(mymock, logger, "whatever", 35, 500, {"A": 1, "B": 1, "C": 1}, vm_dist)
        expected_node_list.extend(set_node_list("A", 11, 1))
        self.assertEqual(result.nodes, expected_node_list)
        
    def testCalculateDistCapacity(self):
        vm_size = {"A": 16, "B": 8}
        vm_dist = cluster.calculate_vm_dist_capacity(vm_size, 24)
        self.assertEqual(vm_dist, {"A": 12, "B": 8})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = cluster.calculate_vm_dist_capacity(vm_size, 50)
        self.assertEqual(vm_dist, {"A": 17, "B": 2, "C": 10})  
        
    def testCalculateDistWeights(self):
        vm_size = {"A": 16, "B": 8}
        vm_dist = cluster.calculate_vm_dist_weighted(vm_size, 24)
        self.assertEqual(vm_dist, {"A": 12, "B": 4})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = cluster.calculate_vm_dist_weighted(vm_size, 50)
        self.assertEqual(vm_dist, {"A": 17, "B": 0, "C": 7})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = cluster.calculate_vm_dist_weighted(vm_size, 100)
        self.assertEqual(vm_dist, {"A": 34, "B": 10, "C": 13})
        
        
if __name__ == "__main__":
    unittest.main()