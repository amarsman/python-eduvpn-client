import logging
import signal
import sys
from os import geteuid
from sys import exit, argv

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

logger = logging.getLogger(__name__)
log_format = format_ = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'


# def parse_args(args: List[str]) -> Optional[str]:
#     parser = ArgumentParser(description='The eduVPN gui client')
#     args = parser.parse_args(args)
#     return args.search

def signal_handler(sig, frame):
    sys.exit(0)


# def main(args: List[str]):
def main(args=None):
    if args is None:
        args = sys.argv
    logging.basicConfig(level=logging.DEBUG)

    signal.signal(signal.SIGINT, signal_handler)

    # parse_args(args)

    if geteuid() == 0:
        logger.error(u"Running eduVPN client as root is not supported (yet)")
        exit(1)

    # import this later so the logging is properly configured
    from eduvpngui.ui import EduVpnGui

    edu_vpn_gui = EduVpnGui(lets_connect=False)
    edu_vpn_gui.run()

    Gtk.main()


def letsconnect():
    raise NotImplementedError("todo :)")


if __name__ == '__main__':
    main(args=argv)
