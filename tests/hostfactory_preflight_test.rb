require 'minitest/autorun'
require 'tmpdir'
require 'fileutils'
require 'open3'
require 'shellwords'

class HostFactoryPreflightTest < Minitest::Test
  PREFLIGHT = File.expand_path('../hostfactory/preflight.sh', __dir__)
  INSTALLER = File.expand_path('../hostfactory/install.sh', __dir__)

  def setup
    @directory = Dir.mktmpdir('hostfactory preflight ')
    @bin = File.join(@directory, 'bin')
    FileUtils.mkdir_p(@bin)
    @environment = { 'PATH' => @bin, 'EGO_TOP' => @directory }
    write_command('python3')
    write_command('jetpack', 'echo cyclecloud-symphony-pkg-3.1.5.zip')
    write_command('jq')
    write_command('egosh', '[ "$1" = -V ] || exit 2')
    write_command('symping', '[ "$1" = -V ] || exit 2')
    File.write(File.join(@directory, 'profile.platform'), "export PATH=#{Shellwords.escape(@bin)}\n")
  end

  def teardown
    FileUtils.remove_entry(@directory)
  end

  def write_command(name, body = 'exit 0')
    path = File.join(@bin, name)
    File.write(path, "#!/bin/bash\n#{body}\n")
    File.chmod(0755, path)
  end

  def prerequisites(mode)
    Open3.capture3(
      @environment, '/bin/bash', '-c',
      '. "$1"; Validate-HostFactory-Prerequisites "$2"', '--', PREFLIGHT, mode
    )
  end

  def validate_environment
    Open3.capture3(
      @environment, '/bin/bash', '-c',
      '. "$1"; Validate-Symphony-Environment', '--', PREFLIGHT
    )
  end

  def test_install_only_does_not_require_jq_or_symphony
    FileUtils.rm(File.join(@bin, 'jq'))
    FileUtils.rm(File.join(@directory, 'profile.platform'))
    _, stderr, status = prerequisites('install')
    assert status.success?, stderr
  end

  def test_generate_config_requires_jq
    FileUtils.rm(File.join(@bin, 'jq'))
    _, stderr, status = prerequisites('generate_config')
    refute status.success?
    assert_includes stderr, 'requires jq'
  end

  def test_missing_jetpack_is_reported
    FileUtils.rm(File.join(@bin, 'jetpack'))
    _, stderr, status = prerequisites('install')
    refute status.success?
    assert_includes stderr, 'jetpack must be executable'
  end

  def test_pip_can_bootstrap_missing_virtualenv
    write_command('python3', '[ "$2" = pip ]')
    _, stderr, status = prerequisites('install')
    assert status.success?, stderr
  end

  def test_missing_virtualenv_and_pip_is_reported
    write_command('python3', 'exit 1')
    _, stderr, status = prerequisites('install')
    refute status.success?
    assert_includes stderr, 'python3-pip and python3-virtualenv'
  end

  def test_valid_environment_uses_version_only_probes
    stdout, stderr, status = validate_environment
    assert status.success?, stderr
    assert_includes stdout, 'EGO and SOAM environment validated'
  end

  def test_missing_profile_is_reported
    FileUtils.rm(File.join(@directory, 'profile.platform'))
    _, stderr, status = validate_environment
    refute status.success?
    assert_includes stderr, 'Cannot read Symphony profile'
  end

  def test_soam_loader_failure_is_reported
    write_command('symping', 'echo "error while loading shared libraries: libsoamapi.so" >&2; exit 127')
    _, stderr, status = validate_environment
    refute status.success?
    assert_includes stderr, 'libsoamapi.so'
    assert_includes stderr, 'symping -V failed'
  end

  def test_generate_config_stops_before_overwriting_configuration
    FileUtils.rm(File.join(@bin, 'symping'))
    assert_configuration_preserved('symping is not executable')
  end

  def test_jetpack_access_failure_preserves_configuration
    write_command('jetpack', 'echo "Jetpack access denied" >&2; exit 1')
    assert_configuration_preserved('Cannot read Jetpack configuration')
  end

  def test_empty_jetpack_setting_preserves_configuration
    write_command('jetpack', 'exit 0')
    assert_configuration_preserved('symphony.pkg_plugin must not be empty')
  end

  def assert_configuration_preserved(expected_error)
    hf_top = File.join(@directory, 'hostfactory')
    conf_dir = File.join(hf_top, 'conf', 'providers')
    FileUtils.mkdir_p(conf_dir)
    config = File.join(conf_dir, 'hostProviders.json')
    File.write(config, 'existing configuration')
    environment = @environment.merge(
      'PATH' => "#{@bin}:/usr/bin:/bin",
      'HF_TOP' => hf_top,
      'HF_CONFDIR' => File.join(hf_top, 'conf'),
      'HF_WORKDIR' => File.join(hf_top, 'work'),
      'HF_LOGDIR' => File.join(hf_top, 'log'),
      'HF_VERSION' => '1.1'
    )
    _, stderr, status = Open3.capture3(
      environment, '/bin/bash', INSTALLER, 'generate_config',
      '--cluster', 'test', '--username', 'test', '--password', 'test',
      '--web_server', 'https://example.invalid', chdir: @directory
    )
    refute status.success?
    assert_includes stderr, expected_error
    assert_equal 'existing configuration', File.read(config)
    refute File.exist?(File.join(hf_top, '1.1', 'providerplugins'))
  end
end
