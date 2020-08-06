import json

import logging
import requests
from urllib import urlencode

class MachineStates:
    building = "building"
    active = "active"
    error = "error"
    deleting = "deleting"
    deleted = "deleted"
    
    
class MachineResults:
    succeed = "succeed"
    executing = "executing"
    failed = "fail"
# LSF:    failed = "failed"
    
    
class RequestStates:
    running = "running"
    complete = "complete"
    complete_with_error = "complete_with_error"


class SymphonyRestClient:

    def __init__(self, config, logger=None):
        self.config = config
        self.webserviceHostname = self.config.get('symphony.hostfactory.rest_address', '127.0.0.1')
        self.webservicePort = self.config.get('symphony.hostfactory.HF_REST_LISTEN_PORT', '9080')
        self.webserviceSsl = self.config.get('symphony.hostfactory.HF_REST_TRANSPORT', 'TCPIPv4').lower() == 'TCPIPv4SSL'.lower()
        self.username = self.config.get('symphony.soam.user', 'Admin')
        self.password = self.config.get('symphony.soam.password', 'Admin')
        self.token = None
        self.logger = logger or logging.getLogger()

    def rest_url(self):
        prefix = 'https' if self.webserviceSsl else 'http'
        return '%s://%s:%s' % (prefix, self.webserviceHostname, self.webservicePort)

    def _raise_on_error(self, r):
        self.logger.info("Symphony REST API response (%s): %s", r.status_code, r)
        if 400 <= r.status_code < 500:
            if r.text:
                raise Exception("Invalid Symphony REST call (%s)" % r.text)
            else:
                raise Exception("Unspecified Symphony REST Error (%s)" % r.status_code)

        r.raise_for_status()        
    
    def _login(self):
        url = self.rest_url() + '/platform/rest/hostfactory/auth/login'
        r = requests.get(url, auth=(self.username, self.password))
        self._raise_on_error(r)
        
        hfcsrftokenBody = r.json()
        self.token = hfcsrftokenBody['hfcsrftoken']
        return self.token

    def update_hostfactory_templates(self, templates):
        hfcsrftoken = self._login()
        params = {'hfcsrftoken': hfcsrftoken}
        url = self.rest_url() + '/platform/rest/hostfactory/provider/azurecc/templates'

        r = requests.put(url, auth=(self.username, self.password), params=params, json=templates)
        self._raise_on_error(r)



