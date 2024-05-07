#!/bin/bash
bash /kind/restore-tmpfs.sh
/usr/local/bin/entrypoint /sbin/init
/bin/bash