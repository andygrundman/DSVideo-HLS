DSVideo-HLS is a lightweight MP4-to-HLS video transcoding web app for Intel-based Synology DiskStation systems.

After a short one-time transcoding process, a video can be played in S browser that supports HTML5
video without needing to use the large Video Station app or webpage. My primary use case is for watching
videos in a picture-in-picture window on iPad while using other applications.

## Installation

Please see the [INSTALL](INSTALL.md) file for installation instructions. This requires root SSH access and
general Linux knowledge, so consider yourself warned.

## Features

* Simple web view of recent MP4 videos added to Video Station.
* Playback starts at current progress point and progress is synced back to the Video Station database.
* ffmpeg transcoding to single-file HLS .ts/.m3u8 format, with progress bar
* Original video's quality is maintained.
* Tested browsers:
    * Mac Safari
    * iOS Safari
    * PC/Mac Chrome
    * Edge

## Limitations

* Only supports videos from the "Home Videos" section of Video Station.
* Requires a 64-bit Intel DiskStation.

## Future Enhancement Ideas

* Auto-delete videos after finishing.
* Re-encoding options for lower quality, resolution, etc.
* Improved web UI with sorting, searching, movie/TV show collections, etc.
* ARM platform support.
* Packaging and/or easier install without root/ssh access.

## Author

[Andy Grundman](andy@hybridized.org)

## License

This project is licensed under the [MIT license](LICENSE).

The below 3rd party components are available under their respective licenses.

## 3rd party components

[CGI.pm](https://metacpan.org/release/CGI)
[DBD::Pg](https://metacpan.org/release/DBD-Pg)
[Proc::Reliable](https://metacpan.org/release/Proc-Reliable)
[jQuery 2.2.4](https://jquery.com)
[jQuery blockUI plugin 2.70.0-2014.11.23](http://malsup.com/jquery/block/)
[hls.js JavaScript HLS client](https://github.com/video-dev/hls.js/)
