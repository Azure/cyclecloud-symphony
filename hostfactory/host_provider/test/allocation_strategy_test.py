import unittest
import allocation_strategy
import logging

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
    
class MockNode:
    
    def __init__(self, node_name, weight):
       self.name = node_name
       self.resources = {"weight": weight}
    
def set_node_list(node_name, node_count, weight=1):
    # concatenate node_name with a number to create a list of nodes
    return([MockNode(node_name + str(i), weight) for i in range(node_count)])


class TestAllocationStrategy(unittest.TestCase):


    def test_allocate_slots(self):
        logger = logging.getLogger("test")


        # Monkey patch the filter_available_vmTypes method to simply return all vmTypes
        def filter_available_vmTypes(_self, y):
            return y
        
        allocation_strategy.AllocationStrategy.filter_available_vmTypes = filter_available_vmTypes
        
        vm_dist = {"A":17}
        expected_node_list = []
        for vm, c in vm_dist.items():
            expected_node_list.extend(set_node_list(vm, c, 1))
        mymock = MockNodeMgr([
            [{"weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 17, False]
            ], expected_new_nodes_list=expected_node_list) 

        # Price based allocation (left-to-right)
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="price", 
                                                                      capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy.allocate_slots(17, "some_template_id", {"A": 1, "B": 1})
        self.assertEqual(result.nodes, expected_node_list)


        # Test capacity based distribution and no remaining slots
        vm_dist = {"A":9, "B":8}
        expected_node_list = []
        for vm, c in vm_dist.items():
            expected_node_list.extend(set_node_list(vm, c, 1))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 9, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 8, False],
            ], expected_new_nodes_list=expected_node_list) 
        
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="capacity", 
                                                                      capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy.allocate_slots(17, "some_template_id", {"A": 1, "B": 1})
        self.assertEqual(result.nodes, expected_node_list)        

        # Test capacity distribution 
        vm_size = {"A": 16, "B": 8, "C": 4}
        expected_node_list.extend(set_node_list('A', 48, 16))
        expected_node_list.extend(set_node_list('B', 32, 8))
        expected_node_list.extend(set_node_list('C', 32, 4))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 48, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 32, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 32, False],
            ], expected_new_nodes_list=expected_node_list) 
        
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="capacity", 
                                                                      capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy.allocate_slots(100, "some_template_id", vm_size)
        self.assertEqual(result.nodes, expected_node_list)        

        # Test weighted distribution
        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        expected_node_list.extend(set_node_list('A', 704, 16))
        expected_node_list.extend(set_node_list('B', 200, 8))
        expected_node_list.extend(set_node_list('C', 48, 48))
        expected_node_list.extend(set_node_list('D', 48, 16))
        expected_node_list.extend(set_node_list('E', 0, 8))
        expected_node_list.extend(set_node_list('F', 0, 4))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 704, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 200, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 48, False],
            [{"node.vm_size": "D", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 48, False],
            ], expected_new_nodes_list=expected_node_list) 
        
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="weighted", 
                                                                      capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy.allocate_slots(1000, "some_template_id", vm_size)
        self.assertEqual(result.nodes, expected_node_list)        


    def test_allocation_strategy(self):
        logger = logging.getLogger("test")
        
        # Test capacity based distribution and no remaining slots
        vm_dist = {"A":9, "B":8}
        expected_node_list = []
        for vm, c in vm_dist.items():
            expected_node_list.extend(set_node_list(vm, c, 1))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 9, False],
            [{"node.vm_size": "B", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 8, False],
            ], expected_new_nodes_list=expected_node_list) 
        
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="price", capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy._allocation_strategy("some_template_id", 17, {"A": 1, "B": 1}, vm_dist)
        self.assertEqual(result.nodes, expected_node_list)
        
        # Test Empty list of nodes
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 9, False],
            [{"weight": 1, "template_id": "some_template_id", "capacity-failure-backoff": 500}, 17, False]], expected_new_nodes_list=[]) 
        
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="price", capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy._allocation_strategy("some_template_id", 17, {"A": 1, "B": 1}, vm_dist)
        self.assertEqual(result, None)
        
        # Test weighted distribution and remaining slots
        vm_dist = {"A":17, "B":0, "C": 7}
        expected_node_list = []
        for vm, c in vm_dist.items():
            expected_node_list.extend(set_node_list(vm, c, 1))
        mymock = MockNodeMgr([
            [{"node.vm_size": "A", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 17, False],
            [{"node.vm_size": "C", "weight": 1, "template_id": "some_template_id", 'capacity-failure-backoff': 500}, 7, False],
            [{"weight": 1, "template_id": "some_template_id", "capacity-failure-backoff": 500}, 11, False]],  
            expected_new_nodes_list=expected_node_list)
        expected_node_list.extend(set_node_list("A", 11, 1))
        autoscaling_strategy = allocation_strategy.AllocationStrategy(mymock, {}, strategy="price", capacity_limit_timeout=500, logger=logger)
        result = autoscaling_strategy._allocation_strategy("some_template_id", 35, {"A": 1, "B": 1, "C": 1}, vm_dist)
        self.assertEqual(result.nodes, expected_node_list)
        
    def test_CalculateDistCapacity(self):
        vm_size = {"A": 16, "B": 8}
        vm_dist = allocation_strategy.calculate_vm_dist_capacity(vm_size, 24)
        self.assertEqual(vm_dist, {"A": 16, "B": 8})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_capacity(vm_size, 50)
        self.assertEqual(vm_dist, {"A": 32, "B": 16, "C": 16})  

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_capacity(vm_size, 100)
        self.assertEqual(vm_dist, {'A': 32, 'B': 24, 'C': 0, 'D': 16, 'E': 16, 'F': 16})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_capacity(vm_size, 1000)                
        self.assertEqual(vm_dist, {'A': 176, 'B': 168, 'C': 192, 'D': 160, 'E': 160, 'F': 164})

        
    def test_CalculateDistWeights(self):
        # default distribution is [.7, .2, .05, .05]
        vm_size = {"A": 16, "B": 8}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 24)
        self.assertEqual(vm_dist, {"A": 16, "B": 8})

        vm_size = {"A": 16, "B": 8}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 40)
        self.assertEqual(vm_dist, {"A": 32, "B": 8})

        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 50)
        self.assertEqual(vm_dist, {"A": 48, "B": 8, "C": 4})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 74)
        self.assertEqual(vm_dist, {"A": 64, "B": 8, "C": 4})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 100)
        self.assertEqual(vm_dist, {"A": 80, "B": 16, "C": 4})
        
        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 100)
        self.assertEqual(vm_dist, {'A': 64, 'B': 16, 'C': 48, 'D': 0, 'E': 0, 'F': 0}) # We err on the side of allocating if node has a percent

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 256)
        self.assertEqual(vm_dist, {'A': 176, 'B': 48, 'C': 48, 'D': 0, 'E': 0, 'F': 0})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 512)
        self.assertEqual(vm_dist, {'A': 352, 'B': 96, 'C': 48, 'D': 16, 'E': 0, 'F': 0})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_weighted(vm_size, 1000)
        self.assertEqual(vm_dist, {'A': 704, 'B': 200, 'C': 48, 'D': 48, 'E': 0, 'F': 0})


    def test_CalculateDistDecay(self):
        vm_size = {"A": 16, "B": 8}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 24)
        self.assertEqual(vm_dist, {"A": 16, "B": 8})

        vm_size = {"A": 16, "B": 8}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 40)
        self.assertEqual(vm_dist, {"A": 32, "B": 8})

        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 50)
        self.assertEqual(vm_dist, {"A": 48, "B": 8, "C": 0})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 74)
        self.assertEqual(vm_dist, {"A": 48, "B": 24, "C": 4})
        
        vm_size = {"A": 16, "B": 8, "C": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 100)
        self.assertEqual(vm_dist, {"A": 64, "B": 24, "C": 16})
        
        vm_size = {"A": 16, "B": 8, "C": 48}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 100)
        self.assertEqual(vm_dist, {"A": 96, "B": 8, "C": 0}) # We never get allocate a big C node here
        
        vm_size = {"A": 16, "B": 8, "C": 48}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 200)
        self.assertEqual(vm_dist, {"A": 144, "B": 56, "C": 0})

        vm_size = {"A": 16, "B": 8, "C": 48}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 256)
        self.assertEqual(vm_dist, {"A": 144, "B": 72, "C": 48})

        vm_size = {"A": 16, "B": 8, "C": 48}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 1000)
        self.assertEqual(vm_dist, {"A": 576, "B": 280, "C": 144})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 100)
        self.assertEqual(vm_dist, {'A': 96, 'B': 8, 'C': 0, 'D': 0, 'E': 0, 'F': 0})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 256)
        self.assertEqual(vm_dist, {'A': 256, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 512)
        self.assertEqual(vm_dist, {'A': 288, 'B': 144, 'C': 48, 'D': 32, 'E': 0, 'F': 0})

        vm_size = {"A": 16, "B": 8, "C": 48, "D": 16, "E": 8, "F": 4}
        vm_dist = allocation_strategy.calculate_vm_dist_decay(vm_size, 1000)
        self.assertEqual(vm_dist, {'A': 576, 'B': 160, 'C': 96, 'D': 64, 'E': 56, 'F': 48})


if __name__ == "__main__":
    unittest.main()
