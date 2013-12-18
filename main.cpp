/*
    main.cpp
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

#include <cstdio>

#include <openssl/ssl.h>
#include <openssl/err.h>

#include "exception.h"
#include "log.h"
#include "cthread.h"

#include "conffile.h"
#include "commandlineparams.h"
#include "amiko.h"
#include "timer.h"
#include "key.h"
#include "version.h"
#include "paylink.h"

CString getInput(CString question="")
{
	printf("%s", question.c_str());
	CString ret;
	while(true)
	{
		char c = getchar();
		if(c == '\n') break;
		ret += c;
	}
	return ret;
}


void app(const std::vector<CString> &arguments)
{
	CCommandlineParams commandline(arguments);

	CString conffilename = commandline.getValue(
		"files", "conffile", "amikopay.conf");

	CAmikoSettings settings;
	settings.loadFrom(CConfFile(conffilename));
	settings.loadFrom(commandline); //overrides settings from conffile
	CAmiko amiko(settings);
	amiko.start();

	//Wait some time to allow initialization to finish
	CTimer::sleep(1000);

	printf(
		"\n"
		"\n"
		"Amiko Pay " AMIKO_VERSION " Copyright (C) 2013 - " AMIKO_LASTCOPYRIGHTYEAR "\n"
		"\n"
		"Amiko Pay is free software: you can redistribute it and/or modify\n"
		"it under the terms of the GNU General Public License as published by\n"
		"the Free Software Foundation, either version 3 of the License, or\n"
		"(at your option) any later version.\n"
		"\n"
		"Amiko Pay is distributed in the hope that it will be useful,\n"
		"but WITHOUT ANY WARRANTY; without even the implied warranty of\n"
		"MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the\n"
		"GNU General Public License for more details.\n"
		"\n"
		"You should have received a copy of the GNU General Public License\n"
		"along with Amiko Pay. If not, see <http://www.gnu.org/licenses/>.\n"
		"\n"
		"Enter \"help\" for a list of commands.\n"
		);

#define CHECKNUMARGS(n) \
	if(splitInput.size() < ((n)+1)) \
	{ \
		printf("Error: setRemoteURI requires %ld arguments; %ld given\n", \
			long(n), long(splitInput.size())-1); \
		continue; \
	}


	while(true)
	{
		CString input = getInput("> ");

		std::vector<CString> splitInput = input.split(' ', true);
		if(splitInput.size() == 0) continue;

		if(splitInput[0] == "quit" || splitInput[0] == "exit")
		{
			break;
		}
		else if(splitInput[0] == "pay")
		{
			CHECKNUMARGS(1)
			CString paymentURL = splitInput[1];
			CPayLink link(CURI(paymentURL));
			//TODO: implement payment
		}
		else if(splitInput[0] == "newlink")
		{
			CString remoteURI;
			if(splitInput.size() >= 2)
				remoteURI = splitInput[1];

			CString localURI = amiko.makeNewLink(remoteURI);
			printf("%s\n", localURI.c_str());
		}
		else if(splitInput[0] == "setremoteuri")
		{
			CHECKNUMARGS(2)
			amiko.setRemoteURI(splitInput[1], splitInput[2]);
		}
		else if(splitInput[0] == "listlinks")
		{
			std::vector<CAmiko::CLinkStatus> list = amiko.listLinks();
			for(size_t i=0; i < list.size(); i++)
			{
				CAmiko::CLinkStatus &status = list[i];

				printf("link %ld:\n", long(i+1));
				printf("  local address: %s\n",
					getBitcoinAddress(status.m_localKey).c_str());
				printf("  local URI: \"%s\"\n",
					status.m_localURI.c_str());
				printf("  remote URI: \"%s\"\n",
					status.m_remoteURI.c_str());
				printf("  completed: %s\n",
					status.m_completed ? "true" : "false");
				printf("  connected: %s\n",
					status.m_connected ? "true" : "false");
			}
		}
		else if(splitInput[0] == "newkey")
		{
			CKey key;
			key.makeNewKey();

			printf("localPrivateKey = %s\n", key.getPrivateKey().hexDump().c_str());
			printf("remoteURI = %s\n", amiko.getSettings().getLocalLinkURL(key).c_str());
			printf("remotePublicKey = %s\n", key.getPublicKey().hexDump().c_str());
		}
		else if(splitInput[0] == "help")
		{
			printf(
				"exit:\n"
				"quit:\n"
				"  Terminate application.\n"
				"help:\n"
				"  Display this message.\n"
				"pay [paymentURL]:\n"
				"  Perform the payment indicated by paymentURL.\n"
				"newlink [remoteURI]:\n"
				"  Create a new link, and optionally provide it with the link\n"
				"  URI of the remote party.\n"
				"  Returns the local URI, which can be given to the remote user.\n"
				"setremoteuri localAddress remoteURI:\n"
				"  Sets the remote URI of the link with the given local address.\n"
				"listlinks\n"
				"  List all links and their status\n"
				"newkey:\n"
				"  Make a new key pair and display its properties.\n"
				);
		}
		else
		{
			printf("Unrecognized command \"%s\"\n", splitInput[0].c_str());
		}
	}

	amiko.stop();
}


int main(int argc, char **argv)
{
	try
	{
		SSL_load_error_strings();
		SSL_library_init();
		COpenSSLMutexes openSSLMutexes;

		std::vector<CString> arguments;
		if(argc > 1)
			for(int i=1; i<argc; i++)
				arguments.push_back(CString(argv[i]));

		app(arguments);

		ERR_free_strings();

		log("Successful exit\n");
		return 0;
	}
	catch(CException &e)
	{
		log(CString::format("Caught application exception: %s\n", 256, e.what()));
		return 1;
	}
	catch(std::exception &e)
	{
		log(CString::format("Caught standard library exception: %s\n", 256, e.what()));
		return 2;
	}
}

