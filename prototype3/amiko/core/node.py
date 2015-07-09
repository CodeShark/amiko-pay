#    node.py
#    Copyright (C) 2015 by CJP
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

import randomsource

import link
import payeelink
import payerlink
import meetingpoint
import transaction

import serializable



class PaymentRequest(serializable.Serializable):
	serializableAttributes = {'amount':0, 'receipt':''}
serializable.registerClass(PaymentRequest)


class MakePayer(serializable.Serializable):
	serializableAttributes = {}
serializable.registerClass(MakePayer)


class ReturnValue(serializable.Serializable):
	serializableAttributes = {'value':''}
serializable.registerClass(ReturnValue)



class Node(serializable.Serializable):
	serializableAttributes = \
	{
	'links':{},
	'payeeLinks':{},
	'payerLink': None,
	'meetingPoints':{},
	'transactions':{}
	}


	def handleMessage(self, msg):
		return \
		{
		PaymentRequest: self.msg_request,
		MakePayer: self.msg_makePayer,
		payeelink.Pay: self.msg_passToPayee,
		payerlink.Timeout: self.msg_passToPayer,
		payerlink.Receipt: self.msg_passToPayer,
		payerlink.Confirm: self.msg_passToPayer
		}[msg.__class__](msg)


	def msg_request(self, msg):
		#ID can be nonsecure random:
		#It only needs to be semi-unique, not secret.
		requestID = randomsource.getNonSecureRandom(8).encode("hex")

		#Token must be secure random
		token = randomsource.getSecureRandom(32)

		newPayeeLink = payeelink.PayeeLink(
			amount=msg.amount, receipt=msg.receipt, token=token)

		self.payeeLinks[requestID] = newPayeeLink

		#Returned messages:
		return [(None, ReturnValue(value=requestID))]


	def msg_makePayer(self, msg):
		if not (self.payerLink is None):
			raise Exception("There already is a payment in progress")
		self.payerLink = payerlink.PayerLink()

		#Returned messages:
		return [
			(5.0, self.payerLink.getTimeoutMessage())  #Add time-out for payer
			]


	def msg_passToPayee(self, msg):
		payee = self.payeeLinks[msg.ID]
		return payee.handleMessage(msg)


	def msg_passToPayer(self, msg):
		if self.payerLink is None:
			raise Exception("Received message for payer, but there is no payer")
		return self.payerLink.handleMessage(msg)


serializable.registerClass(Node)

