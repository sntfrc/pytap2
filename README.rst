``pytap3`` - Cross-platform tunnel interface for Python
=======================================================

This is a cross-platform fork of the original
`johnthagen/pytap2 <https://github.com/johnthagen/pytap2>`_. It provides a
packet-oriented interface to TUN devices on Linux, macOS, and Windows.

For amateur radio operators, it also includes a handy command-line utility,
``kisstun``, which automatically creates and configures a TUN interface from
an IPv4 address and prefix, then bridges IP packets between that interface
and a TCP-connected KISS TNC such as Dire Wolf. Instant, cross-platform
packet radio networking!


Requirements
------------

Requirements depend on your operating system:

* **Linux:** Install ``net-tools`` to provide the ``ifconfig`` command.

  On Debian/Ubuntu:

  .. code:: shell-session

      $ sudo apt install net-tools

  On RHEL/Rocky Linux/Fedora:

  .. code:: shell-session

      $ sudo yum install net-tools

* **macOS:** No additional packages are required; ``ifconfig`` is included
  with macOS.

* **Windows:** ``wintun.dll`` is required. When building/installing from source
  on Windows, the package downloads the signed Wintun 0.14.1 archive from
  `Wintun <https://www.wintun.net/>`_, verifies its SHA-256 checksum, and bundles
  the DLL matching the Python platform. This requires network access during
  installation. Wheels are platform-tagged; build Windows wheels on Windows to
  include the DLL. Source distributions build locally on any supported OS.

Creating and configuring a TUN device may require administrator or root
privileges.

Installation
------------

You can install, upgrade, and uninstall ``pytap3`` with these commands:

.. code:: shell-session

    $ pip install pytap3
    $ pip install --upgrade pytap3
    $ pip uninstall pytap3

Usage
-----

Using as a context manager automatically brings up the device and closes it at the
end of the ``with`` block.

.. code:: python

    from pytap3 import TapDevice

    with TapDevice() as device:
        device.ifconfig(mtu=1300)
        device.write(b'0000')

Or manually call ``up()`` and ``close()``.

.. code:: python

    from pytap3 import TapDevice

    device = TapDevice()
    device.up()
    device.ifconfig(mtu=1300)
    device.write(b'0000')
    device.close()

The ``fileno()`` method is defined, so that the device object can be passed directly
to `select() <https://docs.python.org/library/select.html#select.select>`_. This might
not work on Windows, as the underlying Wintun driver does not support this.

On macOS, configuring an IP address with ``ifconfig(ip=..., netmask=...)`` also
adds a route for that subnet through the ``utun`` interface. Routes that conflict
with an existing route may require administrator privileges or manual adjustment.

You can make pytap3 a drop-in replacement for pytap2 by just importing it like this:
 ``import pytap3 as pytap2``

``kisstun`` command
-------------------

Installing ``pytap3`` provides the ``kisstun`` command. It creates and
configures a TUN interface from an IPv4 address and prefix, then bridges IP
packets between that interface and a TCP-connected KISS TNC. For example:

.. code:: shell-session

    $ sudo kisstun 10.73.0.1/16

The default TCP KISS endpoint is ``127.0.0.1:8001``; the default KISS hardware
port is 0 and MTU is 256. Use ``--host``, ``--port``, ``--kiss-port``, and
``--mtu`` to change these settings. Run ``kisstun --help`` for the full option
list. Creating the interface and routing its subnet may require root or
administrator privileges.

The command can also be run as a Python module:

.. code:: shell-session

    $ sudo python3 -m pytap3.kisstun 10.73.0.1/16

Pass ``--direwolf`` to launch ``direwolf`` from ``PATH`` and wait for its TCP
KISS listener before connecting. Dire Wolf must be configured to listen at the
selected endpoint (by default ``127.0.0.1:8001``). The child process is
terminated when ``kisstun`` exits.

Specify a different TCP TNC endpoint, KISS port, or MTU with options:

.. code:: shell-session

    $ sudo kisstun 10.73.0.1/16 --host 192.168.1.10 --port 8001 --kiss-port 2 --mtu 256
    $ sudo kisstun 10.73.0.1/16 --direwolf

Releases
--------

3.1.0 - 2026-10-26
^^^^^^^^^^^^^^^^^^

- Added the ``kisstun`` utility for my fellow amateur radio operators.

3.0.2 - 2026-10-26
^^^^^^^^^^^^^^^^^^

- Bugfix: use interface routing on macOS, like the test was expecting.

3.0.0 - 2026-10-26
^^^^^^^^^^^^^^^^^^

- Windows, Linux and macOS support!
