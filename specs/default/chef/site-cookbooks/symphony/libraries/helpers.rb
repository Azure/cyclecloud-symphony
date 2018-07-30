# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
module Symphony
  class Helpers

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
