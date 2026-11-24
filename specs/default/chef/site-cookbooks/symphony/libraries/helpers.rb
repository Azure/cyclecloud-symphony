# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
module Symphony
  class Helpers

    def self.force_ego_binary_type(profile_path)
      return if ::File.read(profile_path).include?('Forcing EGO binary type')

      file = Chef::Util::FileEdit.new(profile_path)
      file.insert_line_after_match(/.*"Cannot get binary type.*/, '     export EGO_BINARY_TYPE="linux-x86_64"')
      file.insert_line_after_match(/export EGO_BINARY_TYPE="linux-x86_64"/, '     echo "Forcing EGO binary type: $EGO_BINARY_TYPE"')
      file.write_file
    end

    def self.wait_for_master(sleep_time=10, max_retries=6, &block)
      results = block.call
      retries = 0
      while results.length < 1 and retries < max_retries
        sleep sleep_time
        retries += 1
        results = block.call
        Chef::Log.info "Found symphony master node."
      end
      if retries >= max_retries
        raise Exception, "Timed out waiting for Symphony Master"
      end

      results
    end

  end
end
