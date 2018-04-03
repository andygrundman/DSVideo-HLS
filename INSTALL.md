Warning: follow these instructions at your own risk! You should be comfortable using root 
on your DiskStation and know your way around a Linux system and how to recover if things go wrong.

## Synology Packages

Install the following packages using the Synology Package Center:

* Video Station
* Web Station
* Perl

Create a directory at /volume1/web/hls where the web application will run.

## Web configuration:

Create a web share with an hls directory inside it. The path to this should be
/volume1/web/hls

This should be accessible at http://your_diskstation/hls/

## Database access configuration:

To allow a Perl script to connect to the Postgres database on the system, you must edit the file
/etc/postgresql/pg_hba.conf as root. Unfortunately, this file must be edited after each DSM upgrade.
Enable SSH access and then run:

    $ ssh admin@diskstation
      <enter admin password>
    $ sudo su -
      <enter admin password again>
    $ echo "host    all             all             127.0.0.1/32            trust" >> /etc/postgresql/pg_hba.conf
    $ synoservice --restart pgsql

## Web app installation

Copy all files, including empty directories, to /volume1/web/hls.

The bin directory will contain FFmpeg (next step).
The cache directory will store transcoded video files.
The images directory will contain copies of video thumbnails from Video Station.

Your DSM login information is needed so that the app can use the Synology web API.
Edit index.conf and enter your login and password:

    dsm_login admin
    dsm_pass your_password_here

Make the CGI script executable and test that it doesn't contain any errors:

    $ ssh admin@diskstation
      <enter admin password>
    $ cd /volume1/web/hls
    $ chmod 0755 index.cgi
    $ perl -wc index.cgi
    index.cgi syntax OK

## FFmpeg

The version of FFmpeg in the community package area doesn't support HLS. You can obtain a Linux x86_64 static binary
that does from https://www.johnvansickle.com/ffmpeg/

Download the latest ffmpeg-git-64bit-static.tar.xz and extract the contents to the /volume1/web/hls/bin directory.

    $ cd /volume1/web/hls/bin
    $ wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-64bit-static.tar.xz
    $ tar -xvf ffmpeg-git-64bit-static.tar.xz
    $ cp ffmpeg-git-*/ffmpeg .
    $ chmod 0755 ffmpeg
    $ ./ffmpeg -version

## Test transcoding

Test FFmpeg transcoding by running the mp4-to-hls.sh script on one of your video files.

    $ chmod 0755 scripts/mp4-to-hls.sh
    $ scripts/mp4-to-hls.sh /volume1/video/path/to/video.mp4 test.m3u8

This should create two files in the current directory, test.m3u8 and test.ts. The test.m3u8 file contains pointers into the
ts files in ~10-second chunks. If this transcode completes without errors, you can delete these two files.

## Access the website

The first time you access the website, video thumbnails are retrieved from Video Station and the page may
take a few seconds to appear.

If the page doesn't work or there are any errors, check the following log file for help:

/var/log/upstart/pkg-WebStation-fcgiwrap.log
