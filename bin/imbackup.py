#!/usr/bin/python

#import getpass, time
#from email.MIMEMultipart import MIMEMultipart
#from email.MIMEMessage import MIMEMessage
#from email.Charset import Charset

import sys
import os
import imaplib
import sqlite3
import time
from base64 import encodestring
from email.Message import Message
from email.Utils import formatdate
from BeautifulSoup import BeautifulSoup
from datetime import datetime
from dateutil.parser import parse
from optparse import OptionParser

# Processing timeout in seconds
TIMEOUT = 30

def split_filename(filename):
	parts = filename.split('/')
	sdate = parts.pop()
	dparts = sdate.split(".")
	msg_format = dparts.pop()

	if msg_format in ('htm', 'html'):
		msg_format = 'text/html'
	elif msg_format in ('txt'):
		msg_format = 'text/plain'
	elif msg_format in ('gif'):
		msg_format = 'image/gif'
	elif msg_format in ('jpg', 'jpeg'):
		msg_format = 'image/jpeg'
	elif msg_format in ('png'):
		msg_format = 'image/png'
	else:
		msg_format = 'application/octet-stream'
	
	if msg_format in ('text/html', 'text/plain'):
		sdate = dparts[0] + " " + dparts[1][0:2] + ":" + dparts[1][2:4] + ":" + dparts[1][4:6] + " " + dparts[1][11:14]
		msg_date = parse(sdate)
	else:
		mtime = os.path.getmtime(filename)
		msg_date = datetime.fromtimestamp(mtime)
	msg_from = parts.pop()
	msg_to = parts.pop()
	protocol = parts.pop()
	if msg_to.find("@") == -1:
		msg_to += "@%s" % protocol
	if msg_from.find("@") == -1:
		msg_from += "@%s" % protocol
	return protocol, msg_format, msg_to, msg_from, msg_date

def get_text_body(filename):
	fh = open(filename, 'r')
	data = fh.readlines()
	fh.close()
	return data

def get_binary_body(filename):
	data = []
	with open(filename, 'r') as fh:
		data.append(fh.read())
	return data

def get_subject(msg_format, body):
	for line in body:
		if line.find(':') > -1 and line.find("Conversation with") == -1:
			if msg_format == 'text/html':
				soup = BeautifulSoup(line)
				soup.contents[0].extract()
				text = ''.join(soup.findAll(text=True))
				return text.strip()
			else:
				return line.split(':', 1)[1].strip()
	return ""

def update_message(imap, filename):
	remove_message(imap, filename)
	msg = generate_message(imap, filename)
	send_message(imap, msg)

def create_message(imap, filename):
	msg = generate_message(imap, filename)
	send_message(imap, msg)

def remove_message(imap, filename):
	protocol, msg_format, msg_to, msg_from, msg_date = split_filename(filename)
	msg_id = create_id(msg_date, msg_from)
	result, msg_nums = imap.search(None, 'HEADER', 'MESSAGE-ID', msg_id)
	for msg_num in msg_nums:
		imap.store(msg_num, '+FLAGS', '\\Deleted')
	imap.expunge()

def generate_message(imap, filename):
	protocol, msg_format, msg_to, msg_from, msg_date = split_filename(filename)
	msg_subject = ''
	if msg_format in ('text/html', 'text/plain'):
		msg_body = get_text_body(filename)
		msg_subject = get_subject(msg_format, msg_body)
	else:
		msg_body = get_binary_body(filename)
		msg_subject = filename.split('/').pop()
	return construct_message(imap, msg_format, msg_to, msg_from, msg_date, msg_subject, msg_body)

def create_id(msg_date, msg_from):
	return str(time.mktime(msg_date.timetuple())) + msg_from + '@localhost.localdomain'

def construct_message(imap, msg_format, msg_to, msg_from, msg_date, msg_subject, msg_body):
	msg = Message()
	msg.add_header('Date', formatdate(time.mktime(msg_date.timetuple())))
	msg.add_header('Message-Id', create_id(msg_date, msg_from))
	msg.add_header('To', msg_to)
	msg.add_header('From', msg_from)
	msg.add_header('MIME-Version', '1.0')
	msg.add_header('Subject', msg_subject)
	payload = Message()
	payload.add_header('Content-Type', msg_format)
	if msg_format in ('text/html', 'text/plain'):
		payload.add_header('Content-Transfer-Encoding', '8bit')
		payload.set_payload(''.join(msg_body))
	else:
		payload.add_header('Content-Transfer-Encoding', 'base64')
		payload.add_header('Content-Disposition', 'attachment; filename="%s"' % msg_subject)
		payload.set_payload(encodestring(''.join(msg_body)).decode())
	for item in payload.items():
		msg.add_header(item[0], item[1])
		msg.set_payload(payload.get_payload())
	try:
		msg.as_string()
	except Exception, e:
		print e
	return msg

def send_message(imap, msg):
	path = "imbackup"
	imap.append(path, None, None, msg.as_string())

def update_file_in_db(curs, filename, mtime_ms):
	sql = ''.join([
		"UPDATE file_last_update",
		" SET last_update_ms = ?",
		" WHERE filename = ?"])
	curs.execute(sql, (mtime_ms, filename))

def add_file_to_db(curs, filename, mtime_ms):
	sql = ''.join([
		"INSERT INTO file_last_update",
		" (filename, last_update_ms)",
		" VALUES",
		" (?, ?)"])
	curs.execute(sql, (filename, mtime_ms))

def check_file_in_db(curs, filename):
	sql = ''.join([
		"SELECT *",
		" FROM file_last_update",
		" WHERE filename = ?"])
	curs.execute(sql, (filename,))
	return curs.fetchone()

def visit(arg, dirname, names):
	conn, curs, imap, verbose = arg
	if len(names) > 0 and os.path.isfile(dirname + "/" + names[0]):
		for name in names:
			filename = dirname + "/" + name
			pieces = dirname.split("/")
			mtime_ms = int(os.path.getmtime(filename) * 1000)
			rec = check_file_in_db(curs, filename)
			if not rec:
				create_message(imap, filename)
				add_file_to_db(curs, filename, mtime_ms)
				conn.commit()
				if verbose:
					print "Added %s" % filename
			elif rec[2] < mtime_ms:
				update_message(imap, filename)
				update_file_in_db(curs, filename, mtime_ms)
				conn.commit()
				if verbose:
					print "Updated: %s" % filename
			else:
				pass

def process_files(conn, imap, verbose):
	curs = conn.cursor()
	try:
		os.path.walk(os.path.expanduser("~/.purple/logs"), visit, (conn, curs, imap, verbose))
	finally:
		curs.close()

def get_imap_handle(imapconfig):
	try:
		ssl = False
		port = imapconfig.get('port')
		if imapconfig.has_key('ssl'):
			if imapconfig['ssl'] == 'true':
				ssl = True
		if ssl:
			if not port:
				port = 993
			imap = imaplib.IMAP4_SSL(imapconfig['server'])
		else:
			if not port:
				port = 143
			imap = imaplib.IMAP4(imapconfig['server'])
		imap.login(imapconfig['login'], imapconfig['password'])
	except Exception, e:
		print("IMAP on fire eh?")
		exit(-1)
	return imap

def setup_imap_server(imap):
	path = "imbackup"
	create_imap_path(imap, path, subscribe=True)
	imap.select(path)

def create_imap_path(imap, folder, subscribe=True):
	response = imap.list(folder)
	if(response[1][0] == None):
		response = imap.create(folder)
		if(response[0] == "No"):
			raise Exception, response[1][0]
		if subscribe:
			response = imap.subscribe(folder)
			if(response[0] == "No"):
				raise Exception, response[1][0]

def get_db_connection():
	conn = sqlite3.connect(os.path.expanduser("~/.imbackup/state.db"))
	curs = conn.cursor()
	try:
		ver = create_db_v_1(conn, curs)
		ver = create_db_v_2(conn, curs, ver)
	finally:
		curs.close()
	return conn

def check_db_version(curs):
	sql = ''.join([
		"SELECT MAX(version)",
		" FROM database_version"])
	curs.execute(sql)
	row = curs.fetchone()
	return row[0]

def set_version(curs, ver):
	sql = ''.join([
		"INSERT INTO database_version",
		" (version)",
		" VALUES (?)"])
	curs.execute(sql, (str(ver), ))

def create_db_v_1(conn, curs):
	sql = ''.join([
		"CREATE TABLE IF NOT EXISTS database_version(",
		"  id INTEGER PRIMARY KEY,",
		"  version INTEGER)"])
	curs.execute(sql)
	ver = check_db_version(curs)
	if not ver:
		ver = 1
		set_version(curs, ver)
	conn.commit()
	return ver

def create_db_v_2(conn, curs, ver):
	if ver >= 2:
		return ver
	ver = 2
	sql = ''.join([
			"CREATE TABLE file_last_update(",
			"  id INTEGER PRIMARY KEY,",
			"  filename TEXT,",
			"  last_update_ms INTEGER)"])
	curs.execute(sql)
	set_version(curs, ver)
	conn.commit()
	return ver

def main():
	parser = optionParser()
	(options, args) = parser.parse_args()

	config = {}
	try:
		config = read_config()
	except IOError, e:
		print "Error locating config file."

	if(not config.has_key('login') or not config.has_key('password') or not config.has_key('server')):
		print "Error in config file.  Please ensure user, password, and server are defined."
		print "File should be located at %s/.imbackup/config and should resemble:" % os.path.expanduser("~")
		print "login: username"
		print "password: iforgot"
		print "server: imap.domain.com"
		return(-1)

	conn = get_db_connection()
	imap = get_imap_handle(config)
	setup_imap_server(imap)
	process_files(conn, imap, options.verbose)
	return(0)

def read_config():
	"""Read the user's configuration file"""
	configlines = open(os.path.expanduser("~") +  "/.imbackup/config").readlines()
	config = {}
	for line in configlines:
		line = line.split("#")[0] # Strip comments
		if(line.find(":") >= 0):
			(key, value) = line.split(":")
			config[key.strip()] = value.strip()
	return config

def optionParser():
	usage = "usage: %prog [options]\nTakes instant messaging logs and stores them in an imap server in the folder imbackup.  Will update the stored messages if a log gets appended to between runs."
	parser = OptionParser(usage=usage)
	parser.add_option("-v", "--verbose", action="store_true", dest="verbose", help="Verbose")
	parser.set_defaults(verbose = False)
	return parser

if __name__ == "__main__":
	sys.exit(main())
