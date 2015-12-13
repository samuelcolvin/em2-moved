#!/bin/sh
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS em2"
psql -h localhost -U postgres -c "CREATE DATABASE em2"
