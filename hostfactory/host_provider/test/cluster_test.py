import unittest
import cluster
import logging
from unittest.mock import MagicMock
from unittest.mock import patch

class MockNodeMgr:
    
    def __init__(self, expect=[], expect_new_nodes=0):
        self.expect = expect
        self.expected_node_count = expect_new_nodes 
        # self.expected_new_nodes_list = expect_new_nodes_list
    
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
        
    def expect(self, *args):
        self.expect.append(args)
    
    def expect_new_nodes(self, count):
        self.expected_node_count = count
        
    # def expect_new_nodes_list(self, nodenames):
    #     self.expected_new__list = nodenames
        
    def get_new_nodes(self):        
        return [MockNode(1) for i in range(self.expected_node_count)]
   
class MockNode:
    def __init__(self, weight):
       #self.sku = sku
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
        
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 9, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 8, False]
            ], expect_new_nodes=17) 
        c = cluster.allocation_strategy(mymock, "whatever", 17, 500, {"A": 1, "B": 1})
        self.assertEqual(c, 17, f"Expected 17 got {c}")
        
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 12, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 12, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 11, False]
            ],  expect_new_nodes=35) 
        c = cluster.allocation_strategy(mymock, "whatever", 35, 500, {"A": 1, "B": 1, "C": 1})
        self.assertEqual(c, 35, f"Expected 35 got {c}")
        
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 12, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 12, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 11, False]
            ], expect_new_nodes=35) 
        c = cluster.allocation_strategy(mymock, "whatever", 35, 500, {"A": 2, "B": 2, "C": 1})
        self.assertEqual(c, 35, f"Expected 35 got {c}")
        
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 10, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 10, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 10, False]
            ], expect_new_nodes=30) 
        c = cluster.allocation_strategy(mymock, "whatever", 30, 500, {"A": 2, "B": 2, "C": 1})
        self.assertEqual(c, 30, f"Expected 30 got {c}")
        
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 1, False],
            ], expect_new_nodes=1) 
        c = cluster.allocation_strategy(mymock, "whatever", 1, 500, {"A": 1, "B": 1, "C": 1})
        self.assertEqual(c, 1, f"Expected 1 got {c}")
        # Need to change to take it account cores
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 34, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 33, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "whatever", 'capacity-failure-backoff': 500}, 33, False]
            ], expect_new_nodes=100) 
        c = cluster.allocation_strategy(mymock, "whatever", 100, 500, {"A": 32, "B": 16, "C": 8})
        self.assertEqual(c, 100, f"Expected 100 got {c}")
        
        
        
        
if __name__ == "__main__":
    unittest.main()
    