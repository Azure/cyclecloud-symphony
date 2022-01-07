import json

import logging
import requests
from shutil import which
from urllib.parse import urlencode

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
        self.logger = logger or logging.getLogger()
        self.webserviceUrl = self.rest_url()
        self.username = self.config.get('symphony.soam.user', 'Admin')
        self.password = self.config.get('symphony.soam.password', 'Admin')
        self.token = None

    def rest_url(self):
        # It's possible to the url from ego (supports manual cluster config changes)
        #     egosh client view REST_HOST_FACTORY_URL | grep DESCRIPTION | sed 's/^DESCRIPTION\:\s//g' -
        # But HostFactory does not have the correct environment for egosh
        # Instead, generate the url from cluster config
        webserviceHostname = self.config.get('symphony.hostfactory.rest_address', '127.0.0.1')
        webservicePort = self.config.get('HF_REST_LISTEN_PORT', self.config.get('symphony.hostfactory.HF_REST_LISTEN_PORT', '9080'))
        webserviceSsl = self.config.get('symphony.hostfactory.HF_REST_TRANSPORT', 'TCPIPv4').lower() == 'TCPIPv4SSL'.lower()
        prefix = 'https' if webserviceSsl else 'http'
        url = '%s://%s:%s/platform/rest/hostfactory' % (prefix, webserviceHostname, webservicePort)

        self.logger.info(f"Using HF URL: {url.rstrip('/')}")
        return url.rstrip('/')

    def _raise_on_error(self, r):
        self.logger.info("Symphony REST API [%s] response (%s)", r.url, r.status_code)
        if 400 <= r.status_code < 500:
            if r.text:
                raise Exception("Invalid Symphony REST call (%s): %s" % (r.status_code, r.text))
            else:
                raise Exception("Unspecified Symphony REST Error (%s)" % r.status_code)

        r.raise_for_status()        
    
    def _login(self):
        url = self.webserviceUrl + '/auth/login'
        r = requests.get(url, auth=(self.username, self.password))
        self._raise_on_error(r)
        
        hfcsrftokenBody = r.json()
        self.token = hfcsrftokenBody['hfcsrftoken']
        return self.token

    def update_hostfactory_templates(self, templates):
        hfcsrftoken = self._login()
        params = {'hfcsrftoken': hfcsrftoken}
        url = self.webserviceUrl + '/provider/azurecc/templates'
        r = requests.put(url, auth=(self.username, self.password), params=params, json=templates)
        self._raise_on_error(r)
