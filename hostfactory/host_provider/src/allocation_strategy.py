from math import ceil, floor
from enum import Enum
import logging


class AllocationStrategies(Enum):
    PRICE = "price"
    CAPACITY = "capacity"
    DECAY = "decay"
    WEIGHTED = "weighted"


def round_down_to_nearest_multiple(target, x):
    return x * floor(target / x)

def round_up_to_nearest_multiple(target, x):
    return x * ceil(target / x)

def normalize_list(percentage_weights):
    total = sum(percentage_weights)
    if total == 0:
        raise ValueError("Total of percentage weights is 0 - no slots would be allocated")
    return [x / total for x in percentage_weights]

def calculate_vm_dist_capacity(vm_types, total_slot_count, logger=None):
    vm_dist = {}
    slots_per_vm_type = total_slot_count // len(vm_types) # balanced distribution

    remaining_slots = total_slot_count
    vm_dist = {vm: 0 for vm in vm_types.keys()}
    for n, (vm, weight) in enumerate(vm_types.items()):        
        vm_dist[vm] = round_down_to_nearest_multiple(slots_per_vm_type, weight)
        remaining_slots -= vm_dist[vm]
        if remaining_slots <= 0:
            break

    if remaining_slots > 0:
        for n, (vm, weight) in enumerate(vm_types.items()):
            vm_dist[vm] += weight
            remaining_slots -= weight
            if remaining_slots <= 0:
                break

    logger.info("New (capacity) VM SKU distribution targets: %s", vm_dist)
    return vm_dist


def calculate_vm_dist_weighted(vm_types, requested_slot_count, percentage_weights=[.7, .2, .05, .05], logger=None):
    '''Apply a simple static percentage distribution to the vm_types'''
    percentage_weights = normalize_list(percentage_weights) # Ensure that percentage weights sum to 1

    vm_dist = {vm: 0 for vm in vm_types.keys()}
    slots_per_vm_type = [floor(requested_slot_count * p) for p in percentage_weights]
    if len(slots_per_vm_type) < len(vm_types):
        for i in range(len(vm_types) - len(slots_per_vm_type)):
            slots_per_vm_type.append(0)
        
    remaining_slots = requested_slot_count
    n = 0
    for n, p in enumerate(vm_types.items()):
        vm, weight = p
        if slots_per_vm_type[n] < 1:
            continue
        if weight <= 0:
            continue
        slot_count = max(weight, round_down_to_nearest_multiple(slots_per_vm_type[n], weight))
        remaining_slots -= slot_count
        vm_dist[vm] = slot_count
        if remaining_slots <= 0:
            break

    # Fill in any remaining slots
    while remaining_slots > 0:
        for n, p in enumerate(vm_types.items()):
            vm, weight = p
            remaining_slots -= weight
            vm_dist[vm] += weight
            if remaining_slots <= 0:
                break

    logger.info("New (weighted) VM SKU distribution targets: %s", vm_dist)
    return vm_dist




def calculate_vm_dist_decay(vm_types, total_slot_count, logger=None):
    '''
    Calculate Slots by applying a decreasing distribution : 
    weighted_increment_per_sku = [ num_skus / (1 + idx)  for idx in range(num_skus) ]

    This method is more appropriate for scaling to relatively large slot counts.
    If the incremental slot count increase is small, it will be indistinguishable 
    from the price based allocation.

    vm_types: list of skus to consider for allocation
    total_slot_count: total number of slots to allocate across the vm_types under consideration
    '''
    num_skus = len(vm_types)
    vm_dist = {sku: 0 for sku in vm_types.keys()}

    remaining = total_slot_count
    max_core_count = max(vm_types.values())
    weighted_increment_per_sku = [num_skus / (1 + idx) for idx in range(num_skus)]
    while remaining > 0:
        for idx, p in enumerate(vm_types.items()):
            sku, symphony_slot_weight = p
            unrounded_increment = min(remaining, max_core_count * weighted_increment_per_sku[idx])
            increment = round_down_to_nearest_multiple(unrounded_increment, symphony_slot_weight)
            # Allow 1 instance for the last pass through the list
            if increment == 0 and remaining <= symphony_slot_weight:
                increment += symphony_slot_weight
            remaining -= int(increment)
            vm_dist[sku] += int(increment)
            if remaining <= 0:
                break

    logger.info("New (decay) VM SKU distribution targets: %s", vm_dist)
    return vm_dist



class AllocationStrategy:

    def __init__(self, node_mgr, provider_config, strategy=AllocationStrategies.PRICE, capacity_limit_timeout=300, logger=None):
        self.provider_config = provider_config
        self.logger = logger or logging.getLogger()
        if isinstance(strategy, str):
            # Convert string to enum
            strategy = strategy.upper()
            strategy = getattr(AllocationStrategies, strategy)
        self.auto_scaling_strategy = strategy
        self.capacity_limit_timeout = capacity_limit_timeout
        self.node_mgr = node_mgr

    def filter_available_vmTypes(self, vm_types):
        '''Filter out vmTypes that have no available capacity'''

        buckets_with_capacity = [b for b in self.node_mgr.get_buckets()
                                 if (not b.last_capacity_failure or int(b.last_capacity_failure) > self.capacity_limit_timeout) and b.resources.get("weight") and b.available_count]
        vm_sizes = [b.vm_size for b in buckets_with_capacity]
        filtered_vmTypes = {}
        for vm_size in vm_types:
            if vm_size in vm_sizes:
                filtered_vmTypes[vm_size] = vm_types[vm_size]
        return filtered_vmTypes

    def allocate_slots(self, requested_slot_count, template_id, vm_types):
        # capacity_limit_timeout: Time in seconds to check waiting period after last capacity failure

        logging.info("Allocating %s slots for template_id %s using strategy %s", requested_slot_count, 
                     template_id, self.auto_scaling_strategy)
        # Filter out vmTypes that have no available capacity
        filtered_vm_types = self.filter_available_vmTypes(vm_types)

        if self.auto_scaling_strategy == AllocationStrategies.CAPACITY:
            result = self.allocate_slots_capacity(requested_slot_count, template_id, filtered_vm_types)
        elif self.auto_scaling_strategy == AllocationStrategies.WEIGHTED:
            result = self.allocate_slots_weighted(requested_slot_count, template_id, filtered_vm_types)
        elif self.auto_scaling_strategy == AllocationStrategies.DECAY:
            result = self.allocate_slots_decay(requested_slot_count, template_id, filtered_vm_types)
        else: # PRICE          
            result = self.allocate_slots_price(requested_slot_count, template_id, filtered_vm_types)
            
        return result
    
    def allocate_slots_capacity(self, requested_slots, template_id, vm_types):
        result = None
        self.logger.debug("Using capacity based (aka balanced) allocation")
        # TODO: Need to calculate the new vm_dist based on the current allocations for the vm_types
        # IMPORTANT: Should be IDENTICAL to what's needed in allocate_slots_weighted
        vm_dist = calculate_vm_dist_capacity(vm_types, requested_slots, logger=self.logger)
        result = self._allocation_strategy(template_id, requested_slots, vm_types, vm_dist)
        return result

    def allocate_slots_decay(self, requested_slots, template_id, vm_types):
        result = None
        self.logger.debug("Using decay based allocation")
        vm_dist = calculate_vm_dist_decay(vm_types, requested_slots, logger=self.logger)
        result = self._allocation_strategy(template_id, requested_slots, vm_types, vm_dist)
        return result
    
    def allocate_slots_weighted(self, requested_slots, template_id, vm_types):
        result = None
        distribution = self.provider_config.get("symphony.autoscaling.percent_weights", [.7, .2, .05, .05])
        self.logger.debug("Using weighted based allocation (weights: %s)", distribution)
        # Works per allocation request
        vm_dist = calculate_vm_dist_weighted(vm_types=vm_types, requested_slot_count=requested_slots, percentage_weights=distribution, logger=self.logger)
        result = self._allocation_strategy(template_id, requested_slots, vm_types, vm_dist)
        return result
    
    def allocate_slots_price(self, requested_slots, template_id, vm_types):
        result = None
        self.logger.debug("Using price based allocation")
        # Let node_mgr choose the vm_types
        result = self.node_mgr.allocate({"weight": 1, "template_id": template_id, 
                                        "capacity-failure-backoff": self.capacity_limit_timeout},
                                        slot_count=requested_slots,
                                        allow_existing=False)
        return result.nodes or []
    
    
    def _allocation_strategy(self, template_id, slot_count, vm_sizes, vm_dist):
        allocation_results = []
        check_allocate = None
        self.logger.warning(f"Allocating {slot_count} slots for template_id {template_id} using distribution {vm_dist}")
        for n,vmsize in enumerate(vm_sizes):
            vm_slot_count = vm_dist[vmsize]
            self.logger.debug(f"Allocating {vm_slot_count} slots of {vmsize}")
            if vm_slot_count > 0:
                check_allocate = self.node_mgr.allocate({"node.vm_size": vmsize, "weight": 1, 
                                                         "template_id": template_id, 
                                                         "capacity-failure-backoff": self.capacity_limit_timeout},
                                                        slot_count=vm_slot_count, allow_existing=False)
                if not check_allocate.nodes:
                    self.logger.debug("0 new nodes allocated for %s", vmsize)
                    break
                else:
                    allocation_results.extend(check_allocate.nodes)
        allocated_count = sum([x.resources["weight"] for x in self.node_mgr.get_new_nodes()])
        remaining_count = slot_count - allocated_count
        self.logger.debug("Allocated %s remaining %s", allocated_count, remaining_count)
        # Allocate remaining slots with any available vm size
        if remaining_count > 0:
            self.logger.warning("Allocating remaining: %s slots", remaining_count)
            check_allocate = self.node_mgr.allocate({"weight": 1, 
                                                     "template_id": template_id, 
                                                     "capacity-failure-backoff": self.capacity_limit_timeout},
                                                    slot_count=remaining_count, allow_existing=False) 
            if check_allocate.nodes:
                allocation_results.extend(check_allocate.nodes)
        return allocation_results




