require 'minitest/autorun'
require 'tmpdir'
require 'fileutils'
require 'open3'
require 'shellwords'
require 'chef/util/file_edit'
require_relative '../specs/default/chef/site-cookbooks/symphony/libraries/helpers'

class SymphonyEnvironmentTest < Minitest::Test
  VALIDATOR = File.expand_path(
    '../specs/default/chef/site-cookbooks/symphony/files/default/validate_environment.sh', __dir__
  )

  def setup
    @directory = Dir.mktmpdir('symphony environment ')
    @bin = File.join(@directory, 'bin')
    FileUtils.mkdir_p(@bin)
    @profile = File.join(@directory, 'profile.sh')
    File.write(@profile, "export PATH=#{Shellwords.escape(@bin)}:/usr/bin:/bin\n")
    write_command('egosh')
    write_command('symping')
  end

  def teardown
    FileUtils.remove_entry(@directory)
  end

  def write_command(name, body = 'exit 0')
    path = File.join(@bin, name)
    File.write(path, "#!/bin/bash\n[ \"$1\" = '-V' ] || exit 2\n#{body}\n")
    File.chmod(0755, path)
  end

  def validate
    Open3.capture3('/bin/bash', VALIDATOR, @profile)
  end

  def test_valid_ego_and_soam_environment
    stdout, stderr, status = validate
    assert status.success?, stderr
    assert_includes stdout, 'EGO and SOAM environment validated'
  end

  def test_ego_only_profile_cannot_report_success
    FileUtils.rm(File.join(@bin, 'symping'))
    _, stderr, status = validate
    refute status.success?
    assert_includes stderr, 'symping'
    assert_includes stderr, 'IBM-supported'
  end

  def test_non_executable_soam_command_is_rejected
    File.chmod(0644, File.join(@bin, 'symping'))
    _, stderr, status = validate
    refute status.success?
    assert_includes stderr, 'symping'
  end

  def test_missing_ego_command_is_rejected
    FileUtils.rm(File.join(@bin, 'egosh'))
    _, stderr, status = validate
    refute status.success?
    assert_includes stderr, 'egosh'
  end

  def test_soam_loader_failure_is_reported
    write_command('symping', 'echo "error while loading shared libraries: libsoamapi.so" >&2; exit 127')
    _, stderr, status = validate
    refute status.success?
    assert_includes stderr, 'libsoamapi.so'
    assert_includes stderr, 'symping -V failed'
  end

  def test_profile_failure_is_reported
    File.write(@profile, "return 1\n")
    _, stderr, status = validate
    refute status.success?
    assert_includes stderr, 'Could not load Symphony profile'
  end

  def test_missing_profile_is_reported
    FileUtils.rm(@profile)
    _, stderr, status = validate
    refute status.success?
    assert_includes stderr, 'Cannot read Symphony profile'
  end

  def test_ego_fallback_matches_warning_and_is_idempotent
    File.write(@profile, <<~PROFILE)
      export EGO_BINARY_TYPE=fail
      if [ "$EGO_BINARY_TYPE" = fail ]; then
          echo "Cannot get binary type"
      fi
    PROFILE
    Symphony::Helpers.force_ego_binary_type(@profile)
    patched = File.read(@profile)
    Symphony::Helpers.force_ego_binary_type(@profile)
    assert_equal patched, File.read(@profile)
    stdout, stderr, status = Open3.capture3(
      '/bin/bash', '-c', '. "$1"; test "$EGO_BINARY_TYPE" = linux-x86_64', '--', @profile
    )
    assert status.success?, "#{stdout}\n#{stderr}"
    assert_includes stdout, 'Forcing EGO binary type: linux-x86_64'
  end
end
