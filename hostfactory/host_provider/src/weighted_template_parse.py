import os
import json
from collections import OrderedDict
import math
import unittest
import cluster
import logging
from unittest.mock import MagicMock, patch
import string

class WeightedTemplates():
    
    def __init__(self, cluster_name, provider_config, logger=None):        
            cluster_name = provider_config.get("cyclecloud.cluster.name")
            self.cluster=cluster.Cluster(cluster_name, provider_config, logger)
            self.logger = logger or logging.getLogger()

    def create_machines(self, input_json, azurecc_template):
        symphony_templates = azurecc_template
        result = []
        for template in symphony_templates:
            if template["templateId"] == input_json["template"]["templateId"]:
                nodearray_name = template["attributes"]["nodearray"][1]
                vm_types_weight = template["vmTypes"]
                req_count = input_json["template"]["machineCount"]
                vm_priority_dict = template["vmTypePriority"]
                maxNumber = template["maxNumber"]
                if vm_priority_dict is None or vm_priority_dict == {}:
                    vm_types = template["vmTypes"]
                else:
                    vm_types = dict(sorted(vm_priority_dict.items(), key=lambda item: item[1], reverse=True))
                print(vm_types)
                for vm_type in vm_types:
                    avail_count = self.cluster.get_avail_count(vm_type, nodearray_name)
                    print("avail_count: " + str(avail_count)) 
                    vm_type_weight = vm_types_weight[vm_type]    
                    print("vm type weight: " + str(vm_type_weight))
                    maxNumberWeight = math.floor(maxNumber/vm_type_weight) 
                    print ("maxNumber: " + str(maxNumberWeight)) 
                    req_count_weight = math.ceil(req_count/vm_type_weight)   
                    req_machines = min(req_count_weight, avail_count, maxNumberWeight)
                    if req_machines <= 0:
                        print("Reached maxNumber or no available machines")
                        continue
                    result.append((vm_type, req_machines))
                    print("Create vmType: " + vm_type + " with count: " + str(req_machines))
                    req_count = req_count - avail_count * vm_type_weight
                    maxNumber = maxNumber - avail_count * vm_type_weight
        return result

def azurecc_template_generate(vmTypes, vmTypePriority, maxNumber):
    azurecc_template = [{
      "templateId":   "execute",     
      "attributes" :   {
                "type": ["String", "X86_64"],
               "nram": ["Numeric", "4096"],
                "ncpus":    ["Numeric", 1],
                "nodearray":    ["String", "execute"]
                
            },
       "vmTypes": {" Standard_D2_v2 ":2, " Standard_D1_v2 ":1},
       "vmTypePriority": {" Standard_D2_v2 ":1000, " Standard_D1_v2 ":100},
       "priceInfo":    ["String", "price:0.1,billingTimeUnitType:prorated_hour,billingTimeUnitNumber:1,billingRoundoffType:unit"],
       "rank": ["Numeric", "0"],
       "maxNumber":    100
       }]
    azurecc_template[0]["vmTypes"] = vmTypes
    azurecc_template[0]["vmTypePriority"] = vmTypePriority 
    azurecc_template[0]["maxNumber"] = maxNumber
    return azurecc_template
