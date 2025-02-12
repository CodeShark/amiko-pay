#    node.py
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


import threading
import os
import json
from urlparse import urlparse

from core import network
from core import event
from core import link
from core import meetingpoint
from core import paylink
from core import settings
from core import randomsource
from core import log
from core import paylog
from core import bitcoind
from core import watchdog

#Somehow it is hard to replace the above copyright information with a more
#sensible doc string...
__doc__ = """
Top-level Application Programming Interface for the Amiko payment system
"""

version = "0.1.0 (unstable,development)"
lastCopyrightYear = "2015"



class RoutingContext:
	"""
	The context in which transaction routing takes place.

	Contains all objects relevant to routing, such as links and meeting points.

	Intended for internal use by Node.
	Not intended to be part of the API.
	"""

	def __init__(self):
		self.links = []
		self.meetingPoints = []

	def getState(self, forDisplay=False):
		return \
		{
			"links":
			[lnk.getState(forDisplay) for lnk in self.links],

			"meetingPoints":
			[mp.getState(forDisplay) for mp in self.meetingPoints]
		}


def runInNodeThread(implementationFunc):
	"""
	Function decorator, which can be used by Node methods to have them
	called by an external thread, but have them run inside the internal thread
	of the Node object.

	Intended for internal use by Node.
	Not intended to be part of the API.
	"""

	def remoteCaller(self, *args, **kwargs):
		with self._commandFunctionLock:
			self._commandFunction = (implementationFunc, args, kwargs)
			self._commandProcessed.clear()
		self._commandProcessed.wait()

		if isinstance(self._commandReturnValue, Exception):
			raise self._commandReturnValue
		return self._commandReturnValue

	remoteCaller.__doc__ = implementationFunc.__doc__

	return remoteCaller



class Node(threading.Thread):
	"""
	A single Amiko node.

	A process can run multiple Amiko nodes by making multiple instances of
	this class. Each instance can have its own configuration, and runs in its
	own thread.

	After creating an instance, it can be started with the start() method.

	To stop the node, the stop() method must be called. This should always be
	done before program termination.
	"""

	def __init__(self, conf="amikopay.conf"):
		"""
		Constructor.

		Arguments:
		conf: Name of the configuration file to be loaded, or a
		      settings.Settings instance
		"""

		threading.Thread.__init__(self)

		if isinstance(conf, settings.Settings):
			self.settings = conf
		else:
			self.settings = settings.Settings(conf)

		self.bitcoind = bitcoind.Bitcoind(self.settings)
		self.watchdog = watchdog.Watchdog(self.bitcoind)

		self.context = event.Context()

		self.routingContext = RoutingContext()
		self.payees = []

		self.payLog = paylog.PayLog(self.settings)

		self.__stop = False
		self.__doSave = False

		self._commandFunctionLock = threading.Lock()
		self._commandFunction = None
		self._commandProcessed = threading.Event()
		self._commandReturnValue = None

		self.context.connect(None, event.signals.link,
			self.__handleLinkSignal)
		self.context.connect(None, event.signals.pay,
			self.__handlePaySignal)
		self.context.connect(None, event.signals.save,
			self.__handleSaveSignal)
		self.context.connectPost(event.signals.message,
			self.__postHandleMessageSignal)

		self.__loadState()


	def stop(self):
		"""
		Stops the Node object.

		This method blocks until the Node object is stopped completely.
		"""

		self.__stop = True
		self.join()


	@runInNodeThread
	def request(self, amount, receipt):
		"""
		Request a payment.

		Arguments:
		amount : The amount (integer, in Satoshi) to be paid
		receipt: A receipt for the payment

		Return value:
		The URL of the payment request
		"""

		#ID can be nonsecure random:
		#It only needs to be semi-unique, not secret.
		ID = randomsource.getNonSecureRandom(8).encode("hex")

		#Token must be secure random
		token = randomsource.getSecureRandom(32)

		suggestedMeetingPoints = \
			[mp.ID for mp in self.routingContext.meetingPoints] + \
			self.settings.externalMeetingPoints

		newPayee = paylink.Payee(
			self.context, self.routingContext, ID, amount, receipt, token,
			suggestedMeetingPoints)
		self.payees.append(newPayee)

		return "amikopay://%s/%s" % \
			(self.settings.getAdvertizedNetworkLocation(), ID)


	def pay(self, URL, linkname=None):
		"""
		Start paying a payment.

		Arguments:
		URL     : The URL of the payment request
		linkname: If not equal to None, payment routing is restricted to the
		          link with the given name.

		Return value:
		A "payer" object, with the following attributes:
			amount : The amount (integer, in Satoshi) to be paid
			receipt: A receipt for the payment
		"""

		newPayer = self.__pay(URL, linkname) #implemented in Node thread
		newPayer.waitForReceipt() #Must be done in this thread
		return newPayer


	@runInNodeThread
	def __pay(self, URL, linkname=None):
		rc = self.routingContext
		if linkname != None:
			rc = RoutingContext()
			rc.links = \
				[lnk for lnk in self.routingContext.links if lnk.name == linkname]
			if len(rc.links) == 0:
				raise Exception("There is no link with that name")

		newPayer = paylink.Payer(self.context, rc, URL)
		return newPayer


	def confirmPayment(self, payer, payerAgrees):
		"""
		Finish or cancel paying a payment.

		Arguments:
		payer      : A "payer" object as returned by the pay() method
		payerAgrees: Boolean, indicating whether or not the user agrees to pay
		"""

		self.__confirmPayment(payer, payerAgrees) #implemented in Node thread
		payer.waitForFinished() #Must be done in this thread
		self.payLog.writePayer(payer)


	@runInNodeThread
	def __confirmPayment(self, payer, payerAgrees):
		payer.confirmPayment(payerAgrees)


	@runInNodeThread
	def list(self):
		"""
		Return value:
		A data structure, containing a summary of objects present in this
		Amiko node.
		"""

		return self.__getState(forDisplay=True)


	@runInNodeThread
	def getBalance(self):
		"""
		Return value:
		Dictionary, containing different balances
		(integer, in Satoshi).
		"""

		balances = [{"bitcoin": self.bitcoind.getBalance()}]

		for lnk in self.routingContext.links:
			balances.append(lnk.getBalance())

		ret = {}
		for b in balances:
			for k,v in b.iteritems():
				try:
					ret[k] += v
				except KeyError:
					ret[k] = v

		return ret


	@runInNodeThread
	def makeLink(self, localName, remoteURL=""):
		remoteID = ""
		if remoteURL != "":
			URL = urlparse(remoteURL)
			remoteID = URL.path[1:]
		state = \
		{
            "channels": [],
            "localID": localName, #TODO: is this different from name???
            "name": localName,
            "openTransactions": [],
            "remoteID": remoteID,
            "remoteURL": remoteURL
		}
		newLink = link.Link(
			self.context, self.routingContext, self.bitcoind,
			self.settings, state)
		self.routingContext.links.append(newLink)

		self.context.sendSignal(None, event.signals.save)
		return newLink.localURL


	@runInNodeThread
	def deposit(self, linkname, amount):
		"""
		Deposit into a link.

		Arguments:
		linkname: the name of the link
		amount: the amount (integer, Satoshi) to be deposited
		"""

		#Always default to the first escrow key. TODO: allow the user to
		#choose a different one.
		if len(self.settings.acceptedEscrowKeys) == 0:
			raise Exception("There are no escrow provider keys defined. "
				"Please edit your settings first.")
		escrowKey = self.settings.acceptedEscrowKeys[0]

		links = \
			[lnk for lnk in self.routingContext.links if lnk.name == linkname]
		if len(links) == 0:
			raise Exception("There is no link with that name")

		links[0].deposit(amount, escrowKey)


	@runInNodeThread
	def withdraw(self, linkname, channelID):
		"""
		Withdraw from a link.

		Arguments:
		linkname: the name of the link
		channelID: the channel ID of the channel to be withdrawn
		"""

		links = \
			[lnk for lnk in self.routingContext.links if lnk.name == linkname]
		if len(links) == 0:
			raise Exception("There is no link with that name")
		links[0].withdraw(channelID)


	def run(self):
		"""
		The thread function.

		Intended for internal use by Node.
		Not intended to be part of the API.
		"""

		log.log("\n\nAmiko thread started")

		#Start listening
		listener = network.Listener(self.context,
			self.settings.listenHost, self.settings.listenPort)

		#TODO: (re-)enable creation of new transactions

		self.__stop = False
		while True:

			self.context.dispatchNetworkEvents()
			self.context.dispatchTimerEvents()
			self.watchdog.check()

			with self._commandFunctionLock:
				s = self._commandFunction
				if s != None:
					try:
						self._commandReturnValue = s[0](self, *s[1], **s[2])
					except Exception as e:
						self._commandReturnValue = e
						log.logException()
					self._commandProcessed.set()
					self._commandFunction = None

			if self.__doSave:
				self.__saveState()
				self.__doSave = False

			self.__movePayeesToPayLog()

			if self.__stop:
				#TODO: stop creation of new transactions
				#TODO: only break once there are no more open transactions
				break

		#This closes all network connections etc.
		self.context.sendSignal(None, event.signals.quit)

		log.log("Node thread terminated\n\n")


	def __loadState(self):

		oldFile = self.settings.stateFile + ".old"
		if os.access(oldFile, os.F_OK):
			if os.access(self.settings.stateFile, os.F_OK):
				#Remove old file if normal state file exists:
				os.remove(oldFile)
			else:
				#Use old file if state file does not exist:
				os.rename(oldFile, self.settings.stateFile)

		try:
			with open(self.settings.stateFile, 'rb') as fp:
				state = json.load(fp)
				#print state
		except IOError:
			log.log("Failed to load from %s" % self.settings.stateFile)
			log.log("Starting with empty state")
			state = {"links":[], "meetingPoints":[]}


		for lnk in state["links"]:
			self.routingContext.links.append(link.Link(
				self.context, self.routingContext, self.bitcoind,
				self.settings, lnk))

		for mp in state["meetingPoints"]:
			self.routingContext.meetingPoints.append(
				meetingpoint.MeetingPoint(str(mp["ID"])))

		#TODO: process requests


	def __saveState(self):
		state = self.__getState(forDisplay=False)

		#ensure_ascii doesn't seem to do what I expected,
		#so it becomes required that state is ASCII-only.
		state = json.dumps(state, sort_keys=True, ensure_ascii=True,
			indent=4, separators=(',', ': '))

		#print state

		newFile = self.settings.stateFile + ".new"
		log.log("Saving in " + newFile)
		with open(newFile, 'wb') as fp:
			fp.write(state)

		oldFile = self.settings.stateFile + ".old"

		#Replace old data with new data
		os.rename(self.settings.stateFile, oldFile)
		os.rename(newFile, self.settings.stateFile)
		os.remove(oldFile)


	def __getState(self, forDisplay=False):
		ret = self.routingContext.getState(forDisplay)
		ret["requests"] = [p.getState(forDisplay) for p in self.payees]
		return ret


	def __movePayeesToPayLog(self):
		"Writes finished payee objects to pay log and then removes them"

		doSave = False

		for p in self.payees[:]: #copy of list, since the list will be modified
			if p.state in [p.states.cancelled, p.states.committed]:
				self.payLog.writePayee(p)
				self.payees.remove(p)
				doSave = True

		if doSave:
			self.__saveState()


	def __handleLinkSignal(self, connection, message):
		for lnk in self.routingContext.links:
			if lnk.localID == message.ID:
				lnk.connect(connection, message)
				return

		log.log("Received link message with unknown ID")
		connection.close()


	def __handlePaySignal(self, connection, message):
		for p in self.payees:
			if p.ID == message.value:
				p.connect(connection)
				return

		log.log("Received pay message with unknown ID")
		connection.close()


	def __handleSaveSignal(self):
		log.log("Save handler called")
		self.__doSave = True


	def __postHandleMessageSignal(self, message):
		#log.log("Message post-handler called: " + str(message))

		if self.__doSave:
			self.__saveState()
			self.__doSave = False


