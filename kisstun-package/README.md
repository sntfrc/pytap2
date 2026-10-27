# kisstun

This package is an installation convenience alias for
[pytap3](https://pypi.org/project/pytap3/). It does not replace or modify the
upstream pytap3 project. Installing `kisstun` just installs `pytap3` as a
dependency.


``kisstun`` command
-------------------

Installing ``pytap3`` provides the ``kisstun`` command. It creates and
configures a TUN interface from an IPv4 address and prefix, then bridges IP
packets between that interface and a TCP-connected KISS TNC. For example:

```shell
$ sudo kisstun 10.73.0.1/16
```

The default TCP KISS endpoint is ``127.0.0.1:8001``; the default KISS hardware
port is 0 and MTU is 256. Use ``--host``, ``--port``, ``--kiss-port``, and
``--mtu`` to change these settings. Run ``kisstun --help`` for the full option
list. Creating the interface and routing its subnet may require root or
administrator privileges.

To limit packet-radio traffic, ``kisstun`` filters outgoing packets by default,
forwarding IPv4 unicast and broadcast only. It drops IPv6, IPv4 multicast, and
UDP discovery traffic on ports 67, 68, 137, 138, 1900, 3702, 5353, and 5355
(DHCP, NetBIOS, SSDP, WS-Discovery, mDNS, and LLMNR), including broadcasts
using those ports. Incoming KISS packets are passed to the TUN interface
without this filter. Use ``--no-filter`` to disable filtering of outgoing
packets.

Please note that TCP is a very chatty protocol and is not ideal for packet radio.
Applications using UDP or ICMP are more suitable for this type of networking.
If you are using TCP, consider tweaking the stack parameters to be more
bandwidth-efficient, such as disabling Nagle's algorithm and reducing
the TCP window size. 

The command can also be run as a Python module:

```shell
$ sudo python3 -m pytap3.kisstun 10.73.0.1/16
```

Pass ``--direwolf`` to launch ``direwolf`` from ``PATH`` and wait for its TCP
KISS listener before connecting. Dire Wolf must be configured to listen at the
selected endpoint (by default ``127.0.0.1:8001``). The child process is
terminated when ``kisstun`` exits.

Specify a different TCP TNC endpoint, KISS port, or MTU with options:

```shell
$ sudo kisstun 10.73.0.1/16 --host 192.168.1.10 --port 8001 --kiss-port 2 --mtu 256
$ sudo kisstun 10.73.0.1/16 --direwolf
```
