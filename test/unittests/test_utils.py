# Copyright (C) 2014 Kristoffer Gronlund <kgronlund@suse.com>
# See COPYING for license information.
#
# unit tests for utils.py

import os
import re
import imp
try:
    from unittest import mock
except ImportError:
    import mock
import unittest
from itertools import chain
from crmsh import utils
from crmsh import config
from crmsh import tmpfiles

def setup_function():
    utils._ip_for_cloud = None
    # Mock memoize method and reload the module under test later with imp
    mock.patch('crmsh.utils.memoize', lambda x: x).start()
    imp.reload(utils)


@mock.patch("crmsh.utils.get_stdout")
def test_package_is_installed_local(mock_run):
    mock_run.return_value = (0, None)
    res = utils.package_is_installed("crmsh")
    assert res is True
    mock_run.assert_called_once_with("rpm -q --quiet crmsh")


@mock.patch("crmsh.utils.run_cmd_on_remote")
def test_package_is_installed_remote(mock_run_remote):
    mock_run_remote.return_value = (0, None, None)
    res = utils.package_is_installed("crmsh", "other_node")
    assert res is True
    mock_run_remote.assert_called_once_with(
            "rpm -q --quiet crmsh",
            "other_node",
            "Check whether crmsh is installed on other_node")


@mock.patch("crmsh.utils.parallax_helper.parallax_call")
@mock.patch("crmsh.utils.check_ssh_passwd_need")
def test_run_cmd_on_remote(mock_check_ssh_pw, mock_parallax_call):
    mock_check_ssh_pw.return_value = False
    mock_parallax_call.side_effect = ValueError("Exited with error code 2, Error output: cmd error message")

    rc, out, err = utils.run_cmd_on_remote("cmd", "other_node")
    assert rc == 2
    assert out is None
    assert err == "cmd error message"

    mock_check_ssh_pw.assert_called_once_with("other_node")
    mock_parallax_call.assert_called_once_with(["other_node"], "cmd", False)


@mock.patch('os.path.exists')
def test_check_file_content_included_target_not_exist(mock_exists):
    mock_exists.side_effect = [True, False]
    res = utils.check_file_content_included("file1", "file2")
    assert res is False
    mock_exists.assert_has_calls([mock.call("file1"), mock.call("file2")])


@mock.patch("__builtin__.open")
@mock.patch('os.path.exists')
def test_check_file_content_included(mock_exists, mock_open_file):
    mock_exists.side_effect = [True, True]
    mock_open_file.side_effect = [
            mock.mock_open(read_data="data1").return_value,
            mock.mock_open(read_data="data2").return_value
        ]

    res = utils.check_file_content_included("file1", "file2")
    assert res is False

    mock_exists.assert_has_calls([mock.call("file1"), mock.call("file2")])
    mock_open_file.assert_has_calls([mock.call("file2", 'r'), mock.call("file1", 'r')])


@mock.patch('crmsh.utils.get_stdout_stderr')
def test_check_ssh_passwd_need(mock_run):
    mock_run.return_value = (1, None, None)
    res = utils.check_ssh_passwd_need("node1")
    assert res is True
    mock_run.assert_called_once_with("ssh -o StrictHostKeyChecking=no -o EscapeChar=none -o ConnectTimeout=15 -T -o Batchmode=yes node1 true")


def test_systeminfo():
    assert utils.getuser() is not None
    assert utils.gethomedir() is not None
    assert utils.get_tempdir() is not None


def test_shadowcib():
    assert utils.get_cib_in_use() == ""
    utils.set_cib_in_use("foo")
    assert utils.get_cib_in_use() == "foo"
    utils.clear_cib_in_use()
    assert utils.get_cib_in_use() == ""


def test_booleans():
    truthy = ['yes', 'Yes', 'True', 'true', 'TRUE',
              'YES', 'on', 'On', 'ON']
    falsy = ['no', 'false', 'off', 'OFF', 'FALSE', 'nO']
    not_truthy = ['', 'not', 'ONN', 'TRUETH', 'yess']
    for case in chain(truthy, falsy):
        assert utils.verify_boolean(case) is True
    for case in truthy:
        assert utils.is_boolean_true(case) is True
        assert utils.is_boolean_false(case) is False
        assert utils.get_boolean(case) is True
    for case in falsy:
        assert utils.is_boolean_true(case) is False
        assert utils.is_boolean_false(case) is True
        assert utils.get_boolean(case, dflt=True) is False
    for case in not_truthy:
        assert utils.verify_boolean(case) is False
        assert utils.is_boolean_true(case) is False
        assert utils.is_boolean_false(case) is False
        assert utils.get_boolean(case) is False


def test_olist():
    lst = utils.olist(['B', 'C', 'A'])
    lst.append('f')
    lst.append('aA')
    lst.append('_')
    assert 'aa' in lst
    assert 'a' in lst
    assert list(lst) == ['b', 'c', 'a', 'f', 'aa', '_']


def test_add_sudo():
    tmpuser = config.core.user
    try:
        config.core.user = 'root'
        assert utils.add_sudo('ls').startswith('sudo')
        config.core.user = ''
        assert utils.add_sudo('ls') == 'ls'
    finally:
        config.core.user = tmpuser


def test_str2tmp():
    txt = "This is a test string"
    filename = utils.str2tmp(txt)
    assert os.path.isfile(filename)
    assert open(filename).read() == txt + "\n"
    assert utils.file2str(filename) == txt
    # TODO: should this really return
    # an empty line at the end?
    assert utils.file2list(filename) == [txt, '']
    os.unlink(filename)


def test_sanity():
    sane_paths = ['foo/bar', 'foo', '/foo/bar', 'foo0',
                  'foo_bar', 'foo-bar', '0foo', '.foo',
                  'foo.bar']
    insane_paths = ['#foo', 'foo?', 'foo*', 'foo$', 'foo[bar]',
                    'foo`', "foo'", 'foo/*']
    for p in sane_paths:
        assert utils.is_path_sane(p)
    for p in insane_paths:
        assert not utils.is_path_sane(p)
    sane_filenames = ['foo', '0foo', '0', '.foo']
    insane_filenames = ['foo/bar']
    for p in sane_filenames:
        assert utils.is_filename_sane(p)
    for p in insane_filenames:
        assert not utils.is_filename_sane(p)
    sane_names = ['foo']
    insane_names = ["f'o"]
    for n in sane_names:
        assert utils.is_name_sane(n)
    for n in insane_names:
        assert not utils.is_name_sane(n)


def test_nvpairs2dict():
    assert utils.nvpairs2dict(['a=b', 'c=d']) == {'a': 'b', 'c': 'd'}
    assert utils.nvpairs2dict(['a=b=c', 'c=d']) == {'a': 'b=c', 'c': 'd'}
    assert utils.nvpairs2dict(['a']) == {'a': None}


def test_validity():
    assert utils.is_id_valid('foo0')
    assert not utils.is_id_valid('0foo')


def test_msec():
    assert utils.crm_msec('1ms') == 1
    assert utils.crm_msec('1s') == 1000
    assert utils.crm_msec('1us') == 0
    assert utils.crm_msec('1') == 1000
    assert utils.crm_msec('1m') == 60*1000
    assert utils.crm_msec('1h') == 60*60*1000


def test_parse_sysconfig():
    """
    bsc#1129317: Fails on this line

    FW_SERVICES_ACCEPT_EXT="0/0,tcp,22,,hitcount=3,blockseconds=60,recentname=ssh"
    """
    s = '''
FW_SERVICES_ACCEPT_EXT="0/0,tcp,22,,hitcount=3,blockseconds=60,recentname=ssh"
'''

    fd, fname = tmpfiles.create()
    with open(fname, 'w') as f:
        f.write(s)
    sc = utils.parse_sysconfig(fname)
    assert ("FW_SERVICES_ACCEPT_EXT" in sc)

def test_sysconfig_set():
    s = '''
FW_SERVICES_ACCEPT_EXT="0/0,tcp,22,,hitcount=3,blockseconds=60,recentname=ssh"
'''
    fd, fname = tmpfiles.create()
    with open(fname, 'w') as f:
        f.write(s)
    utils.sysconfig_set(fname, FW_SERVICES_ACCEPT_EXT="foo=bar", FOO="bar")
    sc = utils.parse_sysconfig(fname)
    assert (sc.get("FW_SERVICES_ACCEPT_EXT") == "foo=bar")
    assert (sc.get("FOO") == "bar")

@mock.patch("crmsh.utils.is_program")
def test_detect_cloud_not_dmidecode(mock_is_program):
    mock_is_program.return_value = False
    assert utils.detect_cloud() is None
    mock_is_program.assert_called_once_with("dmidecode")

@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
def test_detect_cloud_aws(mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.return_value = (0, "4.2.amazon")
    assert utils.detect_cloud() == "amazon-web-services"
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_called_once_with("dmidecode -s system-version")


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
def test_detect_cloud_aws_error(mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.return_value = (1, "other")
    assert utils.detect_cloud() is None
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_called_once_with("dmidecode -s system-version")


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
@mock.patch("crmsh.utils._cloud_metadata_request")
def test_detect_cloud_microsoft(mock_metadata, mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.side_effect = [(0, "other"), (0, "microsoft corporation")]
    mock_metadata.return_value = "10.10.10.10"
    assert utils.detect_cloud() == "microsoft-azure"
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_has_calls([
        mock.call("dmidecode -s system-version"),
        mock.call("dmidecode -s system-manufacturer")
    ])
    mock_metadata.assert_called_once_with(
        "http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/privateIpAddress?api-version=2017-08-01&format=text",
        headers={"Metadata": "true"})
    assert utils._ip_for_cloud == "10.10.10.10"


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
@mock.patch("crmsh.utils._cloud_metadata_request")
def test_detect_cloud_microsoft_error(mock_metadata, mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.side_effect = [
        (0, "other"), (0, "microsoft corporation"), (0, "microsoft corporation")]
    mock_metadata.return_value = None
    assert utils.detect_cloud() is None
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_has_calls([
        mock.call("dmidecode -s system-version"),
        mock.call("dmidecode -s system-manufacturer")
    ])
    mock_metadata.assert_called_once_with(
        "http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/privateIpAddress?api-version=2017-08-01&format=text",
        headers={"Metadata": "true"})
    assert utils._ip_for_cloud is None


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
@mock.patch("crmsh.utils._cloud_metadata_request")
def test_detect_cloud_microsoft_rc_error(mock_metadata, mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.side_effect = [
        (0, "other"), (1, "other"), (0, "other")]
    mock_metadata.return_value = None
    assert utils.detect_cloud() is None
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_has_calls([
        mock.call("dmidecode -s system-version"),
        mock.call("dmidecode -s system-manufacturer")
    ])
    assert mock_metadata.call_count == 0
    assert utils._ip_for_cloud is None


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
@mock.patch("crmsh.utils._cloud_metadata_request")
def test_detect_cloud_gcp(mock_metadata, mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.side_effect = [
        (0, "other"), (1, "other"), (0, "Google")]
    mock_metadata.return_value = "10.10.10.10"
    assert utils.detect_cloud() == "google-cloud-platform"
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_has_calls([
        mock.call("dmidecode -s system-version"),
        mock.call("dmidecode -s system-manufacturer"),
        mock.call("dmidecode -s bios-vendor")
    ])
    mock_metadata.assert_called_once_with(
        "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip",
        headers={"Metadata-Flavor": "Google"})
    assert utils._ip_for_cloud == "10.10.10.10"


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
@mock.patch("crmsh.utils._cloud_metadata_request")
def test_detect_cloud_gcp_error(mock_metadata, mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.side_effect = [
        (0, "other"), (0, "other"), (0, "Google")]
    mock_metadata.return_value = None
    assert utils.detect_cloud() is None
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_has_calls([
        mock.call("dmidecode -s system-version"),
        mock.call("dmidecode -s system-manufacturer"),
        mock.call("dmidecode -s bios-vendor")
    ])
    mock_metadata.assert_called_once_with(
        "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip",
        headers={"Metadata-Flavor": "Google"})
    assert utils._ip_for_cloud is None


@mock.patch("crmsh.utils.is_program")
@mock.patch("crmsh.utils.get_stdout")
@mock.patch("crmsh.utils._cloud_metadata_request")
def test_detect_cloud_gcp_rc_error(mock_metadata, mock_get_stdout, mock_is_program):
    mock_is_program.return_value = True
    mock_get_stdout.side_effect = [
        (0, "other"), (0, "other"), (1, "other")]
    mock_metadata.return_value = None
    assert utils.detect_cloud() is None
    mock_is_program.assert_called_once_with("dmidecode")
    mock_get_stdout.assert_has_calls([
        mock.call("dmidecode -s system-version"),
        mock.call("dmidecode -s system-manufacturer"),
        mock.call("dmidecode -s bios-vendor")
    ])
    assert mock_metadata.call_count == 0
    assert utils._ip_for_cloud is None


@mock.patch("crmsh.utils.get_stdout")
def test_interface_choice(mock_get_stdout):
    ip_a_output = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host 
       valid_lft forever preferred_lft forever
2: enp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP group default qlen 1000
    link/ether 52:54:00:9e:1b:4f brd ff:ff:ff:ff:ff:ff
    inet 192.168.122.241/24 brd 192.168.122.255 scope global enp1s0
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:ff:fe9e:1b4f/64 scope link 
       valid_lft forever preferred_lft forever
3: br-933fa0e1438c: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default 
    link/ether 9e:fe:24:df:59:49 brd ff:ff:ff:ff:ff:ff
    inet 10.10.10.1/24 brd 10.10.10.255 scope global br-933fa0e1438c
       valid_lft forever preferred_lft forever
    inet6 fe80::9cfe:24ff:fedf:5949/64 scope link 
       valid_lft forever preferred_lft forever
4: veth3fff6e9@if7: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue master docker0 state UP group default 
    link/ether 1e:2c:b3:73:6b:42 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    inet6 fe80::1c2c:b3ff:fe73:6b42/64 scope link 
       valid_lft forever preferred_lft forever
       valid_lft forever preferred_lft forever
"""
    mock_get_stdout.return_value = (0, ip_a_output)
    assert utils.interface_choice() == ["enp1s0", "br-933fa0e1438c", "veth3fff6e9"]
    mock_get_stdout.assert_called_once_with("ip a")


class TestIP(unittest.TestCase):
    """
    Unitary tests for class utils.IP
    """
    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.ip_inst = utils.IP("10.10.10.1")

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch('ipaddress.ip_address')
    def test_ip_address(self, mock_ip_address):
        mock_ip_address_inst = mock.Mock()
        mock_ip_address.return_value = mock_ip_address_inst
        self.ip_inst.ip_address
        mock_ip_address.assert_called_once_with("10.10.10.1")

    @mock.patch('crmsh.utils.IP.ip_address', new_callable=mock.PropertyMock)
    def test_version(self, mock_ip_address):
        mock_ip_address_inst = mock.Mock(version=4)
        mock_ip_address.return_value = mock_ip_address_inst
        res = self.ip_inst.version
        self.assertEqual(res, mock_ip_address_inst.version)
        mock_ip_address.assert_called_once_with()

    @mock.patch('crmsh.utils.IP.ip_address', new_callable=mock.PropertyMock)
    def test_is_mcast(self, mock_ip_address):
        mock_ip_address_inst = mock.Mock(is_multicast=False)
        mock_ip_address.return_value = mock_ip_address_inst
        res = utils.IP.is_mcast("10.10.10.1")
        self.assertEqual(res, False)
        mock_ip_address.assert_called_once_with()

    @mock.patch('crmsh.utils.IP.version', new_callable=mock.PropertyMock)
    def test_is_ipv6(self, mock_version):
        mock_version.return_value = 4
        res = utils.IP.is_ipv6("10.10.10.1")
        self.assertEqual(res, False)
        mock_version.assert_called_once_with()

    @mock.patch('crmsh.utils.IP.ip_address', new_callable=mock.PropertyMock)
    def test_is_valid_ip_exception(self, mock_ip_address):
        mock_ip_address.side_effect = ValueError
        res = utils.IP.is_valid_ip("xxxx")
        self.assertEqual(res, False)
        mock_ip_address.assert_called_once_with()

    @mock.patch('crmsh.utils.IP.ip_address', new_callable=mock.PropertyMock)
    def test_is_valid_ip(self, mock_ip_address):
        res = utils.IP.is_valid_ip("10.10.10.1")
        self.assertEqual(res, True)
        mock_ip_address.assert_called_once_with()

    @mock.patch('crmsh.utils.IP.ip_address', new_callable=mock.PropertyMock)
    def test_is_loopback(self, mock_ip_address):
        mock_ip_address_inst = mock.Mock(is_loopback=False)
        mock_ip_address.return_value = mock_ip_address_inst
        res = self.ip_inst.is_loopback
        self.assertEqual(res, mock_ip_address_inst.is_loopback)
        mock_ip_address.assert_called_once_with()

    @mock.patch('crmsh.utils.IP.ip_address', new_callable=mock.PropertyMock)
    def test_is_link_local(self, mock_ip_address):
        mock_ip_address_inst = mock.Mock(is_link_local=False)
        mock_ip_address.return_value = mock_ip_address_inst
        res = self.ip_inst.is_link_local
        self.assertEqual(res, mock_ip_address_inst.is_link_local)
        mock_ip_address.assert_called_once_with()


class TestInterface(unittest.TestCase):
    """
    Unitary tests for class utils.Interface
    """
    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.interface = utils.Interface("10.10.10.123/24")

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    def test_ip_with_mask(self):
        assert self.interface.ip_with_mask == "10.10.10.123/24"

    @mock.patch('ipaddress.ip_interface')
    def test_ip_interface(self, mock_ip_interface):
        mock_ip_interface_inst = mock.Mock()
        mock_ip_interface.return_value = mock_ip_interface_inst
        self.interface.ip_interface
        mock_ip_interface.assert_called_once_with("10.10.10.123/24")

    @mock.patch('crmsh.utils.Interface.ip_interface', new_callable=mock.PropertyMock)
    def test_network(self, mock_ip_interface):
        mock_ip_interface_inst = mock.Mock()
        mock_ip_interface.return_value = mock_ip_interface_inst
        mock_ip_interface_inst.network = mock.Mock(network_address="10.10.10.0")
        assert self.interface.network == "10.10.10.0"
        mock_ip_interface.assert_called_once_with()

    @mock.patch('crmsh.utils.Interface.ip_interface', new_callable=mock.PropertyMock)
    @mock.patch('crmsh.utils.IP')
    def test_ip_in_network(self, mock_ip, mock_ip_interface):
        mock_ip_inst = mock.Mock(ip_address="10.10.10.123")
        mock_ip.return_value = mock_ip_inst
        mock_ip_interface_inst = mock.Mock(network=["10.10.10.123"])
        mock_ip_interface.return_value = mock_ip_interface_inst
        res = self.interface.ip_in_network("10.10.10.123")
        assert res is True
        mock_ip.assert_called_once_with("10.10.10.123")
        mock_ip_interface.assert_called_once_with()


class TestInterfacesInfo(unittest.TestCase):
    """
    Unitary tests for class utils.InterfacesInfo
    """

    network_output_error = """1: lo    inet 127.0.0.1/8 scope host lo\       valid_lft forever preferred_lft forever
2: enp1s0    inet 192.168.122.241/24 brd 192.168.122.255 scope global enp1s0"""

    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.interfaces_info = utils.InterfacesInfo()
        self.interfaces_info_with_second_hb = utils.InterfacesInfo(second_heartbeat=True)
        self.interfaces_info_with_custom_nic = utils.InterfacesInfo(second_heartbeat=True, custom_nic_list=['eth1'])
        self.interfaces_info_with_wrong_nic = utils.InterfacesInfo(custom_nic_list=['eth7'])
        self.interfaces_info_fake = utils.InterfacesInfo()
        self.interfaces_info_fake._nic_info_dict = {
                "eth0": [mock.Mock(ip="10.10.10.1", network="10.10.10.0"), mock.Mock(ip="10.10.10.2", network="10.10.10.0")],
                "eth1": [mock.Mock(ip="20.20.20.1", network="20.20.20.0")]
                }
        self.interfaces_info_fake._default_nic_list = ["eth7"]

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_interfaces_info_no_address(self, mock_run):
        only_lo = "1: lo    inet 127.0.0.1/8 scope host lo\       valid_lft forever preferred_lft forever"
        mock_run.return_value = (0, only_lo, None)
        with self.assertRaises(ValueError) as err:
            self.interfaces_info.get_interfaces_info()
        self.assertEqual("No address configured", str(err.exception))
        mock_run.assert_called_once_with("ip -4 -o addr show")

    @mock.patch('crmsh.utils.Interface')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_interfaces_info_one_addr(self, mock_run, mock_interface):
        mock_run.return_value = (0, self.network_output_error, None)
        mock_interface_inst_1 = mock.Mock(is_loopback=True, is_link_local=False)
        mock_interface_inst_2 = mock.Mock(is_loopback=False, is_link_local=False)
        mock_interface.side_effect = [mock_interface_inst_1, mock_interface_inst_2]

        with self.assertRaises(ValueError) as err:
            self.interfaces_info_with_second_hb.get_interfaces_info()
        self.assertEqual("Cannot configure second heartbeat, since only one address is available", str(err.exception))

        mock_run.assert_called_once_with("ip -4 -o addr show")
        mock_interface.assert_has_calls([
            mock.call("127.0.0.1/8"),
            mock.call("192.168.122.241/24")
            ])

    def test_interface_list(self):
        res = self.interfaces_info_fake.interface_list
        assert len(res) == 3

    @mock.patch('crmsh.utils.InterfacesInfo.interface_list', new_callable=mock.PropertyMock)
    def test_ip_list(self, mock_interface_list):
        mock_interface_list.return_value = [
                mock.Mock(ip="10.10.10.1"),
                mock.Mock(ip="10.10.10.2")
                ]
        res = self.interfaces_info_fake.ip_list
        self.assertEqual(res, ["10.10.10.1", "10.10.10.2"])
        mock_interface_list.assert_called_once_with()

    @mock.patch('crmsh.utils.InterfacesInfo.ip_list', new_callable=mock.PropertyMock)
    @mock.patch('crmsh.utils.InterfacesInfo.get_interfaces_info')
    def test_get_local_ip_list(self, mock_get_info, mock_ip_list):
        mock_ip_list.return_value = ["10.10.10.1", "10.10.10.2"]
        res = utils.InterfacesInfo.get_local_ip_list(False)
        self.assertEqual(res, mock_ip_list.return_value)
        mock_get_info.assert_called_once_with()
        mock_ip_list.assert_called_once_with()

    @mock.patch('crmsh.utils.InterfacesInfo.interface_list', new_callable=mock.PropertyMock)
    def test_network_list(self, mock_interface_list):
        mock_interface_list.return_value = [
                mock.Mock(network="10.10.10.0"),
                mock.Mock(network="20.20.20.0")
                ]
        res = self.interfaces_info.network_list
        self.assertEqual(res, list(set(["10.10.10.0", "20.20.20.0"])))
        mock_interface_list.assert_called_once_with()

    def test_nic_first_ip(self):
        res = self.interfaces_info_fake._nic_first_ip("eth0")
        self.assertEqual(res, "10.10.10.1")

    @mock.patch('crmsh.utils.InterfacesInfo.nic_list', new_callable=mock.PropertyMock)
    @mock.patch('crmsh.utils.common_warn')
    @mock.patch('crmsh.utils.InterfacesInfo.get_interfaces_info')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_default_nic_list_from_route_no_default(self, mock_run, mock_get_interfaces_info, mock_warn, mock_nic_list):
        output = """10.10.10.0/24 dev eth1 proto kernel scope link src 10.10.10.51 
        20.20.20.0/24 dev eth2 proto kernel scope link src 20.20.20.51"""
        mock_run.return_value = (0, output, None)
        mock_nic_list.side_effect = [["eth0", "eth1"], ["eth0", "eth1"]]

        res = self.interfaces_info.get_default_nic_list_from_route()
        self.assertEqual(res, ["eth0"])

        mock_run.assert_called_once_with("ip -o route show")
        mock_warn.assert_called_once_with("No default route configured. Using the first found nic")
        mock_nic_list.assert_has_calls([mock.call(), mock.call()])

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_default_nic_list_from_route(self, mock_run):
        output = """default via 192.168.122.1 dev eth8 proto dhcp 
        10.10.10.0/24 dev eth1 proto kernel scope link src 10.10.10.51 
        20.20.20.0/24 dev eth2 proto kernel scope link src 20.20.20.51 
        192.168.122.0/24 dev eth8 proto kernel scope link src 192.168.122.120"""
        mock_run.return_value = (0, output, None)

        res = self.interfaces_info.get_default_nic_list_from_route()
        self.assertEqual(res, ["eth8"])

        mock_run.assert_called_once_with("ip -o route show")

    @mock.patch('crmsh.utils.InterfacesInfo.nic_list', new_callable=mock.PropertyMock)
    def test_get_default_ip_list_failed_detect(self, mock_nic_list):
        mock_nic_list.side_effect = [["eth0", "eth1"], ["eth0", "eth1"]]

        with self.assertRaises(ValueError) as err:
            self.interfaces_info_with_wrong_nic.get_default_ip_list()
        self.assertEqual("Failed to detect IP address for eth7", str(err.exception))

        mock_nic_list.assert_has_calls([mock.call(), mock.call()])

    @mock.patch('crmsh.utils.InterfacesInfo._nic_first_ip')
    @mock.patch('crmsh.utils.InterfacesInfo.nic_list', new_callable=mock.PropertyMock)
    def test_get_default_ip_list(self, mock_nic_list, mock_first_ip):
        mock_nic_list.side_effect = [["eth0", "eth1"], ["eth0", "eth1"], ["eth0", "eth1"]]
        mock_first_ip.side_effect = ["10.10.10.1", "20.20.20.1"]

        res = self.interfaces_info_with_custom_nic.get_default_ip_list()
        self.assertEqual(res, ["10.10.10.1", "20.20.20.1"])

        mock_nic_list.assert_has_calls([mock.call(), mock.call(), mock.call()])
        mock_first_ip.assert_has_calls([mock.call("eth1"), mock.call("eth0")])

    @mock.patch('crmsh.utils.Interface')
    @mock.patch('crmsh.utils.InterfacesInfo.interface_list', new_callable=mock.PropertyMock)
    @mock.patch('crmsh.utils.InterfacesInfo.get_interfaces_info')
    @mock.patch('crmsh.utils.IP.is_ipv6')
    def test_ip_in_network(self, mock_is_ipv6, mock_get_interfaces_info, mock_interface_list, mock_interface):
        mock_is_ipv6.return_value = False
        mock_interface_inst_1 = mock.Mock()
        mock_interface_inst_2 = mock.Mock()
        mock_interface_inst_1.ip_in_network.return_value = False
        mock_interface_inst_2.ip_in_network.return_value = True
        mock_interface_list.return_value = [mock_interface_inst_1, mock_interface_inst_2]

        res = utils.InterfacesInfo.ip_in_network("10.10.10.1")
        assert res is True

        mock_is_ipv6.assert_called_once_with("10.10.10.1")
        mock_get_interfaces_info.assert_called_once_with()
        mock_interface_list.assert_called_once_with()
        mock_interface_inst_1.ip_in_network.assert_called_once_with("10.10.10.1")
        mock_interface_inst_2.ip_in_network.assert_called_once_with("10.10.10.1")

    @mock.patch('crmsh.utils.Interface')
    @mock.patch('crmsh.utils.InterfacesInfo.interface_list', new_callable=mock.PropertyMock)
    @mock.patch('crmsh.utils.InterfacesInfo.get_interfaces_info')
    @mock.patch('crmsh.utils.IP.is_ipv6')
    def test_ip_in_network_false(self, mock_is_ipv6, mock_get_interfaces_info, mock_interface_list, mock_interface):
        mock_is_ipv6.return_value = False
        mock_interface_inst_1 = mock.Mock()
        mock_interface_inst_2 = mock.Mock()
        mock_interface_inst_1.ip_in_network.return_value = False
        mock_interface_inst_2.ip_in_network.return_value = False
        mock_interface_list.return_value = [mock_interface_inst_1, mock_interface_inst_2]

        res = utils.InterfacesInfo.ip_in_network("10.10.10.1")
        assert res is False

        mock_is_ipv6.assert_called_once_with("10.10.10.1")
        mock_get_interfaces_info.assert_called_once_with()
        mock_interface_list.assert_called_once_with()
        mock_interface_inst_1.ip_in_network.assert_called_once_with("10.10.10.1")
        mock_interface_inst_2.ip_in_network.assert_called_once_with("10.10.10.1")


class TestServiceManager(unittest.TestCase):
    """
    Unitary tests for class utils.ServiceManager
    """

    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.service_local = utils.ServiceManager("service1")
        self.service_remote = utils.ServiceManager("service1", "node1")

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch("crmsh.utils.get_stdout_stderr")
    def test_do_action_except_run_error(self, mock_run):
        mock_run.return_value = (1, None, "this command failed")
        with self.assertRaises(ValueError) as err:
            self.service_local._do_action("start")
        self.assertEqual("Run \"systemctl start service1\" error: this command failed", str(err.exception))
        mock_run.assert_called_once_with("systemctl start service1")

    @mock.patch("crmsh.utils.run_cmd_on_remote")
    def test_do_action_remote(self, mock_run_remote):
        mock_run_remote.return_value = (0, "data", None)
        rc, out = self.service_remote._do_action("start")
        assert rc == True
        assert out == "data"
        mock_run_remote.assert_called_once_with("systemctl start service1",
                "node1",
                "Run \"systemctl start service1\" on node1")

    def test_is_available(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, "service1 service2")
        assert self.service_local.is_available() == True
        self.service_local._do_action.assert_called_once_with("list-unit-files")

    def test_is_enabled(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, None)
        assert self.service_local.is_enabled() == True
        self.service_local._do_action.assert_called_once_with("is-enabled")

    def test_is_active(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, None)
        assert self.service_local.is_active() == True
        self.service_local._do_action.assert_called_once_with("is-active")

    def test_start(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, None)
        self.service_local.start()
        self.service_local._do_action.assert_called_once_with("start")

    def test_stop(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, None)
        self.service_local.stop()
        self.service_local._do_action.assert_called_once_with("stop")

    def test_enable(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, None)
        self.service_local.enable()
        self.service_local._do_action.assert_called_once_with("enable")

    def test_disable(self):
        self.service_local._do_action = mock.Mock()
        self.service_local._do_action.return_value = (True, None)
        self.service_local.disable()
        self.service_local._do_action.assert_called_once_with("disable")

    @mock.patch("crmsh.utils.ServiceManager.is_available")
    def test_service_is_available(self, mock_available):
        mock_available.return_value = True
        res = utils.ServiceManager.service_is_available("service1")
        self.assertEqual(res, True)
        mock_available.assert_called_once_with()

    @mock.patch("crmsh.utils.ServiceManager.is_enabled")
    def test_service_is_enabled(self, mock_enabled):
        mock_enabled.return_value = True
        res = utils.ServiceManager.service_is_enabled("service1")
        self.assertEqual(res, True)
        mock_enabled.assert_called_once_with()

    @mock.patch("crmsh.utils.ServiceManager.is_active")
    def test_service_is_active(self, mock_active):
        mock_active.return_value = True
        res = utils.ServiceManager.service_is_active("service1")
        self.assertEqual(res, True)
        mock_active.assert_called_once_with()

    @mock.patch('crmsh.utils.ServiceManager.start')
    @mock.patch('crmsh.utils.ServiceManager.enable')
    def test_start_service(self, mock_enable, mock_start):
        utils.ServiceManager.start_service("service1", enable=True)
        mock_enable.assert_called_once_with()
        mock_start.assert_called_once_with()

    @mock.patch('crmsh.utils.ServiceManager.stop')
    @mock.patch('crmsh.utils.ServiceManager.disable')
    def test_stop_service(self, mock_disable, mock_stop):
        utils.ServiceManager.stop_service("service1", disable=True)
        mock_disable.assert_called_once_with()
        mock_stop.assert_called_once_with()

    @mock.patch('crmsh.utils.ServiceManager.enable')
    def test_enable_service(self, mock_enable):
        utils.ServiceManager.enable_service("service1")
        mock_enable.assert_called_once_with()

    @mock.patch('crmsh.utils.ServiceManager.disable')
    def test_disable_service(self, mock_disable):
        utils.ServiceManager.disable_service("service1")
        mock_disable.assert_called_once_with()


@mock.patch("crmsh.utils.get_nodeid_from_name")
def test_get_iplist_from_name_no_nodeid(mock_get_nodeid):
    mock_get_nodeid.return_value = None
    res = utils.get_iplist_from_name("test")
    assert res == []
    mock_get_nodeid.assert_called_once_with("test")


@mock.patch("crmsh.utils.get_nodeinfo_from_cmaptool")
@mock.patch("crmsh.utils.get_nodeid_from_name")
def test_get_iplist_from_name_no_nodeinfo(mock_get_nodeid, mock_get_nodeinfo):
    mock_get_nodeid.return_value = "1"
    mock_get_nodeinfo.return_value = None
    res = utils.get_iplist_from_name("test")
    assert res == []
    mock_get_nodeid.assert_called_once_with("test")
    mock_get_nodeinfo.assert_called_once_with()


@mock.patch("crmsh.utils.get_nodeinfo_from_cmaptool")
@mock.patch("crmsh.utils.get_nodeid_from_name")
def test_get_iplist_from_name(mock_get_nodeid, mock_get_nodeinfo):
    mock_get_nodeid.return_value = "1"
    mock_get_nodeinfo.return_value = {"1": ["10.10.10.1"], "2": ["10.10.10.2"]}
    res = utils.get_iplist_from_name("test")
    assert res == ["10.10.10.1"]
    mock_get_nodeid.assert_called_once_with("test")
    mock_get_nodeinfo.assert_called_once_with()
