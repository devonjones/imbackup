Presently works with libpurple logs (Pidgin, Finch, possibly Adium, I don't know, I don't have a Mac).
Uploads the logs one by one to your imap server specified by the file ~/.imbackup/config (look at config.example).  imbackup is intended to run from cron.

So far this has only been tested on Ubuntu/Linux Mint, and against xithe dovecot IMAP server (www.dovecot.org/).

**Requirements:**

* BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
* dateutil: http://labix.org/python-dateutil

**Ubuntu Setup:**

    sudo apt-get install python-beautifulsoup python-dateutil

**Setup:**

Create ~/.imbackup/config with the following contents:

    login: [imap username]
    password: [imap password]
    server: [address of imap host]
    port: [imap server's port] [optional, default 143, 993 if ssl = true]
    ssl: [true or false] [optional, default false]

Run imbackup:

    cd imbackup/bin
    ./imbackup.py

**TODO**

* add foldername to config (right now defaults to imbackup)
* add all config values as command line arguments
* test on other IMAP servers
* test on adium's logs
