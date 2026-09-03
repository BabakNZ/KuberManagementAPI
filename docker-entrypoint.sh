#!/bin/sh
set -e

rm -f /tmp/prometheus/*

exec "$@"