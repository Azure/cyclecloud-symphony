name             'symphony'
description      'Installs/Configures a basic IBM Spectrum Symphony cluster'
version          '0.0.1'

depends 'jdk'
depends 'line'

chef_version '>= 11' if respond_to?(:chef_version)
