#!/usr/bin/env perl

$| = 1;    # Unbuffered output

use strict;
use FindBin qw($Bin);
use lib "$Bin/lib";

# These modules are included with the Synology Perl package
use Cwd qw(abs_path);
use Data::Dumper qw(Dumper);
use DBI;
use File::Spec::Functions qw(catdir catfile);
use Filesys::Df;
use JSON::XS qw(encode_json decode_json);
use LWP::UserAgent;
use Template;
use Time::HiRes qw(time sleep);
use URI;
use URI::QueryParam;
use utf8;

# Additional modules loaded from the lib directory.
use CGI;
use CGI::Carp qw(fatalsToBrowser);
use DBD::Pg;
use Proc::Reliable;

use constant DB_NAME => 'video_metadata';
use constant DB_USER => 'postgres';
use constant DB_PASS => '';

use constant WORK_DIR        => '/volume1/web/hls/cache';
use constant SID_CACHE_FILE  => '/tmp/hls-session-id';
use constant IMAGE_CACHE_DIR => '/volume1/web/hls/images';
use constant HLS_CACHE_DIR   => '/volume1/web/hls/cache';

our $CONF = read_config_file('/volume1/web/hls/index.conf');

our $ua = LWP::UserAgent->new;

our $T;

# Main
my $q   = CGI->new;
my $out = {
    template => 'index.tt',
};

process_request( $q, $out );
render_output( $q, $out );

# End

sub _print_env {
    my $ret = '';

    foreach my $key ( sort keys %ENV ) {
        $ret .= "$key = $ENV{$key}\n";
    }

    return $ret;
}

sub _dbh {
    return DBI->connect_cached(
        "dbi:Pg:host=127.0.0.1;dbname=" . DB_NAME, DB_USER, DB_PASS,
        { AutoCommit => 0 }
    );
}

sub process_request {
    my ( $q, $out ) = @_;

    #$out->{debug} = _print_env();
    #$out->{debug} .= "\n" . Dumper($q) . "\n";

    if ( $q->param('action') eq 'transcode' ) {
        transcode_video( $q, $out );
    }
    elsif ( $q->param('action') eq 'transcode_progress' ) {
        transcode_progress( $q, $out );
    }
    elsif ( $q->param('action') eq 'play' ) {
        play_video( $q, $out );
    }
    elsif ( $q->param('action') eq 'delete' ) {
        delete_video( $q, $out );
    }
    elsif ( $q->param('action') eq 'update_watch' ) {
        update_watch( $q, $out );
    }
    else {
        # Display list of recently downloaded videos
        video_list( $q, $out );
    }
}

sub render_output {
    my ( $q, $out ) = @_;

    if ( my $redir = $out->{redirect} ) {
        print $q->redirect($redir);
    }
    elsif ( $out->{json} ) {
        print $q->header('application/json');
        print encode_json( $out->{json} );
    }
    elsif ( $out->{text} ) {
        print $q->header('text/plain');
        print $out->{text};
    }
    else {
        print $q->header('text/html; charset=utf-8');
        $T ||= Template->new();
        $T->process( $out->{template}, $out ) || die $T->error();
    }
}

sub video_list {
    my ( $q, $out, $opts ) = @_;

    my $order = $opts->{order_by} || 'home_video.create_date desc';
    my $limit = $opts->{limit}    || 50;

    my $sth = _dbh->prepare_cached(
        qq{
        SELECT    home_video.id AS home_video_id,
                  home_video.title,
                  home_video.create_date,
                  video_file.id AS id,
                  video_file.duration,
                  watch_status.position,
                  watch_status.modify_date AS last_watched
        FROM      home_video
        JOIN      video_file ON video_file.mapper_id = home_video.mapper_id
        LEFT JOIN watch_status ON watch_status.mapper_id = home_video.mapper_id
        ORDER BY $order
        LIMIT    $limit
    }
    );
    $sth->execute;

    $out->{sid} = _get_sid();

    my $list = $out->{video_list} = [];

    while ( my $video = $sth->fetchrow_hashref ) {
        $video->{title} =~ s/_\d{4}$//;
        $video->{hms} = _sec2string( $video->{duration} );
        $video->{position} ||= 0;
        $video->{position_hms} = $video->{position} ? _sec2string( $video->{position} ) : 0;

        if ( $video->{duration} > 0 ) {
            $video->{watched} = sprintf '%2d', ( $video->{position} / $video->{duration} ) * 100;

            # Hide nearly-finished videos
            next if $video->{watched} >= 98;
        }
        else {
            $video->{watched} = 0;
        }

        my $m3u8 = catfile( HLS_CACHE_DIR, 'video_' . $video->{id} . '.m3u8' );
        $video->{transcoded} = -f $m3u8 ? 1 : 0;

        # Cache thumbnails cause I don't know what poster.cgi does
        my $thumb = catfile( IMAGE_CACHE_DIR, 'poster_' . $video->{id} . '.jpg' );
        if ( !-e $thumb ) {
            my $res = $ua->get(
                      "http://localhost:5000/video/webapi/VideoStation/poster.cgi?" . "_sid="
                    . $out->{sid}
                    . "&api=SYNO.VideoStation.Poster&method=getimage&version=2"
                    . "&type=home_video&id="
                    . $video->{home_video_id},
                ':content_file' => "${thumb}.tmp",
            );

            my $cmd = "/bin/convert ${thumb}.tmp -resize 320 $thumb";
            system($cmd);
            unlink "${thumb}.tmp";
        }

        push @{$list}, $video;
    }
}

sub transcode_video {
    my ( $q, $out ) = @_;

    my $id    = $q->param('id')    || die "No id provided\n";
    my $start = $q->param('start') || 0;

    my $sth = _dbh->prepare_cached('SELECT path FROM video_file WHERE id = ?');
    $sth->execute($id);

    my ($path) = $sth->fetchrow_array;

    if ( !-r $path ) {
        $out->{json} = { error => "Can't read $path" };
        return;
    }

    my $m3u8_file = catfile( HLS_CACHE_DIR, 'video_' . $id ) . '.m3u8';
    my $m3u8_url = "/hls/index.cgi?action=play&id=${id}&start=${start}";

    # If m3u8 file exists, page may have been reloaded, etc.
    if ( -e $m3u8_file ) {
        $out->{json} = {
            redirect => $m3u8_url,
        };
        return;
    }

    # Make sure we won't run out of space!
    # mpeg2-ts overhead is about 3%, but if you don't have 1.5x free space you're in trouble anyway
    my $wanted_free = ( stat $path )[7] * 2;
    my $ref = df( WORK_DIR, 1 );    # bytes, not 1K blocks
    if ( $ref->{bfree} < $wanted_free ) {
        $out->{json} = {
                  error => "YIKES! Your free disk space on this volume is down to "
                . sprintf( "%.2d", ( $ref->{bfree} / 1048576 ) ) . " MB. "
                . " Free up at least "
                . sprintf( "%.2d", ( $wanted_free / 1048576 ) )
                . " MB and try again. TODO: auto-clear cache and check again.",
        };
        return;
    }

    # Otherwise, launch a transcoding process
    my $proc = Proc::Reliable->new(
        num_tries    => 1,
        time_per_try => 600,
        maxtime      => 600,
    );

    $path =~ s{"}{\\"}g;    # escape any quotes in filenames
    my $cmd = "bash /volume1/web/hls/scripts/mp4-to-hls.sh \"$path\" \"$m3u8_file\"";
    warn "Running: $cmd\n";
    $proc->run($cmd);

    if ( $proc->status ) {
        $out->{json} = {
            error => "Transcoding failed",
            data  => {
                out    => $proc->stdout,
                err    => $proc->stderr,
                status => $proc->status,
                msg    => $proc->msg,
            },
        };

        warn "Failed: " . Dumper( $out->{json} ) . "\n";
    }
    else {
        # Good to go!
        $out->{json} = {
            redirect => $m3u8_url,
        };

        warn "Done! Redirect to $m3u8_url\n";
    }

    return;
}

sub transcode_progress {
    my ( $q, $out ) = @_;

    my $id       = $q->param('id')       || die "No id provided";
    my $duration = $q->param('duration') || 0;

    my $m3u8_file = catfile( HLS_CACHE_DIR, 'video_' . $id ) . '.m3u8';

    my $total = 0;
    eval {
        if ( -e $m3u8_file ) {

            # Add up the segments
            my $m3u8_data = _slurp($m3u8_file);
            for my $segment_time ( $m3u8_data =~ m/#EXTINF:([^,]+)/g ) {
                $total += $segment_time;
            }
        }
    };
    if ($@) {
        $out->{json} = {
            error => $@,
        };
    }
    else {
        if ($duration) {
            $out->{json} = {
                percent => sprintf( "%2d", ( $total / $duration ) * 100 ),
            };
            warn "transcode_progress { id: $id, duration: $duration } => percent: "
                . $out->{json}->{percent} . "\n";
        }
        else {    # just in case
            $out->{json} = {
                percent => 50,
            };
        }
    }
}

sub play_video {
    my ( $q, $out ) = @_;

    my $id = $q->param('id');

    $out->{template} = 'player.tt';
    $out->{src}      = "/hls/cache/video_${id}.m3u8";
    $out->{id}       = $q->param('id') || die "No id";
    $out->{start}    = $q->param('start') || 0;
    $out->{sid}      = _get_sid();
}

sub delete_video {
    my ( $q, $out ) = @_;

    my $id = $q->param('id') || die "No id provided";

    my $sid = _get_sid();

    my $res = $ua->post(
        "http://localhost:5000/video/webapi/entry.cgi",
        {
            api     => 'SYNO.VideoStation2.File',
            method  => 'delete',
            version => 1,
            id      => '[' . $id . ']',             # has to be a JSON array
        },

        # headers
        'X-SYNO-TOKEN' => $sid,
    );

    warn "delete response: " . Dumper($res) . "\n";

    $out->{text} = Dumper($res);

    return;

    $out->{json} = {
        ok => 1,
    };
}

sub update_watch {
    my ( $q, $out ) = @_;

    my $id  = $q->param('id');
    my $pos = $q->param('position');

    if ( $id && $pos ) {
        my $ua = LWP::UserAgent->new;

        my $u = URI->new( "", "http" );
        $u->query_form(
            {
                api      => 'SYNO.VideoStation.WatchStatus',
                version  => 1,
                method   => 'setinfo',
                id       => $id,
                position => $pos,
                _sid     => _get_sid(),
            }
        );

        my $req = HTTP::Request->new(
            GET => "http://localhost:5000/webapi/VideoStation/watchstatus.cgi?" . $u->query,
        );
        my $res = $ua->request($req);

        my $api_res;
        if ( $res->is_success ) {
            $api_res = decode_json( $res->content );
        }

        if ( $api_res && $api_res->{success} ) {
            $out->{ok} = 1;
        }
        else {
            #warn Dumper($res) . "\n";
            $out = {
                ok    => 0,
                error => $api_res ? $api_res : 'Unknown',
            };
        }
    }
    else {
        $out = {
            ok    => 0,
            error => "video_file_id and position params are required",
        };
    }
}

sub _get_sid {

    # Try to read from cached session file
    my $data = eval { decode_json( _slurp(SID_CACHE_FILE) ) };

    if ($@) {
        my $url = sprintf(
            "http://localhost:5000/webapi/auth.cgi?api=%s&version=%d&method=%s&account=%s&passwd=%s&session=%s&format=%s",
            'SYNO.API.Auth', 6, 'login', $CONF->{dsm_user}, $CONF->{dsm_pass}, 'VideoStation', 'sid'
        );
        my $req = HTTP::Request->new( GET => $url );
        my $res = $ua->request($req);
        if ( $res->is_success ) {
            $data = decode_json( $res->content );

            warn "Got new session ID from Syno.API.Auth: " . $data->{data}->{sid} . "\n";
        }

        open my $fh, '>', SID_CACHE_FILE or die "Unable to create cache file: $!";
        print $fh $res->content;
        close $fh;
    }

    return $data->{data}->{sid};
}

sub read_config_file {
    my $filename = shift;

    my %conf;

    open my $f, '<', $filename
        or die "can't open $filename for reading: $!";

    while (<$f>) {
        chomp;
        next unless $_ and $_ !~ /^\s*#/;

        my ( $k, $v ) = m/^\s*(\w+)\s+(.+)$/;
        die "multiple enties for $k" if $conf{$k};
        $conf{$k} = $v;
    }

    # minimum validation of arguments
    die "Configured user has trailing whitespace"
        if defined $conf{dsm_user} && $conf{dsm_user} =~ /\s$/;
    die "Configured pass contains whitespace"
        if defined $conf{dsm_pass} && $conf{dsm_pass} =~ /\s/;

    return \%conf;
}

sub _sec2string {
    my $secs = shift;

    if ( $secs >= 3600 ) {
        return sprintf( "%d:%02d:%02d", ( $secs / 3600 ), ( $secs / 60 ) % 60, $secs % 60 );
    }
    else {
        return sprintf( "%02d:%02d", ( $secs / 60 ) % 60, $secs % 60 );
    }
}

sub _slurp {
    my $f = shift;
    open my $fh, "<", $f or die "Can't open $f: $!";
    local $/;
    scalar(<$fh>);
}
