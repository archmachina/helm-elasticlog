#!/bin/bash

touch /usr/share/elasticsearch/config/users
touch /usr/share/elasticsearch/config/users_roles

/usr/share/elasticsearch/bin/elasticsearch-users useradd "$LOCALADMIN_USERNAME" -p "$LOCALADMIN_PASSWORD"
/usr/share/elasticsearch/bin/elasticsearch-users passwd "$LOCALADMIN_USERNAME" -p "$LOCALADMIN_PASSWORD" || exit 1
/usr/share/elasticsearch/bin/elasticsearch-users roles "$LOCALADMIN_USERNAME" -a superuser || exit 1
