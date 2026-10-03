#!/usr/bin/perl -w

# vnstat-json.cgi -- example cgi for vnStat json output
# copyright (c) 2015-2021 Teemu Toivola <tst at iki dot fi>
# released under the GNU General Public License
# Security backport (2026-10-04): execute commands without a shell.

use strict;

# location of vnstat binary
my $vnstat_cmd = '/usr/bin/vnstat';

# individually accessible interfaces with ?interface=N or /interfacename suffix
# for static list, uncomment first line below, update the list and comment out second line
#my @interfaces = ('eth0', 'eth1');
my @interfaces = load_interfaces();


################


sub load_interfaces
{
	open(my $iflist, "-|", $vnstat_cmd, "--dbiflist", "1") or die "Failed to list interfaces: $!";
	my @lines = <$iflist>;
	close $iflist or die "Failed to list interfaces";
	return @lines;
}

my @iface;
chomp @interfaces;

if (defined $ENV{PATH_INFO}) {
	my @fields = split(/\//, $ENV{PATH_INFO});
	my $interface = $fields[-1];
	for my $i (0..$#interfaces) {
		if ($interfaces[${i}] eq $interface) {
			@iface = ("-i", $interface);
			last;
		}
	}
}

if (!@iface and defined $ENV{QUERY_STRING}) {
	my $getiface = "";
	my @values = split(/&/, $ENV{QUERY_STRING});
	foreach my $i (@values) {
		my ($varname, $varvalue) = split(/=/, $i);
		if ($varname eq 'interface' && $varvalue =~ /^(\d+)$/) {
			$getiface = $varvalue;
		}
	}

	if (length($getiface) > 0 && $getiface >= 0 && $getiface <= $#interfaces) {
		@iface = ("-i", $interfaces[int($getiface)]);
	}
}

print "Content-Type: application/json\n\n";
exec {$vnstat_cmd} $vnstat_cmd, "--json", @iface;
