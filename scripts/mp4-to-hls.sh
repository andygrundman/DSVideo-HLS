#!/bin/bash
#
# Usage: mp4-to-hls.sh /path/to/video.mp4 /path/to/playlist.m3u8

# should be run from index.cgi

# Delete old files if they're this old
REMOVE_AFTER=10

nice -n 19 /volume1/web/hls/bin/ffmpeg -y -loglevel info -hide_banner -i "$1" \
    -vcodec copy -acodec copy -bsf:v h264_mp4toannexb -bsf:a aac_adtstoasc \
    -hls_flags single_file \
    -hls_time 10 \
    -hls_playlist_type event \
    -hls_list_size 0 \
    -hls_allow_cache 0 \
    "$2"

# Might as well use this script to cleanup old files too!
# XXX find a better way to schedule this
find /volume1/web/hls/cache -mtime +${REMOVE_AFTER} -exec rm {} \;
