# IBM Spectrum Symphony #

This project installs and configures IBM Spectrum Symphony.

Use of IBM Spectrum Symphony requires a license agreement and Symphony binaries obtained directly 
from [IBM Spectrum Analytics](https://www.ibm.com/us-en/marketplace/analytics-workload-management).

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


This sample requires the following:

  1. A license to use IBM Spectrum Symphony from [IBM Spectrum Analytics](https://www.ibm.com/us-en/marketplace/analytics-workload-management).  If you don't already have a license you can "Start a Free Trial" to get one.
     
  1. CycleCloud must be installed and running.

     a. If this is not the case, see the [CycleCloud QuickStart Guide](https://docs.microsoft.com/en-us/azure/cyclecloud/quickstart-install-cyclecloud) for
        assistance.

  1. The [CycleCloud CLI](https://docs.microsoft.com/en-us/azure/cyclecloud/install-cyclecloud-cli) must be installed and configured for use.  You can configure CycleCloud CLI for the first time with 
      ```bash
      cyclecloud initialize
      ```

  1. You must have access to log in to CycleCloud.

  1. You must have access to upload data and launch instances in your chosen
     Cloud Provider account.

  1. You must have access to a configured CycleCloud "Locker" for Project Storage
     (Cluster-Init and Chef).

  1. Optional: To use the `cyclecloud project upload <locker>` command, you must
     have a Pogo configuration file set up with write-access to your locker.

     a. The "Upload the Project" section of [this tutorial](https://docs.microsoft.com/en-us/azure/cyclecloud/tutorials/deploy-custom-application#upload-the-project) provides steps to edit your Pogo configuration file
     
     b. You may use your preferred tool to interact with your storage "Locker"
        instead.


## Configuring the Project ##


The first step is to configure the project for use with your storage locker:

  1. Open a terminal session with the CycleCloud CLI enabled.
  
  1. Clone this repo into a new directory

  1. Change directory to the cloned repo

  1. Download the IBM Spectrum Symphony installation binaries from [IBM](https://www.ibm.com/us-en/marketplace/analytics-workload-management) and place them in the `./blobs/symphony` directory.
      * `symeval-7.2.1.0_x86_64.bin`
      * `symeval-7.2.1.0.exe`
      * `sym_adv_ev_entitlement.dat`
  
  1. If the version number is not 7.2.1, update the version numbers in [`project.ini`](project.ini) and [`templates/symphony.txt`](templates/symphony.txt) 

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


