#    finlink.py
#    Copyright (C) 2014 by CJP
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

import time

import network
import messages



class FinLink:
	def __init__(self, context, localID, remoteID):
		self.context = context

		self.localID = localID

		self.remoteHost = "localhost" #TODO
		self.remotePort = 4321 #TODO
		self.remoteID = remoteID

		self.context.setTimer(time.time() + 1.0, self.handleReconnectTimeout)


	def connect(self, connection):
		print "Connection established"
		#TODO


	def isConnected(self):
		return False #TODO


	def handleReconnectTimeout(self):
		# Timeout was pointless if we've been connected:
		if self.isConnected():
			return

		print "Finlink reconnect timeout: connecting"

		# Note: the new connection will register itself at the context, so
		# it will not be deleted when it goes out of scope here.
		# Once (if) it's established, it will connect back to this FinLink.
		newConnection = network.Connection(self.context,
			(self.remoteHost, self.remotePort))

		# Already send a link establishment message:
		newConnection.sendMessage(messages.Link(self.remoteID))

		# Register again, in case the above connection fails:
		self.context.setTimer(time.time() + 1.0, self.handleReconnectTimeout)


