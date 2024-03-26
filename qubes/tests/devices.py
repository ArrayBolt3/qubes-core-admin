# pylint: disable=protected-access,pointless-statement

#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2015-2016  Joanna Rutkowska <joanna@invisiblethingslab.com>
# Copyright (C) 2015-2016  Wojtek Porczyk <woju@invisiblethingslab.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, see <https://www.gnu.org/licenses/>.
#

import qubes.devices
from qubes.device_protocol import (Device, DeviceInfo, DeviceAssignment,
                                   DeviceInterface)

import qubes.tests


class TestDevice(DeviceInfo):
    # pylint: disable=too-few-public-methods
    pass


class TestVMCollection(dict):
    def __iter__(self):
        return iter(set(self.values()))


class TestApp(object):
    # pylint: disable=too-few-public-methods
    def __init__(self):
        self.domains = TestVMCollection()


class TestVM(qubes.tests.TestEmitter):
    def __init__(self, app, name, *args, **kwargs):
        super(TestVM, self).__init__(*args, **kwargs)
        self.app = app
        self.name = name
        self.device = TestDevice(self, 'testdev', 'testclass')
        self.events_enabled = True
        self.devices = {
            'testclass': qubes.devices.DeviceCollection(self, 'testclass')
        }
        self.app.domains[name] = self
        self.app.domains[self] = self
        self.running = False

    def __str__(self):
        return self.name

    @qubes.events.handler('device-list-attached:testclass')
    def dev_testclass_list_attached(self, event, persistent=False):
        for vm in self.app.domains:
            if vm.device.data.get('test_frontend_domain', None) == self:
                yield (vm.device, {})

    @qubes.events.handler('device-list:testclass')
    def dev_testclass_list(self, event):
        yield self.device

    def is_halted(self):
        return not self.running

    def is_running(self):
        return self.running

    class log:
        @staticmethod
        def exception(message):
            pass


class TC_00_DeviceCollection(qubes.tests.QubesTestCase):
    def setUp(self):
        super().setUp()
        self.app = TestApp()
        self.emitter = TestVM(self.app, 'vm')
        self.app.domains['vm'] = self.emitter
        self.device = self.emitter.device
        self.collection = self.emitter.devices['testclass']
        self.assignment = DeviceAssignment(
            backend_domain=self.device.backend_domain,
            ident=self.device.ident,
            attach_automatically=True,
            required=True,
        )

    def attach(self):
        self.emitter.running = True
        # device-attach event not implemented, so manipulate object manually
        self.device.data['test_frontend_domain'] = self.emitter

    def detach(self):
        # device-detach event not implemented, so manipulate object manually
        del self.device.data['test_frontend_domain']

    def test_000_init(self):
        self.assertFalse(self.collection._set)

    def test_001_attach(self):
        self.emitter.running = True
        self.loop.run_until_complete(self.collection.attach(self.assignment))
        self.assertEventFired(self.emitter, 'device-pre-attach:testclass')
        self.assertEventFired(self.emitter, 'device-attach:testclass')
        self.assertEventNotFired(self.emitter, 'device-pre-detach:testclass')
        self.assertEventNotFired(self.emitter, 'device-detach:testclass')

    def test_002_attach_to_halted(self):
        with self.assertRaises(qubes.exc.QubesVMNotRunningError):
            self.loop.run_until_complete(
                self.collection.attach(self.assignment))

    def test_003_detach(self):
        self.attach()
        self.loop.run_until_complete(self.collection.detach(self.assignment))
        self.assertEventFired(self.emitter, 'device-pre-detach:testclass')
        self.assertEventFired(self.emitter, 'device-detach:testclass')

    def test_004_detach_from_halted(self):
        with self.assertRaises(LookupError):
            self.loop.run_until_complete(
                self.collection.detach(self.assignment))

    def test_010_empty_detach(self):
        self.emitter.running = True
        with self.assertRaises(LookupError):
            self.loop.run_until_complete(
                self.collection.detach(self.assignment))

    def test_011_empty_unassign(self):
        for _ in range(2):
            with self.assertRaises(LookupError):
                self.loop.run_until_complete(
                    self.collection.unassign(self.assignment))
            self.emitter.running = True

    def test_012_double_attach(self):
        self.attach()
        with self.assertRaises(qubes.devices.DeviceAlreadyAttached):
            self.loop.run_until_complete(
                self.collection.attach(self.assignment))

    def test_013_double_detach(self):
        self.attach()
        self.loop.run_until_complete(self.collection.detach(self.assignment))
        self.detach()

        with self.assertRaises(qubes.devices.DeviceNotAssigned):
            self.loop.run_until_complete(
                self.collection.detach(self.assignment))

    def test_014_double_assign(self):
        self.loop.run_until_complete(self.collection.assign(self.assignment))

        with self.assertRaises(qubes.devices.DeviceAlreadyAssigned):
            self.loop.run_until_complete(
                self.collection.assign(self.assignment))

    def test_015_double_unassign(self):
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.loop.run_until_complete(self.collection.unassign(self.assignment))

        with self.assertRaises(qubes.devices.DeviceNotAssigned):
            self.loop.run_until_complete(
                self.collection.unassign(self.assignment))

    def test_016_list_assigned(self):
        self.assertEqual(set([]), set(self.collection.get_assigned_devices()))
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEqual({self.device},
                         set(self.collection.get_assigned_devices()))
        self.assertEqual(set([]),
                         set(self.collection.get_attached_devices()))
        self.assertEqual({self.device},
                         set(self.collection.get_dedicated_devices()))

    def test_017_list_attached(self):
        self.assignment.required = False
        self.attach()
        self.assertEqual({self.device},
                         set(self.collection.get_attached_devices()))
        self.assertEqual(set([]),
                         set(self.collection.get_assigned_devices()))
        self.assertEqual({self.device},
                         set(self.collection.get_dedicated_devices()))
        self.assertEventFired(self.emitter, 'device-list-attached:testclass')

    def test_018_list_available(self):
        self.assertEqual({self.device}, set(self.collection))
        self.assertEventFired(self.emitter, 'device-list:testclass')

    def test_020_update_required_to_false(self):
        self.assertEqual(set([]), set(self.collection.get_assigned_devices()))
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.attach()
        self.assertEqual(
            {self.device},
            set(self.collection.get_assigned_devices(required_only=True)))
        self.assertEqual(
            {self.device}, set(self.collection.get_assigned_devices()))
        self.loop.run_until_complete(
            self.collection.update_required(self.device, False))
        self.assertEqual(
            {self.device}, set(self.collection.get_assigned_devices()))
        self.assertEqual(
            {self.device}, set(self.collection.get_attached_devices()))

    def test_021_update_required_to_true(self):
        self.assignment.required = False
        self.attach()
        self.assertEqual(set(), set(self.collection.get_assigned_devices()))
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEqual(
            set(),
            set(self.collection.get_assigned_devices(required_only=True)))
        self.assertEqual({self.device},
                         set(self.collection.get_attached_devices()))
        self.assertEqual({self.device}
                         , set(self.collection.get_assigned_devices()))
        self.assertEqual({self.device},
                         set(self.collection.get_attached_devices()))
        self.loop.run_until_complete(
            self.collection.update_required(self.device, True))
        self.assertEqual({self.device},
                         set(self.collection.get_assigned_devices()))
        self.assertEqual({self.device},
                         set(self.collection.get_attached_devices()))

    def test_022_update_required_reject_not_running(self):
        self.assertEqual(set([]), set(self.collection.get_assigned_devices()))
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEqual({self.device},
                         set(self.collection.get_assigned_devices()))
        self.assertEqual(set(), set(self.collection.get_attached_devices()))
        with self.assertRaises(qubes.exc.QubesVMNotStartedError):
            self.loop.run_until_complete(
                self.collection.update_required(self.device, False))

    def test_023_update_required_reject_not_attached(self):
        self.assertEqual(set(), set(self.collection.get_assigned_devices()))
        self.assertEqual(set(), set(self.collection.get_attached_devices()))
        self.emitter.running = True
        with self.assertRaises(qubes.exc.QubesValueError):
            self.loop.run_until_complete(
                self.collection.update_required(self.device, True))
        with self.assertRaises(qubes.exc.QubesValueError):
            self.loop.run_until_complete(
                self.collection.update_required(self.device, False))

    def test_030_assign(self):
        self.emitter.running = True
        self.assignment.required = False
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventNotFired(self.emitter, 'device-unassign:testclass')

    def test_031_assign_to_halted(self):
        self.assignment.required = False
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventNotFired(self.emitter, 'device-unassign:testclass')

    def test_032_assign_required(self):
        self.emitter.running = True
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventNotFired(self.emitter, 'device-unassign:testclass')

    def test_033_assign_required_to_halted(self):
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventNotFired(self.emitter, 'device-unassign:testclass')

    def test_034_unassign_from_halted(self):
        self.assignment.required = False
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.loop.run_until_complete(self.collection.unassign(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventFired(self.emitter, 'device-unassign:testclass')

    def test_035_unassign(self):
        self.emitter.running = True
        self.assignment.required = False
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.loop.run_until_complete(self.collection.unassign(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventFired(self.emitter, 'device-unassign:testclass')

    def test_040_detach_required(self):
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.attach()
        with self.assertRaises(qubes.exc.QubesVMNotHaltedError):
            self.loop.run_until_complete(
                self.collection.detach(self.assignment))

    def test_041_detach_required_from_halted(self):
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        with self.assertRaises(LookupError):
            self.loop.run_until_complete(
                self.collection.detach(self.assignment))

    def test_042_unassign_required(self):
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.emitter.running = True
        with self.assertRaises(qubes.exc.QubesVMNotHaltedError):
            self.loop.run_until_complete(
                self.collection.unassign(self.assignment))

    def test_043_detach_assigned(self):
        self.assignment.required = False
        self.loop.run_until_complete(self.collection.assign(self.assignment))
        self.attach()
        self.loop.run_until_complete(self.collection.detach(self.assignment))
        self.assertEventFired(self.emitter, 'device-assign:testclass')
        self.assertEventFired(self.emitter, 'device-pre-detach:testclass')
        self.assertEventFired(self.emitter, 'device-detach:testclass')


class TC_01_DeviceManager(qubes.tests.QubesTestCase):
    def setUp(self):
        super().setUp()
        self.app = TestApp()
        self.emitter = TestVM(self.app, 'vm')
        self.manager = qubes.devices.DeviceManager(self.emitter)

    def test_000_init(self):
        self.assertEqual(self.manager, {})

    def test_001_missing(self):
        device = TestDevice(self.emitter.app.domains['vm'], 'testdev')
        assignment = DeviceAssignment(
            backend_domain=device.backend_domain,
            ident=device.ident,
            attach_automatically=True, required=True)
        self.loop.run_until_complete(
            self.manager['testclass'].assign(assignment))
        self.assertEqual(
            len(list(self.manager['testclass'].get_assigned_devices())), 1)


class TC_02_DeviceInfo(qubes.tests.QubesTestCase):
    def setUp(self):
        super().setUp()
        self.app = TestApp()
        self.vm = TestVM(self.app, 'vm')

    def test_010_serialize(self):
        device = DeviceInfo(
            backend_domain=self.vm,
            ident="1-1.1.1",
            devclass="bus",
            vendor="ITL",
            product="Qubes",
            manufacturer="",
            name="Some untrusted garbage",
            serial=None,
            interfaces=[DeviceInterface(" ******"),
                        DeviceInterface("u03**01")],
            additional_info="",
            date="06.12.23",
        )
        actual = device.serialize()
        expected = (
            b"manufacturer='unknown' self_identity='0000:0000::?******' "
            b"serial='unknown' ident='1-1.1.1' product='Qubes' "
            b"vendor='ITL' name='Some untrusted garbage' devclass='bus' "
            b"backend_domain='vm' interfaces=' ******u03**01' "
            b"_additional_info='' _date='06.12.23'")
        expected = set(expected.replace(b"Some untrusted garbage",
                                  b"Some_untrusted_garbage").split(b" "))
        actual = set(actual.replace(b"Some untrusted garbage",
                                    b"Some_untrusted_garbage").split(b" "))
        self.assertEqual(actual, expected)

    def test_011_serialize_with_parent(self):
        device = DeviceInfo(
            backend_domain=self.vm,
            ident="1-1.1.1",
            devclass="bus",
            vendor="ITL",
            product="Qubes",
            manufacturer="",
            name="Some untrusted garbage",
            serial=None,
            interfaces=[DeviceInterface(" ******"),
                        DeviceInterface("u03**01")],
            additional_info="",
            date="06.12.23",
            parent=Device(self.vm, '1-1.1', 'pci')
        )
        actual = device.serialize()
        expected = (
            b"manufacturer='unknown' self_identity='0000:0000::?******' "
            b"serial='unknown' ident='1-1.1.1' product='Qubes' "
            b"vendor='ITL' name='Some untrusted garbage' devclass='bus' "
            b"backend_domain='vm' interfaces=' ******u03**01' "
            b"_additional_info='' _date='06.12.23' "
            b"parent_ident='1-1.1' parent_devclass='pci'")
        expected = set(expected.replace(b"Some untrusted garbage",
                                        b"Some_untrusted_garbage").split(b" "))
        actual = set(actual.replace(b"Some untrusted garbage",
                                    b"Some_untrusted_garbage").split(b" "))
        self.assertEqual(actual, expected)

    def test_020_deserialize(self):
        serialized = (
            b"1-1.1.1 "
            b"manufacturer='unknown' self_identity='0000:0000::?******' "
            b"serial='unknown' ident='1-1.1.1' product='Qubes' "
            b"vendor='ITL' name='Some untrusted garbage' devclass='bus' "
            b"backend_domain='vm' interfaces=' ******u03**01' "
            b"_additional_info='' _date='06.12.23' "
            b"parent_ident='1-1.1' parent_devclass='None'")
        actual = DeviceInfo.deserialize(serialized, self.vm)
        expected = DeviceInfo(
            backend_domain=self.vm,
            ident="1-1.1.1",
            devclass="bus",
            vendor="ITL",
            product="Qubes",
            manufacturer="unknown",
            name="Some untrusted garbage",
            serial=None,
            interfaces=[DeviceInterface(" ******"),
                        DeviceInterface("u03**01")],
            additional_info="",
            date="06.12.23",
        )

        self.assertEqual(actual.backend_domain, expected.backend_domain)
        self.assertEqual(actual.ident, expected.ident)
        self.assertEqual(actual.devclass, expected.devclass)
        self.assertEqual(actual.vendor, expected.vendor)
        self.assertEqual(actual.product, expected.product)
        self.assertEqual(actual.manufacturer, expected.manufacturer)
        self.assertEqual(actual.name, expected.name)
        self.assertEqual(actual.serial, expected.serial)
        self.assertEqual(repr(actual.interfaces), repr(expected.interfaces))
        self.assertEqual(actual.self_identity, expected.self_identity)
        self.assertEqual(actual.data, expected.data)
