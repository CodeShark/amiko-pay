#!/usr/bin/env python
#    twonodes.py
#    Copyright (C) 2014-2015 by CJP
#
#    This file is part of Amiko Pay.
#
#    Amiko Pay is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Amiko Pay is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Amiko Pay. If not, see <http://www.gnu.org/licenses/>.
#
#    Additional permission under GNU GPL version 3 section 7
#
#    If you modify this Program, or any covered work, by linking or combining it
#    with the OpenSSL library (or a modified version of that library),
#    containing parts covered by the terms of the OpenSSL License and the SSLeay
#    License, the licensors of this Program grant you additional permission to
#    convey the resulting work. Corresponding Source for a non-source form of
#    such a combination shall include the source code for the parts of the
#    OpenSSL library used as well as that of the covered work.

import time
import pprint
import sys
sys.path.append('../..')

from amiko.channels import plainchannel

from amiko import node
from amiko.core import settings

settings1 = settings.Settings()
settings1.bitcoinRPCURL = "dummy"
settings1.listenHost = "localhost"
settings1.listenPort = 4322
settings1.advertizedHost = settings1.listenHost
settings1.advertizedPort = settings1.listenPort
settings1.stateFile = "twonodes_1.dat"
settings1.payLogFile = "payments1.log"
with open(settings1.stateFile, "wb") as f:
	f.write("""
		{
			"Node":
			{
				"_class": "NodeState",
				"links":
				{
					"node1":
					{
						"_class": "Link",
						"channels":
						[
						{
						"_class": "PlainChannel",
						"state": "ready",
						"amountLocal": 1000,
						"amountRemote": 0,
						"transactionsIncomingLocked": {},
						"transactionsOutgoingLocked": {},
						"transactionsIncomingReserved": {},
						"transactionsOutgoingReserved": {}
						}
						]
					}
				},
				"connections":
				{
					"node1":
					{
						"_class": "PersistentConnection",
						"connectMessage":
						{
							"_class": "ConnectLink",
							"ID": "node2",
							"callbackHost": "localhost", "callbackPort": 4322, "callbackID": "node1"
						},
						"messages": [], "lastIndex": -1, "notYetTransmitted": 0,
						"host": "localhost", "port": 4323,
						"closing": false
					}
				},
				"transactions": {},
				"meetingPoints": {},
				"payeeLinks": {},
				"payerLink": null
			},
			"TimeoutMessages": []
		}
		""")
node1 = node.Node(settings1)
node1.start()

settings2 = settings.Settings()
settings2.bitcoinRPCURL = "dummy"
settings2.listenHost = "localhost"
settings2.listenPort = 4323
settings2.advertizedHost = settings2.listenHost
settings2.advertizedPort = settings2.listenPort
settings2.stateFile = "twonodes_2.dat"
settings2.payLogFile = "payments2.log"
with open(settings2.stateFile, "wb") as f:
	f.write("""
		{
			"Node":
			{
				"_class": "NodeState",
				"links":
				{
					"node2":
					{
						"_class": "Link",
						"channels":
						[
						{
						"_class": "PlainChannel",
						"state": "ready",
						"amountLocal": 0,
						"amountRemote": 1000,
						"transactionsIncomingLocked": {},
						"transactionsOutgoingLocked": {},
						"transactionsIncomingReserved": {},
						"transactionsOutgoingReserved": {}
						}
						]
					}
				},
				"connections":
				{
					"node2":
					{
						"_class": "PersistentConnection",
						"connectMessage":
						{
							"_class": "ConnectLink",
							"ID": "node1",
							"callbackHost": "localhost", "callbackPort": 4323, "callbackID": "node2"
						},
						"messages": [], "lastIndex": -1, "notYetTransmitted": 0,
						"host": "localhost", "port": 4322,
						"closing": false
					}
				},
				"transactions": {},
				"meetingPoints": {},
				"payeeLinks": {},
				"payerLink": null
			},
			"TimeoutMessages": []
		}
		""")
node2 = node.Node(settings2)
node2.start()

#Allow links to connect
time.sleep(3)

print "Node 1:"
pprint.pprint(node1.list())

print "Node 2:"
pprint.pprint(node2.list())

URL = node2.request(123, "receipt")
print "Payment URL:", URL

amount, receipt = node1.pay(URL)
print "Amount: ", amount
print "Receipt: ", receipt
paymentState = node1.confirmPayment(True)
print "Payment is ", paymentState

#Allow paylink to disconnect
time.sleep(0.5)

print "Node 1:"
pprint.pprint(node1.list())

print "Node 2:"
pprint.pprint(node2.list())

node1.stop()
node2.stop()


