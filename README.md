# IBM Spectrum Symphony #

This project installs and configures IBM Spectrum Symphony.

Use of IBM Spectrum Symphony requires a license agreement and Symphony binaries obtained directly 
from [IBM Spectrum Analytics](https://www.ibm.com/us-en/marketplace/analytics-workload-management).


NOTE:
Currently, this project only supports Linux-only Symphony clusters.  Windows workers are not yet supported.

<!-- markdown-toc start - Don't edit this section. Run M-x markdown-toc-generate-toc again -->

**Table of Contents**

- [IBM Spectrum Symphony](#ibm-spectrum-symphony)
    - [Pre-Requisites](#pre-requisites)
    - [Configuring the Project](#configuring-the-project)
    - [Deploying the Project](#deploying-the-project)
    - [Importing the Cluster Template](#importing-the-cluster-template)
    - [Using the Project Specs in Other Clusters](#using-the-project-specs-in-other-clusters)

<!-- markdown-toc end -->


## Pre-Requisites ##

This project requires running Azure CycleCloud version 7.7.1 and Symphony 7.2.0 or later.

This project requires the following:

  1. A license to use IBM Spectrum Symphony from [IBM Spectrum Analytics](https://www.ibm.com/us-en/marketplace/analytics-workload-management).  
  
  2. The IBM Spectrum Symphony installation binaries.
  
     a. Download the binaries from [IBM](https://www.ibm.com/us-en/marketplace/analytics-workload-management) and place them in the `./blobs/symphony/` directory.
     
     b. If the version is not 7.3.0.0 (the project default), then update the version number in the Files list
        in `./project.ini` and in the cluster template: `./templates/symphony.txt`
     
  3. CycleCloud must be installed and running.

     a. If this is not the case, see the [CycleCloud QuickStart Guide](https://docs.microsoft.com/en-us/azure/cyclecloud/quickstart-install-cyclecloud) for
        assistance.

  4. The [CycleCloud CLI](https://docs.microsoft.com/en-us/azure/cyclecloud/install-cyclecloud-cli) must be installed and configured for use.
  
     a. If this is not the case, see the [CycleCloud CLI Install Guide](https://docs.microsoft.com/en-us/azure/cyclecloud/install-cyclecloud-cli) for
        assistance.


## Configuring the Project ##


The first step is to configure the project for use with your storage locker:

  1. Open a terminal or Azure Cloud Shell session with the CycleCloud CLI enabled.
  
  1. Clone this repo into a new directory and change to the new directory:

``` bash

   $ git clone https://github.com/Azure/cyclecloud-symphony.git
   $ cd ./cyclecloud-symphony
   
```
  3. Download the IBM Spectrum Symphony installation binaries and license entitlement file from [IBM](https://www.ibm.com/us-en/marketplace/analytics-workload-management) and place them in the `./blobs/symphony` directory.
    * ./blobs/symphony/sym-7.3.0.0.exe
    * ./blobs/symphony/sym-7.3.0.0_x86_64.bin
    * ./blobs/symphony/sym_adv_entitlement.dat
    
      Or, if using an eval edition:
      
    * ./blobs/symphony/sym_adv_ev_entitlement.dat
    * ./blobs/symphony/symeval-7.3.0.0_x86_64.bin
    * ./blobs/symphony/symeval-7.3.0.0.exe
    
  4. If the version number is not 7.3.0.0, update the version numbers in [`project.ini`](project.ini) and [`templates/symphony.txt`](templates/symphony.txt) 


## Deploying the Project ##


To upload the project (including any local changes) to your target locker, run the
`cyclecloud project upload` command from the project directory.  The expected output looks like
this:

``` bash

   $ cyclecloud project upload my_locker
   Sync completed!

```


**IMPORTANT**

For the upload to succeed, you must have a valid Pogo configuration for your target Locker.


## Importing the Cluster Template ##


To import the cluster:

 1. Open a terminal session with the CycleCloud CLI enabled.

 2. Switch to the Symphony directory.

 3. Run ``cyclecloud import_template symphony -f templates/symphony.txt``.
    The expected output looks like this:
    
    ``` bash
    
    $ cyclecloud import_template symphony -f templates/symphony.txt
    Importing template symphony....
    ----------------
    symphony : *template*
    ----------------
    Keypair: $Keypair
    Cluster nodes:
        master: off
    Total nodes: 1
    ```


## Host Factory Provider for Azure CycleCloud

This project extends the Symphony Host Factory with an Azure CycleCloud resource provider: azurecc.

The Host Factory will be configured as the default autoscaler for the cluster.

### Installing the azurecc HostFactory

It is also possible to configure an existing Symphony installation to use the `azurecc` HostFactory to 
burst into Azure.

Please contact azure support for help with this configuration.



# Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
