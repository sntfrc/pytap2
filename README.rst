``pytap3`` - Cross-platform TUN interface for Python
====================================================

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

* **Windows:** ``wintun.dll`` is required. Download the signed DLL matching
  your system architecture from `Wintun <https://www.wintun.net/>`_ and make it
  available beside the installed ``pytap2`` module or on ``PATH``.

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
to `select() <https://docs.python.org/library/select.html#select.select>`_.

Releases
--------

3.0.0 - 2024-06-05
^^^^^^^^^^^^^^^^^^

- Windows, Linux and macOS support!
