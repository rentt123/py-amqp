#!/usr/bin/env python
"""
Test amqplib.client_0_8.connection module

"""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>
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
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301

import sys
import time
import unittest

import settings


from amqplib.client_0_8 import Connection

class TestConnection(unittest.TestCase):
    def setUp(self):
        self.conn = Connection(**settings.connect_args)

    def tearDown(self):
        self.conn.close()

    def test_channel(self):
        ch = self.conn.channel(1)
        self.assertEqual(ch.channel_id, 1)

        ch2 = self.conn.channel()
        self.assertNotEqual(ch2.channel_id, 1)

        ch.close()
        ch2.close()


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConnection)
    unittest.TextTestRunner(**settings.test_args).run(suite)


if __name__ == '__main__':
    main()