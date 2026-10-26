``pytap3`` - Cross-platform tunnel interface for Python
=======================================================

This is a cross-platform fork of the original
`johnthagen/pytap2 <https://github.com/johnthagen/pytap2>`_. It provides a
packet-oriented interface to TUN devices on Linux, macOS, and Windows.

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

Releases
--------

3.0.1 - 2026-10-26
^^^^^^^^^^^^^^^^^^

- Bugfix: use interface routing on macOS, like the test was expecting.

3.0.0 - 2026-10-26
^^^^^^^^^^^^^^^^^^

- Windows, Linux and macOS support!
