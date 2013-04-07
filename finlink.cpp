/*
    finlink.cpp
    Copyright (C) 2013 by CJP

    This file is part of Amiko Pay.

    Amiko Pay is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Amiko Pay is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Amiko Pay. If not, see <http://www.gnu.org/licenses/>.
*/

#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>

#include <cstdio>

#include "log.h"
#include "bitcoinaddress.h"
#include "messages.h"
#include "file.h"
#include "pointerowner.h"

#include "finlink.h"

//TODO: make this a setting:
#define LINKSDIR "./links/"

#define LINKFILE_FORMAT_VERSION 1


CFinLink::CFinLink(const CAmikoSettings::CLink &linkInfo) :
	m_LocalKey(linkInfo.m_localKey),
	m_RemoteKey(linkInfo.m_remoteKey),
	m_Filename(CString(LINKSDIR) + getBitcoinAddress(m_LocalKey))
{
	try
		{CFile::makeDirectory(LINKSDIR);}
	catch(CFile::CError &e)
	{
		log(CString(e.what()) + "\n");
	}

	load();

	//To make sure we can save, we try it once here:
	save();
}


CFinLink::~CFinLink()
{
	//Should already be saved; just do it one final time just to be sure
	try
	{
		save();
	}
	catch(CSaveError &e)
	{
		log(CString::format("An error occurred during final save: %s\n",
			1024, e.what()
			));
	}
}


void CFinLink::sendMessage(const CBinBuffer &message)
{
	CMutexLocker lock(m_Inbox);
	m_Inbox.m_Value.push(message);
}


void CFinLink::load()
{
	CMutexLocker lock(m_Filename);

	CFile f(m_Filename.m_Value, "rb");
	if(f.m_FP == NULL)
	{
		log(CString::format("Could not load %s; assuming this is a new link\n",
			256, m_Filename.m_Value.c_str()));
		return;
	}

	CBinBuffer data, chunk;
	chunk.resize(1024);
	while(true)
	{
		size_t ret = fread(&chunk[0], 1, chunk.size(), f.m_FP);
		if(ret < chunk.size())
		{
			//TODO: distinguish between EOF and error
			chunk.resize(ret);
			data.appendRawBinBuffer(chunk);
			break;
		}
		data.appendRawBinBuffer(chunk);
	}

	deserialize(data);
}


void CFinLink::save()
{
	CMutexLocker lock(m_Filename);

	CString tmpfile = m_Filename.m_Value + ".tmp";

	//Save as tmpfile
	{
		CBinBuffer data = serialize();

		//TODO: use tmp file to prevent overwriting with unfinished data
		CFile f(tmpfile, "wb");
		if(f.m_FP == NULL)
			throw CSaveError(CString::format("ERROR: Could not store %s!!!",
				256, tmpfile.c_str()
				));

		size_t ret = fwrite(&data[0], data.size(), 1, f.m_FP);
		if(ret != 1)
			throw CSaveError(CString::format("ERROR while storing in %s!!!",
				256, tmpfile.c_str()
				));
	}

	//Overwrite file in m_Filename with tmpfile
	try
	{
		CFile::rename(tmpfile, m_Filename.m_Value);
	}
	catch(CFile::CError &e)
	{
		throw CSaveError(CString::format(
			"ERROR while storing in %s; new data can be found in %s!!!",
			1024, m_Filename.m_Value.c_str(), tmpfile.c_str()
			));
	}
}


CBinBuffer CFinLink::serialize() const
{
	CBinBuffer ret;

	//Format version
	ret.appendUint<uint32_t>(LINKFILE_FORMAT_VERSION);

	//My messages
	ret.appendUint<uint32_t>(m_myMessages.size());
	for(std::list<CBinBuffer>::const_iterator i=m_myMessages.begin();
		i != m_myMessages.end(); i++)
			ret.appendBinBuffer(*i);

	//Your messages
	ret.appendUint<uint32_t>(m_yourMessages.size());
	for(std::list<CBinBuffer>::const_iterator i=m_yourMessages.begin();
		i != m_yourMessages.end(); i++)
			ret.appendBinBuffer(*i);

	//TODO: transactions

	return ret;
}


void CFinLink::deserialize(const CBinBuffer &data)
{
	try
	{
		size_t pos = 0;
		uint32_t formatVersion = data.readUint<uint32_t>(pos);
		if(formatVersion != LINKFILE_FORMAT_VERSION)
			throw CLoadError("File format version mismatch");

		uint32_t numMessages = data.readUint<uint32_t>(pos);
		//TODO: check whether numMessages makes sense
		for(uint32_t i=0; i < numMessages; i++)
			m_myMessages.push_back(data.readBinBuffer(pos));

		numMessages = data.readUint<uint32_t>(pos);
		//TODO: check whether numMessages makes sense
		for(uint32_t i=0; i < numMessages; i++)
			m_yourMessages.push_back(data.readBinBuffer(pos));

		//TODO: transactions
	}
	catch(CBinBuffer::CReadError &e)
	{
		throw CLoadError(CString(e.what()));
	}
}


void CFinLink::processInbox()
{
	CMutexLocker lock(m_Inbox);

	while(!m_Inbox.m_Value.empty())
	{
		CBinBuffer msgData = m_Inbox.m_Value.front();
		m_Inbox.m_Value.pop();

		CMessage *msg = NULL;
		try
		{
			msg = CMessage::constructMessage(msgData);
		}
		catch(CMessage::CSerializationError &e)
		{
			log(CString::format("Received incorrectly formatted message on %s: %s",
				1024,
				getBitcoinAddress(getLocalKey()).c_str(),
				e.what()
				));
			sendNackMessage(
				CNackMessage::eFormatError,
				"Message format error",
				CSHA256(msgData));

			//Ignore the incorrect message
			return;
		}

		//This object will take care of deleting msg:
		CPointerOwner<CMessage> messageOwner(msg);

		//TODO
		sendNackMessage(
			CNackMessage::eNonstandardReason,
			"Message receiving is not yet fully implemented",
			CSHA256(msgData));
	}
}


void CFinLink::sendNackMessage(
	CNackMessage::eReason reasonCode,
	const CString &reason,
	const CSHA256 &rejectedMessage)
{
	CNackMessage nack;
	nack.m_reasonCode = reasonCode;
	nack.m_reason = reason;
	nack.m_rejectedBySource = rejectedMessage;
	setOutboundMessageFields(nack);
	deliverMessage(nack.serialize());
}


void CFinLink::setOutboundMessageFields(CMessage &msg)
{
	msg.m_source = CRIPEMD160(
		CSHA256(getLocalKey().getPublicKey()).toBinBuffer()
		);
	msg.m_destination = CRIPEMD160(
		CSHA256(getRemoteKey().getPublicKey()).toBinBuffer()
		);

	msg.m_lastSentBySource = CSHA256(
		m_myMessages.empty()? CBinBuffer() : m_myMessages.back()
		);

	msg.m_lastAcceptedBySource = CSHA256(
		m_yourMessages.empty()? CBinBuffer() : m_yourMessages.back()
		);

	//TODO: timestamp

	msg.sign(getLocalKey());
}


